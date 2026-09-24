import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.collection.queue import enqueue_job
from opportunity_api.database import get_session
from opportunity_api.intelligence.schemas import (
    ClusterDetail,
    ClusterEntityRead,
    ClusterRead,
    EntityRead,
    IntelligenceBackfill,
    IntelligenceMetrics,
    MembershipRead,
    RelationshipRead,
)
from opportunity_api.intelligence.service import intelligence_metrics, pending_signals_query
from opportunity_api.models import (
    ClusterEntity,
    ClusterMembership,
    ClusterStatus,
    ClusterType,
    EntityEdge,
    EntityType,
    EvidenceCluster,
    KnowledgeEntity,
    Signal,
)

router = APIRouter(prefix="/intelligence", tags=["evidence intelligence"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/signals/{signal_id}/cluster", status_code=202)
async def queue_signal(signal_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    if await session.get(Signal, signal_id) is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    await enqueue_job("cluster_evidence_signal", str(signal_id))
    return {"status": "queued", "signal_id": str(signal_id)}


@router.post("/backfill", status_code=202)
async def queue_backfill(payload: IntelligenceBackfill, session: SessionDep) -> dict[str, int]:
    signals = list(
        (await session.scalars(pending_signals_query(payload.limit, include_failed=True))).all()
    )
    for signal in signals:
        await enqueue_job("cluster_evidence_signal", str(signal.id))
    return {"queued": len(signals)}


@router.get("/clusters", response_model=list[ClusterRead])
async def list_clusters(
    session: SessionDep,
    cluster_type: ClusterType | None = None,
    status: ClusterStatus = ClusterStatus.active,
    min_corroboration: float = Query(default=0, ge=0, le=1),
    min_sources: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[EvidenceCluster]:
    statement = (
        select(EvidenceCluster)
        .where(
            EvidenceCluster.status == status,
            EvidenceCluster.corroboration_score >= min_corroboration,
            EvidenceCluster.source_count >= min_sources,
        )
        .order_by(
            EvidenceCluster.corroboration_score.desc(),
            EvidenceCluster.velocity_30d.desc(),
        )
        .limit(limit)
    )
    if cluster_type:
        statement = statement.where(EvidenceCluster.cluster_type == cluster_type)
    return list((await session.scalars(statement)).all())


@router.get("/clusters/{cluster_id}", response_model=ClusterDetail)
async def get_cluster(cluster_id: uuid.UUID, session: SessionDep) -> ClusterDetail:
    cluster = await session.get(EvidenceCluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    memberships = list(
        (
            await session.scalars(
                select(ClusterMembership)
                .where(ClusterMembership.cluster_id == cluster.id)
                .order_by(ClusterMembership.similarity.desc())
            )
        ).all()
    )
    entity_rows = (
        await session.execute(
            select(ClusterEntity, KnowledgeEntity)
            .join(KnowledgeEntity, KnowledgeEntity.id == ClusterEntity.entity_id)
            .where(ClusterEntity.cluster_id == cluster.id)
            .order_by(ClusterEntity.support_count.desc())
        )
    ).all()
    payload = ClusterRead.model_validate(cluster).model_dump()
    return ClusterDetail(
        **payload,
        memberships=[MembershipRead.model_validate(item) for item in memberships],
        entities=[
            ClusterEntityRead(
                entity_id=entity.id,
                entity_type=entity.entity_type,
                display_value=entity.display_value,
                relation=association.relation,
                support_count=association.support_count,
            )
            for association, entity in entity_rows
        ],
    )


@router.get("/entities", response_model=list[EntityRead])
async def list_entities(
    session: SessionDep,
    entity_type: EntityType | None = None,
    q: str | None = Query(default=None, min_length=2, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[KnowledgeEntity]:
    statement = select(KnowledgeEntity).order_by(KnowledgeEntity.display_value).limit(limit)
    if entity_type:
        statement = statement.where(KnowledgeEntity.entity_type == entity_type)
    if q:
        statement = statement.where(KnowledgeEntity.display_value.ilike(f"%{q}%"))
    return list((await session.scalars(statement)).all())


@router.get("/relationships", response_model=list[RelationshipRead])
async def list_relationships(
    session: SessionDep,
    entity_id: uuid.UUID | None = None,
    min_support: int = Query(default=1, ge=1),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[EntityEdge]:
    statement = (
        select(EntityEdge)
        .where(EntityEdge.support_count >= min_support)
        .order_by(EntityEdge.support_count.desc())
        .limit(limit)
    )
    if entity_id:
        statement = statement.where(
            or_(
                EntityEdge.source_entity_id == entity_id,
                EntityEdge.target_entity_id == entity_id,
            )
        )
    return list((await session.scalars(statement)).all())


@router.get("/metrics", response_model=IntelligenceMetrics)
async def get_metrics(session: SessionDep) -> dict[str, int]:
    return await intelligence_metrics(session)
