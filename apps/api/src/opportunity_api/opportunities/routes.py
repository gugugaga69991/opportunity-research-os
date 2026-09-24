import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.collection.queue import enqueue_job
from opportunity_api.database import get_session
from opportunity_api.models import (
    EvidenceCluster,
    HypothesisReadiness,
    HypothesisTrack,
    OpportunityClusterLink,
    OpportunityEvidence,
    OpportunityHypothesis,
    OpportunityStatus,
    OpportunityTransition,
)
from opportunity_api.opportunities.schemas import (
    OpportunityBackfill,
    OpportunityClusterRead,
    OpportunityDetail,
    OpportunityEvidenceRead,
    OpportunityMetrics,
    OpportunityRead,
    StateChange,
    TransitionRead,
)
from opportunity_api.opportunities.service import (
    opportunity_metrics,
    pending_hypothesis_clusters_query,
    transition_opportunity,
)

router = APIRouter(prefix="/opportunities", tags=["opportunity hypotheses"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/clusters/{cluster_id}/generate", status_code=202)
async def queue_cluster(cluster_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    if await session.get(EvidenceCluster, cluster_id) is None:
        raise HTTPException(status_code=404, detail="Evidence cluster not found")
    await enqueue_job("generate_opportunity_hypothesis", str(cluster_id))
    return {"status": "queued", "cluster_id": str(cluster_id)}


@router.post("/generate/backfill", status_code=202)
async def queue_backfill(payload: OpportunityBackfill, session: SessionDep) -> dict[str, int]:
    clusters = list((await session.scalars(pending_hypothesis_clusters_query(payload.limit))).all())
    for cluster in clusters:
        await enqueue_job("generate_opportunity_hypothesis", str(cluster.id))
    return {"queued": len(clusters)}


@router.get("", response_model=list[OpportunityRead])
async def list_opportunities(
    session: SessionDep,
    track: HypothesisTrack | None = None,
    status: OpportunityStatus | None = None,
    readiness: HypothesisReadiness | None = None,
    evidence_gate_passed: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OpportunityHypothesis]:
    statement = (
        select(OpportunityHypothesis)
        .order_by(
            OpportunityHypothesis.evidence_gate_passed.desc(),
            OpportunityHypothesis.confidence.desc(),
        )
        .limit(limit)
    )
    if track:
        statement = statement.where(OpportunityHypothesis.track == track)
    if status:
        statement = statement.where(OpportunityHypothesis.status == status)
    if readiness:
        statement = statement.where(OpportunityHypothesis.readiness == readiness)
    if evidence_gate_passed is not None:
        statement = statement.where(
            OpportunityHypothesis.evidence_gate_passed == evidence_gate_passed
        )
    return list((await session.scalars(statement)).all())


@router.get("/metrics", response_model=OpportunityMetrics)
async def get_metrics(session: SessionDep) -> dict[str, int]:
    return await opportunity_metrics(session)


@router.get("/{opportunity_id}", response_model=OpportunityDetail)
async def get_opportunity(opportunity_id: uuid.UUID, session: SessionDep) -> OpportunityDetail:
    opportunity = await session.get(OpportunityHypothesis, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity hypothesis not found")
    evidence = list(
        (
            await session.scalars(
                select(OpportunityEvidence)
                .where(OpportunityEvidence.opportunity_id == opportunity.id)
                .order_by(
                    OpportunityEvidence.stance,
                    OpportunityEvidence.confidence.desc(),
                )
            )
        ).all()
    )
    clusters = list(
        (
            await session.scalars(
                select(OpportunityClusterLink)
                .where(OpportunityClusterLink.opportunity_id == opportunity.id)
                .order_by(OpportunityClusterLink.role)
            )
        ).all()
    )
    transitions = list(
        (
            await session.scalars(
                select(OpportunityTransition)
                .where(OpportunityTransition.opportunity_id == opportunity.id)
                .order_by(OpportunityTransition.created_at)
            )
        ).all()
    )
    payload = OpportunityRead.model_validate(opportunity).model_dump()
    detail_fields = {
        field: getattr(opportunity, field)
        for field in (
            "core_workflow",
            "frequency",
            "current_workaround",
            "economic_cost",
            "existing_spend",
            "why_now",
            "desired_outcome",
            "value_proposition",
            "thesis",
            "genealogy",
        )
    }
    return OpportunityDetail(
        **payload,
        **detail_fields,
        evidence=[OpportunityEvidenceRead.model_validate(item) for item in evidence],
        clusters=[OpportunityClusterRead.model_validate(item) for item in clusters],
        transitions=[TransitionRead.model_validate(item) for item in transitions],
    )


@router.patch("/{opportunity_id}/state", response_model=OpportunityRead)
async def change_state(
    opportunity_id: uuid.UUID,
    payload: StateChange,
    session: SessionDep,
) -> OpportunityHypothesis:
    opportunity = await session.get(OpportunityHypothesis, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity hypothesis not found")
    try:
        return await transition_opportunity(
            session,
            opportunity,
            payload.status,
            payload.reason,
            payload.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{opportunity_id}/refresh", status_code=202)
async def refresh_opportunity(opportunity_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    opportunity = await session.get(OpportunityHypothesis, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity hypothesis not found")
    await enqueue_job("generate_opportunity_hypothesis", str(opportunity.origin_cluster_id))
    return {"status": "queued", "opportunity_id": str(opportunity.id)}
