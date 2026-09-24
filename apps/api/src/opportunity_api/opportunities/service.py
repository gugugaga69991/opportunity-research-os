import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, distinct, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.config import Settings
from opportunity_api.models import (
    ClusterEntity,
    ClusterLinkRole,
    ClusterMembership,
    ClusterStatus,
    ClusterType,
    EvidenceCluster,
    EvidenceStance,
    HypothesisReadiness,
    HypothesisTrack,
    OpportunityClusterLink,
    OpportunityEvidence,
    OpportunityHypothesis,
    OpportunityStatus,
    OpportunityTransition,
    RawDocument,
    Signal,
    SignalEntity,
    SignalExtraction,
    Source,
)
from opportunity_api.opportunities.generator import build_hypothesis_fields, evaluate_gate

GENERATION_VERSION = "1.0.0"
ALLOWED_TRANSITIONS: dict[OpportunityStatus, set[OpportunityStatus]] = {
    OpportunityStatus.raw: {
        OpportunityStatus.clustered,
        OpportunityStatus.watchlist,
        OpportunityStatus.killed,
    },
    OpportunityStatus.clustered: {
        OpportunityStatus.screened,
        OpportunityStatus.watchlist,
        OpportunityStatus.killed,
    },
    OpportunityStatus.screened: {
        OpportunityStatus.researching,
        OpportunityStatus.watchlist,
        OpportunityStatus.killed,
    },
    OpportunityStatus.researching: {
        OpportunityStatus.thesis_ready,
        OpportunityStatus.watchlist,
        OpportunityStatus.killed,
    },
    OpportunityStatus.thesis_ready: {
        OpportunityStatus.validating,
        OpportunityStatus.watchlist,
        OpportunityStatus.killed,
    },
    OpportunityStatus.validating: {
        OpportunityStatus.pilot,
        OpportunityStatus.prototype,
        OpportunityStatus.watchlist,
        OpportunityStatus.killed,
    },
    OpportunityStatus.pilot: {
        OpportunityStatus.prototype,
        OpportunityStatus.build,
        OpportunityStatus.watchlist,
        OpportunityStatus.killed,
    },
    OpportunityStatus.prototype: {
        OpportunityStatus.build,
        OpportunityStatus.watchlist,
        OpportunityStatus.killed,
    },
    OpportunityStatus.watchlist: {
        OpportunityStatus.clustered,
        OpportunityStatus.screened,
        OpportunityStatus.researching,
        OpportunityStatus.killed,
    },
    OpportunityStatus.killed: {OpportunityStatus.watchlist},
    OpportunityStatus.build: set(),
}


def can_transition(current: OpportunityStatus, target: OpportunityStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


async def _related_clusters(
    session: AsyncSession, origin: EvidenceCluster
) -> list[tuple[EvidenceCluster, int]]:
    entity_ids = list(
        (
            await session.scalars(
                select(ClusterEntity.entity_id).where(ClusterEntity.cluster_id == origin.id)
            )
        ).all()
    )
    if not entity_ids:
        return []
    shared_count = func.count(distinct(ClusterEntity.entity_id))
    return list(
        (
            await session.execute(
                select(EvidenceCluster, shared_count.label("shared_count"))
                .join(ClusterEntity, ClusterEntity.cluster_id == EvidenceCluster.id)
                .where(
                    EvidenceCluster.id != origin.id,
                    EvidenceCluster.status == ClusterStatus.active,
                    ClusterEntity.entity_id.in_(entity_ids),
                )
                .group_by(EvidenceCluster.id)
                .having(shared_count >= 2)
                .order_by(shared_count.desc(), EvidenceCluster.corroboration_score.desc())
                .limit(12)
            )
        ).all()
    )


async def _evidence_records(session: AsyncSession, cluster_ids: list[uuid.UUID]) -> list[dict]:
    if not cluster_ids:
        return []
    rows = (
        await session.execute(
            select(Signal, SignalExtraction, RawDocument, Source, ClusterMembership.cluster_id)
            .join(ClusterMembership, ClusterMembership.signal_id == Signal.id)
            .join(SignalExtraction, SignalExtraction.signal_id == Signal.id)
            .join(RawDocument, RawDocument.id == Signal.raw_document_id)
            .join(Source, Source.id == RawDocument.source_id)
            .where(ClusterMembership.cluster_id.in_(cluster_ids))
            .order_by(SignalExtraction.confidence.desc())
        )
    ).all()
    records: dict[uuid.UUID, dict] = {}
    for signal, extraction, document, source, cluster_id in rows:
        if signal.id not in records:
            records[signal.id] = {
                **extraction.ontology,
                "_signal": signal,
                "_extraction": extraction,
                "_document": document,
                "_source": source,
                "_cluster_id": cluster_id,
            }
    return list(records.values())


async def _contradiction_records(
    session: AsyncSession,
    origin: EvidenceCluster,
    excluding_signal_ids: set[uuid.UUID],
) -> list[dict]:
    entity_ids = list(
        (
            await session.scalars(
                select(ClusterEntity.entity_id).where(ClusterEntity.cluster_id == origin.id)
            )
        ).all()
    )
    if not entity_ids:
        return []
    candidate_ids = list(
        (
            await session.scalars(
                select(SignalEntity.signal_id)
                .join(SignalExtraction, SignalExtraction.signal_id == SignalEntity.signal_id)
                .where(
                    SignalEntity.entity_id.in_(entity_ids),
                    SignalExtraction.is_pain.is_(False),
                    SignalEntity.signal_id.not_in(excluding_signal_ids),
                )
                .group_by(SignalEntity.signal_id)
                .having(func.count(distinct(SignalEntity.entity_id)) >= 2)
                .limit(50)
            )
        ).all()
    )
    if not candidate_ids:
        return []
    rows = (
        await session.execute(
            select(Signal, SignalExtraction, RawDocument, Source)
            .join(SignalExtraction, SignalExtraction.signal_id == Signal.id)
            .join(RawDocument, RawDocument.id == Signal.raw_document_id)
            .join(Source, Source.id == RawDocument.source_id)
            .where(Signal.id.in_(candidate_ids))
        )
    ).all()
    return [
        {
            **extraction.ontology,
            "_signal": signal,
            "_extraction": extraction,
            "_document": document,
            "_source": source,
            "_cluster_id": None,
        }
        for signal, extraction, document, source in rows
    ]


async def _upsert_cluster_link(
    session: AsyncSession,
    opportunity: OpportunityHypothesis,
    cluster: EvidenceCluster,
    role: ClusterLinkRole,
    shared_entity_count: int,
) -> OpportunityClusterLink:
    link = await session.scalar(
        select(OpportunityClusterLink).where(
            OpportunityClusterLink.opportunity_id == opportunity.id,
            OpportunityClusterLink.cluster_id == cluster.id,
            OpportunityClusterLink.role == role,
        )
    )
    confidence = min(1.0, cluster.corroboration_score + min(shared_entity_count * 0.08, 0.3))
    seen_at = datetime.now(UTC)
    if link is None:
        link = OpportunityClusterLink(
            opportunity_id=opportunity.id,
            cluster_id=cluster.id,
            role=role,
            shared_entity_count=shared_entity_count,
            confidence=confidence,
            active=True,
            last_seen_at=seen_at,
        )
        session.add(link)
    else:
        link.shared_entity_count = shared_entity_count
        link.confidence = confidence
        link.active = True
        link.last_seen_at = seen_at
    return link


async def _upsert_evidence(
    session: AsyncSession,
    opportunity: OpportunityHypothesis,
    record: dict,
    stance: EvidenceStance,
) -> OpportunityEvidence:
    signal: Signal = record["_signal"]
    extraction: SignalExtraction = record["_extraction"]
    document: RawDocument = record["_document"]
    source: Source = record["_source"]
    evidence = await session.scalar(
        select(OpportunityEvidence).where(
            OpportunityEvidence.opportunity_id == opportunity.id,
            OpportunityEvidence.signal_id == signal.id,
            OpportunityEvidence.stance == stance,
        )
    )
    values = {
        "cluster_id": record.get("_cluster_id"),
        "evidence_type": source.source_type,
        "claim": record.get("summary") or signal.normalized_title,
        "confidence": extraction.confidence,
        "active": True,
        "last_seen_at": datetime.now(UTC),
        "metadata_": {
            "source_url": document.canonical_url,
            "published_at": document.published_at.isoformat() if document.published_at else None,
            "verified_evidence_spans": sum(
                bool(span.get("verified")) for span in extraction.evidence_spans
            ),
        },
    }
    if evidence is None:
        evidence = OpportunityEvidence(
            opportunity_id=opportunity.id,
            signal_id=signal.id,
            stance=stance,
            **values,
        )
        session.add(evidence)
    else:
        for field, value in values.items():
            setattr(evidence, field, value)
    return evidence


async def _record_transition(
    session: AsyncSession,
    opportunity: OpportunityHypothesis,
    from_status: OpportunityStatus | None,
    to_status: OpportunityStatus,
    reason: str,
    *,
    actor: str = "system",
) -> None:
    session.add(
        OpportunityTransition(
            opportunity_id=opportunity.id,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            reason=reason,
            metadata_={},
        )
    )


async def generate_hypothesis(
    session: AsyncSession, cluster_id: uuid.UUID, settings: Settings
) -> OpportunityHypothesis:
    origin = await session.get(EvidenceCluster, cluster_id)
    if origin is None:
        raise LookupError(f"Evidence cluster {cluster_id} does not exist")
    if origin.cluster_type not in {ClusterType.pain, ClusterType.change}:
        raise ValueError("Only pain and change clusters can originate opportunity hypotheses")
    if origin.status != ClusterStatus.active:
        raise ValueError("Only active clusters can originate opportunity hypotheses")
    lock_key = int.from_bytes(cluster_id.bytes[:8], byteorder="big", signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(lock_key)))
    track = (
        HypothesisTrack.pain_led
        if origin.cluster_type == ClusterType.pain
        else HypothesisTrack.change_led
    )
    hypothesis_key = hashlib.sha256(f"{track.value}:{origin.cluster_key}".encode()).hexdigest()
    opportunity = await session.scalar(
        select(OpportunityHypothesis).where(OpportunityHypothesis.origin_cluster_id == origin.id)
    )
    created = opportunity is None
    if opportunity is None:
        opportunity = OpportunityHypothesis(
            hypothesis_key=hypothesis_key,
            origin_cluster_id=origin.id,
            track=track,
            status=OpportunityStatus.clustered,
            readiness=HypothesisReadiness.preliminary,
            name=origin.title,
            last_cluster_update_at=origin.updated_at,
            thesis={},
            genealogy={},
        )
        session.add(opportunity)
        await session.flush()
        await _record_transition(
            session,
            opportunity,
            None,
            OpportunityStatus.clustered,
            "Created from an evidence cluster; awaiting evidence gates.",
        )

    await session.execute(
        update(OpportunityClusterLink)
        .where(OpportunityClusterLink.opportunity_id == opportunity.id)
        .values(active=False)
    )
    await session.execute(
        update(OpportunityEvidence)
        .where(OpportunityEvidence.opportunity_id == opportunity.id)
        .values(active=False)
    )
    await _upsert_cluster_link(session, opportunity, origin, ClusterLinkRole.origin, 0)
    related = await _related_clusters(session, origin)
    support_clusters: list[EvidenceCluster] = [origin]
    has_confirming_pain_cluster = track == HypothesisTrack.pain_led
    related_genealogy: list[dict] = []
    for cluster, shared_count in related:
        if track == HypothesisTrack.change_led and cluster.cluster_type in {
            ClusterType.pain,
            ClusterType.workflow,
        }:
            role = ClusterLinkRole.supporting
            support_clusters.append(cluster)
            has_confirming_pain_cluster = (
                has_confirming_pain_cluster or cluster.cluster_type == ClusterType.pain
            )
        elif track == HypothesisTrack.pain_led and cluster.cluster_type == ClusterType.workflow:
            role = ClusterLinkRole.supporting
            support_clusters.append(cluster)
        else:
            role = ClusterLinkRole.context
        await _upsert_cluster_link(session, opportunity, cluster, role, shared_count)
        related_genealogy.append(
            {
                "cluster_id": str(cluster.id),
                "cluster_type": cluster.cluster_type,
                "role": role,
                "shared_entities": shared_count,
            }
        )

    support_ids = list(dict.fromkeys(cluster.id for cluster in support_clusters))
    records = await _evidence_records(session, support_ids)
    if not records:
        raise ValueError("Origin cluster has no usable evidence records")
    for record in records:
        await _upsert_evidence(session, opportunity, record, EvidenceStance.supporting)
    supporting_signal_ids = {record["_signal"].id for record in records}
    contradictions = (
        await _contradiction_records(session, origin, supporting_signal_ids)
        if track == HypothesisTrack.pain_led
        else []
    )
    for record in contradictions:
        await _upsert_evidence(session, opportunity, record, EvidenceStance.contradicting)

    ontology_records = [
        {key: value for key, value in record.items() if not key.startswith("_")}
        for record in records
    ]
    fields = build_hypothesis_fields(track, origin.title, origin.summary, ontology_records)
    sources = {record["_source"].id for record in records}
    evidence_types = {record["_source"].source_type for record in records}
    average_confidence = sum(record["_extraction"].confidence for record in records) / len(records)
    recurrence_score = max(
        [origin.recurrence_score, *(cluster.recurrence_score for cluster in support_clusters)]
    )
    gate = evaluate_gate(
        track=track,
        signal_count=len(records),
        source_count=len(sources),
        evidence_type_count=len(evidence_types),
        recurrence_score=recurrence_score,
        buyer_identified=bool(fields["buyer_role"]),
        economic_evidence_present=bool(fields["economic_cost"] or fields["existing_spend"]),
        corroboration_score=max(cluster.corroboration_score for cluster in support_clusters),
        average_extraction_confidence=average_confidence,
        contradiction_count=len(contradictions),
        has_confirming_pain_cluster=has_confirming_pain_cluster,
        minimum_signals=settings.hypothesis_min_signal_count,
        minimum_sources=settings.hypothesis_min_sources,
        minimum_evidence_types=settings.hypothesis_min_evidence_types,
        minimum_recurrence=settings.hypothesis_min_recurrence,
    )
    editable = created or opportunity.status in {
        OpportunityStatus.raw,
        OpportunityStatus.clustered,
        OpportunityStatus.screened,
    }
    if editable:
        for field in (
            "name",
            "industry",
            "icp",
            "user_role",
            "buyer_role",
            "core_workflow",
            "problem",
            "frequency",
            "current_workaround",
            "economic_cost",
            "existing_spend",
            "why_now",
            "desired_outcome",
            "solution_concept",
            "value_proposition",
            "thesis",
        ):
            setattr(opportunity, field, fields[field])
    opportunity.readiness = gate.readiness
    opportunity.confidence = gate.confidence
    opportunity.confirming_signal_count = len(records)
    opportunity.confirming_source_count = len(sources)
    opportunity.evidence_type_count = len(evidence_types)
    opportunity.contradiction_count = len(contradictions)
    opportunity.buyer_identified = bool(fields["buyer_role"])
    opportunity.recurring_problem = recurrence_score >= settings.hypothesis_min_recurrence
    opportunity.evidence_gate_passed = gate.passed
    opportunity.generation_version = GENERATION_VERSION
    opportunity.last_cluster_update_at = max(cluster.updated_at for cluster in support_clusters)
    opportunity.genealogy = {
        "origin_cluster_id": str(origin.id),
        "track": track,
        "gate_checks": gate.checks,
        "source_types": sorted(evidence_types),
        "supporting_signal_ids": sorted(map(str, supporting_signal_ids)),
        "contradicting_signal_ids": sorted(str(record["_signal"].id) for record in contradictions),
        "related_clusters": related_genealogy,
    }
    if gate.passed and opportunity.status in {
        OpportunityStatus.raw,
        OpportunityStatus.clustered,
    }:
        previous = opportunity.status
        opportunity.status = OpportunityStatus.screened
        opportunity.promoted_at = datetime.now(UTC)
        await _record_transition(
            session,
            opportunity,
            previous,
            OpportunityStatus.screened,
            "Passed recurrence, buyer, source-diversity, and evidence-diversity gates.",
        )
    await session.commit()
    await session.refresh(opportunity)
    return opportunity


async def transition_opportunity(
    session: AsyncSession,
    opportunity: OpportunityHypothesis,
    target: OpportunityStatus,
    reason: str,
    actor: str,
) -> OpportunityHypothesis:
    if target == opportunity.status:
        return opportunity
    if not can_transition(opportunity.status, target):
        raise ValueError(f"Cannot transition from {opportunity.status} to {target}")
    if target in {OpportunityStatus.screened, OpportunityStatus.researching} and not (
        opportunity.evidence_gate_passed
    ):
        raise ValueError("Opportunity has not passed the evidence gate")
    previous = opportunity.status
    opportunity.status = target
    await _record_transition(session, opportunity, previous, target, reason, actor=actor)
    await session.commit()
    await session.refresh(opportunity)
    return opportunity


def pending_hypothesis_clusters_query(limit: int) -> Select[tuple[EvidenceCluster]]:
    stale = datetime.now(UTC) - timedelta(hours=6)
    return (
        select(EvidenceCluster)
        .outerjoin(
            OpportunityHypothesis,
            OpportunityHypothesis.origin_cluster_id == EvidenceCluster.id,
        )
        .where(
            EvidenceCluster.status == ClusterStatus.active,
            EvidenceCluster.cluster_type.in_([ClusterType.pain, ClusterType.change]),
            or_(
                OpportunityHypothesis.id.is_(None),
                OpportunityHypothesis.last_cluster_update_at < EvidenceCluster.updated_at,
                OpportunityHypothesis.updated_at < stale,
            ),
        )
        .order_by(EvidenceCluster.corroboration_score.desc())
        .limit(limit)
    )


async def opportunity_metrics(session: AsyncSession) -> dict[str, int]:
    async def count(statement) -> int:
        return int((await session.scalar(statement)) or 0)

    return {
        "total": await count(select(func.count()).select_from(OpportunityHypothesis)),
        "preliminary": await count(
            select(func.count())
            .select_from(OpportunityHypothesis)
            .where(OpportunityHypothesis.readiness == HypothesisReadiness.preliminary)
        ),
        "corroborating": await count(
            select(func.count())
            .select_from(OpportunityHypothesis)
            .where(OpportunityHypothesis.readiness == HypothesisReadiness.corroborating)
        ),
        "research_ready": await count(
            select(func.count())
            .select_from(OpportunityHypothesis)
            .where(OpportunityHypothesis.readiness == HypothesisReadiness.research_ready)
        ),
        "pain_led": await count(
            select(func.count())
            .select_from(OpportunityHypothesis)
            .where(OpportunityHypothesis.track == HypothesisTrack.pain_led)
        ),
        "change_led": await count(
            select(func.count())
            .select_from(OpportunityHypothesis)
            .where(OpportunityHypothesis.track == HypothesisTrack.change_led)
        ),
        "evidence_gated": await count(
            select(func.count())
            .select_from(OpportunityHypothesis)
            .where(OpportunityHypothesis.evidence_gate_passed.is_(True))
        ),
        "with_contradictions": await count(
            select(func.count())
            .select_from(OpportunityHypothesis)
            .where(OpportunityHypothesis.contradiction_count > 0)
        ),
    }
