import itertools
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.config import Settings
from opportunity_api.intelligence.entities import (
    ClusterDescriptor,
    EntityCandidate,
    cluster_descriptors,
    entities_from_document_context,
    entities_from_ontology,
)
from opportunity_api.models import (
    ClusterEntity,
    ClusterMembership,
    ClusterStatus,
    ClusterType,
    EntityEdge,
    EntityType,
    EvidenceCluster,
    KnowledgeEntity,
    MembershipMethod,
    ProcessingStatus,
    RawDocument,
    Signal,
    SignalEntity,
    SignalExtraction,
    Source,
)

GRAPH_ENTITY_TYPES = {
    EntityType.industry,
    EntityType.subindustry,
    EntityType.company,
    EntityType.role,
    EntityType.trigger,
    EntityType.task,
    EntityType.pain_type,
    EntityType.tool,
    EntityType.software,
}
CLUSTER_ANCHOR_ENTITY_TYPES = {
    EntityType.industry,
    EntityType.subindustry,
    EntityType.role,
    EntityType.trigger,
    EntityType.task,
    EntityType.pain_type,
}
EVIDENCE_FIELD_BY_RELATION = {
    "uses_tool": "tools",
    "uses_software": "current_software",
    "workflow_input": "inputs",
    "workflow_output": "outputs",
    "workflow_step": "current_workflow",
    "manual_step": "manual_steps",
}


async def _upsert_entities(
    session: AsyncSession,
    signal: Signal,
    candidates: list[EntityCandidate],
    evidence_spans: list[dict],
) -> dict[tuple[EntityType, str], KnowledgeEntity]:
    entities: dict[tuple[EntityType, str], KnowledgeEntity] = {}
    for candidate in candidates:
        entity = await session.scalar(
            select(KnowledgeEntity).where(
                KnowledgeEntity.entity_type == candidate.entity_type,
                KnowledgeEntity.normalized_value == candidate.normalized_value,
            )
        )
        if entity is None:
            entity = KnowledgeEntity(
                entity_type=candidate.entity_type,
                display_value=candidate.display_value,
                normalized_value=candidate.normalized_value,
                aliases=[],
                metadata_={},
            )
            session.add(entity)
            await session.flush()
        elif (
            candidate.display_value != entity.display_value
            and candidate.display_value not in entity.aliases
        ):
            entity.aliases = [*entity.aliases, candidate.display_value][:25]

        link = await session.scalar(
            select(SignalEntity).where(
                SignalEntity.signal_id == signal.id,
                SignalEntity.entity_id == entity.id,
                SignalEntity.relation == candidate.relation,
            )
        )
        if link is None:
            ontology_field = EVIDENCE_FIELD_BY_RELATION.get(candidate.relation, candidate.relation)
            matching_evidence = [
                span
                for span in evidence_spans
                if span.get("field")
                in {ontology_field, candidate.relation, candidate.entity_type.value}
            ]
            session.add(
                SignalEntity(
                    signal_id=signal.id,
                    entity_id=entity.id,
                    relation=candidate.relation,
                    confidence=candidate.confidence,
                    evidence=matching_evidence,
                )
            )
        entities[(candidate.entity_type, candidate.normalized_value)] = entity
    await session.flush()
    return entities


async def _update_graph_edges(
    session: AsyncSession,
    signal: Signal,
    entities: dict[tuple[EntityType, str], KnowledgeEntity],
) -> None:
    graph_entities = sorted(
        {
            entity.id: entity
            for entity in entities.values()
            if entity.entity_type in GRAPH_ENTITY_TYPES
        }.values(),
        key=lambda entity: str(entity.id),
    )
    signal_id = str(signal.id)
    for left, right in itertools.combinations(graph_entities, 2):
        edge = await session.scalar(
            select(EntityEdge).where(
                EntityEdge.source_entity_id == left.id,
                EntityEdge.target_entity_id == right.id,
                EntityEdge.relation == "co_occurs",
            )
        )
        if edge is None:
            session.add(
                EntityEdge(
                    source_entity_id=left.id,
                    target_entity_id=right.id,
                    relation="co_occurs",
                    support_count=1,
                    confidence=0.2,
                    supporting_signal_ids=[signal_id],
                )
            )
        elif signal_id not in edge.supporting_signal_ids:
            edge.supporting_signal_ids = [*edge.supporting_signal_ids, signal_id][-100:]
            edge.support_count += 1
            edge.confidence = min(1.0, 1 - (0.8**edge.support_count))


async def _existing_cluster_for_signal(
    session: AsyncSession, signal_id: uuid.UUID, cluster_type: ClusterType
) -> EvidenceCluster | None:
    return await session.scalar(
        select(EvidenceCluster)
        .join(ClusterMembership, ClusterMembership.cluster_id == EvidenceCluster.id)
        .where(
            ClusterMembership.signal_id == signal_id,
            EvidenceCluster.cluster_type == cluster_type,
        )
        .limit(1)
    )


async def _find_cluster(
    session: AsyncSession,
    descriptor: ClusterDescriptor,
    signal: Signal,
    anchor_entity_ids: set[uuid.UUID],
    settings: Settings,
) -> tuple[EvidenceCluster | None, float, MembershipMethod]:
    exact = await session.scalar(
        select(EvidenceCluster).where(
            EvidenceCluster.cluster_type == descriptor.cluster_type,
            EvidenceCluster.cluster_key == descriptor.cluster_key,
            EvidenceCluster.status == ClusterStatus.active,
        )
    )
    if exact:
        return exact, 1.0, MembershipMethod.fingerprint
    if signal.embedding is None:
        return None, 0.0, MembershipMethod.fingerprint

    distance = EvidenceCluster.centroid.cosine_distance(signal.embedding)
    rows = (
        await session.execute(
            select(EvidenceCluster, distance.label("distance"))
            .where(
                EvidenceCluster.cluster_type == descriptor.cluster_type,
                EvidenceCluster.status == ClusterStatus.active,
                EvidenceCluster.centroid.is_not(None),
            )
            .order_by(distance)
            .limit(10)
        )
    ).all()
    for cluster, cosine_distance in rows:
        similarity = 1 - float(cosine_distance)
        if similarity < settings.cluster_semantic_threshold:
            break
        overlap = 0
        if anchor_entity_ids:
            overlap = int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(ClusterEntity)
                        .where(
                            ClusterEntity.cluster_id == cluster.id,
                            ClusterEntity.entity_id.in_(anchor_entity_ids),
                        )
                    )
                )
                or 0
            )
        if overlap > 0:
            return cluster, similarity, MembershipMethod.hybrid
        if similarity >= settings.cluster_high_confidence_threshold:
            return cluster, similarity, MembershipMethod.semantic
    return None, 0.0, MembershipMethod.fingerprint


def _updated_centroid(
    current: list[float] | None, count: int, vector: list[float] | None
) -> tuple[list[float] | None, int]:
    if vector is None:
        return current, count
    incoming = [float(value) for value in vector]
    if current is None or count <= 0:
        return incoming, 1
    existing = [float(value) for value in current]
    return (
        [(old * count + new) / (count + 1) for old, new in zip(existing, incoming, strict=True)],
        count + 1,
    )


def corroboration_score(
    source_count: int,
    evidence_type_count: int,
    signal_count: int,
    recurrence_score: float,
) -> float:
    return min(
        1.0,
        0.4 * min(source_count / 3, 1)
        + 0.3 * min(evidence_type_count / 3, 1)
        + 0.2 * min(signal_count / 5, 1)
        + 0.1 * recurrence_score,
    )


async def _attach_entities_to_cluster(
    session: AsyncSession,
    cluster: EvidenceCluster,
    entities: dict[tuple[EntityType, str], KnowledgeEntity],
) -> None:
    for entity in entities.values():
        association = await session.scalar(
            select(ClusterEntity).where(
                ClusterEntity.cluster_id == cluster.id,
                ClusterEntity.entity_id == entity.id,
                ClusterEntity.relation == "contains",
            )
        )
        if association is None:
            session.add(
                ClusterEntity(
                    cluster_id=cluster.id,
                    entity_id=entity.id,
                    relation="contains",
                    support_count=1,
                )
            )
        else:
            association.support_count += 1


async def refresh_cluster_metrics(session: AsyncSession, cluster: EvidenceCluster) -> None:
    observed_at = func.coalesce(RawDocument.published_at, RawDocument.collected_at)
    aggregates = (
        await session.execute(
            select(
                func.count(distinct(ClusterMembership.signal_id)),
                func.count(distinct(RawDocument.source_id)),
                func.count(distinct(Source.source_type)),
                func.min(observed_at),
                func.max(observed_at),
            )
            .select_from(ClusterMembership)
            .join(Signal, Signal.id == ClusterMembership.signal_id)
            .join(RawDocument, RawDocument.id == Signal.raw_document_id)
            .join(Source, Source.id == RawDocument.source_id)
            .where(ClusterMembership.cluster_id == cluster.id)
        )
    ).one()
    signal_count, source_count, evidence_type_count, first_seen, last_seen = aggregates
    cutoff = datetime.now(UTC) - timedelta(days=30)
    recent_count = int(
        (
            await session.scalar(
                select(func.count(distinct(ClusterMembership.signal_id)))
                .select_from(ClusterMembership)
                .join(Signal, Signal.id == ClusterMembership.signal_id)
                .join(RawDocument, RawDocument.id == Signal.raw_document_id)
                .where(
                    ClusterMembership.cluster_id == cluster.id,
                    observed_at >= cutoff,
                )
            )
        )
        or 0
    )
    source_types = list(
        (
            await session.scalars(
                select(distinct(Source.source_type))
                .select_from(ClusterMembership)
                .join(Signal, Signal.id == ClusterMembership.signal_id)
                .join(RawDocument, RawDocument.id == Signal.raw_document_id)
                .join(Source, Source.id == RawDocument.source_id)
                .where(ClusterMembership.cluster_id == cluster.id)
            )
        ).all()
    )
    cluster.signal_count = int(signal_count or 0)
    cluster.source_count = int(source_count or 0)
    cluster.evidence_type_count = int(evidence_type_count or 0)
    cluster.first_seen_at = first_seen
    cluster.last_seen_at = last_seen
    cluster.velocity_30d = recent_count / max(cluster.signal_count, 1)
    cluster.corroboration_score = corroboration_score(
        cluster.source_count,
        cluster.evidence_type_count,
        cluster.signal_count,
        cluster.recurrence_score,
    )
    cluster.metrics = {
        "recent_30d": recent_count,
        "source_types": sorted(source_types),
        "independent_sources": cluster.source_count,
        "evidence_categories": cluster.evidence_type_count,
    }


async def cluster_signal(
    session: AsyncSession, signal_id: uuid.UUID, settings: Settings
) -> list[EvidenceCluster]:
    signal = await session.get(Signal, signal_id)
    if signal is None:
        raise LookupError(f"Signal {signal_id} does not exist")
    if signal.status != ProcessingStatus.succeeded or signal.is_duplicate:
        return []
    if signal.intelligence_status == ProcessingStatus.succeeded:
        return list(
            (
                await session.scalars(
                    select(EvidenceCluster)
                    .join(
                        ClusterMembership,
                        ClusterMembership.cluster_id == EvidenceCluster.id,
                    )
                    .where(ClusterMembership.signal_id == signal.id)
                )
            ).all()
        )
    if signal.intelligence_status == ProcessingStatus.running and signal.updated_at > datetime.now(
        UTC
    ) - timedelta(minutes=15):
        return []
    signal.intelligence_status = ProcessingStatus.running
    signal.intelligence_error = None
    signal.intelligence_attempts += 1
    await session.commit()
    extraction = await session.scalar(
        select(SignalExtraction).where(SignalExtraction.signal_id == signal.id)
    )
    if extraction is None:
        signal.intelligence_status = ProcessingStatus.succeeded
        signal.intelligence_processed_at = datetime.now(UTC)
        await session.commit()
        return []
    document = await session.get(RawDocument, signal.raw_document_id)
    if document is None:
        raise LookupError(f"Raw document {signal.raw_document_id} does not exist")
    source = await session.get(Source, document.source_id)
    if source is None:
        raise LookupError(f"Source {document.source_id} does not exist")

    ontology = extraction.ontology
    candidates = [
        *entities_from_ontology(ontology, extraction.confidence),
        *entities_from_document_context(document.raw_payload),
    ]
    entities = await _upsert_entities(session, signal, candidates, extraction.evidence_spans)
    await _update_graph_edges(session, signal, entities)
    anchor_ids = {
        entity.id
        for entity in entities.values()
        if entity.entity_type in CLUSTER_ANCHOR_ENTITY_TYPES
    }
    descriptors = cluster_descriptors(
        ontology,
        is_pain=extraction.is_pain,
        source_type=source.source_type,
        document_type=document.document_type,
        fallback_title=document.title,
    )
    clusters: list[EvidenceCluster] = []
    for descriptor in descriptors:
        existing = await _existing_cluster_for_signal(session, signal.id, descriptor.cluster_type)
        if existing:
            clusters.append(existing)
            continue
        cluster, similarity, method = await _find_cluster(
            session, descriptor, signal, anchor_ids, settings
        )
        if cluster is None:
            cluster = EvidenceCluster(
                cluster_type=descriptor.cluster_type,
                cluster_key=descriptor.cluster_key,
                title=descriptor.title,
                summary=descriptor.summary,
                status=ClusterStatus.active,
                metrics={},
            )
            session.add(cluster)
            await session.flush()
            similarity = 1.0
            method = MembershipMethod.fingerprint
        session.add(
            ClusterMembership(
                cluster_id=cluster.id,
                signal_id=signal.id,
                similarity=similarity,
                method=method,
                is_primary=descriptor.cluster_type == ClusterType.pain,
            )
        )
        cluster.centroid, cluster.centroid_count = _updated_centroid(
            cluster.centroid, cluster.centroid_count, signal.embedding
        )
        cluster.recurrence_score = max(cluster.recurrence_score, descriptor.recurrence_score)
        await _attach_entities_to_cluster(session, cluster, entities)
        await session.flush()
        await refresh_cluster_metrics(session, cluster)
        clusters.append(cluster)
    signal.intelligence_status = ProcessingStatus.succeeded
    signal.intelligence_processed_at = datetime.now(UTC)
    await session.commit()
    for cluster in clusters:
        await session.refresh(cluster)
    return clusters


def pending_signals_query(
    limit: int, *, include_failed: bool = False, retry_limit: int = 3
) -> Select[tuple[Signal]]:
    stale = datetime.now(UTC) - timedelta(minutes=15)
    states = [
        Signal.intelligence_status.is_(None),
        and_(
            Signal.intelligence_status == ProcessingStatus.running,
            Signal.updated_at < stale,
        ),
    ]
    if include_failed:
        states.append(
            and_(
                Signal.intelligence_status == ProcessingStatus.failed,
                Signal.intelligence_attempts < retry_limit,
            )
        )
    return (
        select(Signal)
        .join(SignalExtraction, SignalExtraction.signal_id == Signal.id)
        .where(
            Signal.status == ProcessingStatus.succeeded,
            Signal.is_duplicate.is_(False),
            Signal.intelligence_attempts < retry_limit,
            or_(*states),
        )
        .order_by(Signal.processed_at)
        .limit(limit)
    )


async def intelligence_metrics(session: AsyncSession) -> dict[str, int]:
    async def count(statement) -> int:
        return int((await session.scalar(statement)) or 0)

    return {
        "entities": await count(select(func.count()).select_from(KnowledgeEntity)),
        "relationships": await count(select(func.count()).select_from(EntityEdge)),
        "clusters": await count(select(func.count()).select_from(EvidenceCluster)),
        "pain_clusters": await count(
            select(func.count())
            .select_from(EvidenceCluster)
            .where(EvidenceCluster.cluster_type == ClusterType.pain)
        ),
        "workflow_clusters": await count(
            select(func.count())
            .select_from(EvidenceCluster)
            .where(EvidenceCluster.cluster_type == ClusterType.workflow)
        ),
        "change_clusters": await count(
            select(func.count())
            .select_from(EvidenceCluster)
            .where(EvidenceCluster.cluster_type == ClusterType.change)
        ),
        "clustered_signals": await count(
            select(func.count(distinct(ClusterMembership.signal_id))).select_from(ClusterMembership)
        ),
        "corroborated_clusters": await count(
            select(func.count())
            .select_from(EvidenceCluster)
            .where(
                EvidenceCluster.source_count >= 2,
                EvidenceCluster.evidence_type_count >= 2,
            )
        ),
    }
