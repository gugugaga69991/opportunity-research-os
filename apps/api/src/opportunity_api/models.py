import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class AccessRisk(StrEnum):
    approved = "approved"
    review_required = "review_required"
    restricted = "restricted"


class TriggerType(StrEnum):
    manual = "manual"
    schedule = "schedule"
    webhook = "webhook"


class ProcessingStatus(StrEnum):
    queued = "queued"
    running = "running"
    awaiting_model = "awaiting_model"
    succeeded = "succeeded"
    failed = "failed"


class DuplicateKind(StrEnum):
    exact = "exact"
    near = "near"
    semantic = "semantic"


class EntityType(StrEnum):
    industry = "industry"
    subindustry = "subindustry"
    company_type = "company_type"
    company_size = "company_size"
    company = "company"
    role = "role"
    trigger = "trigger"
    task = "task"
    pain_type = "pain_type"
    tool = "tool"
    software = "software"
    input = "input"
    output = "output"
    workflow_step = "workflow_step"
    workaround = "workaround"
    recurrence = "recurrence"
    desired_outcome = "desired_outcome"


class ClusterType(StrEnum):
    pain = "pain"
    workflow = "workflow"
    change = "change"


class ClusterStatus(StrEnum):
    active = "active"
    merged = "merged"
    archived = "archived"


class MembershipMethod(StrEnum):
    fingerprint = "fingerprint"
    semantic = "semantic"
    hybrid = "hybrid"


class HypothesisTrack(StrEnum):
    pain_led = "pain_led"
    change_led = "change_led"


class OpportunityStatus(StrEnum):
    raw = "raw"
    clustered = "clustered"
    screened = "screened"
    researching = "researching"
    thesis_ready = "thesis_ready"
    validating = "validating"
    pilot = "pilot"
    prototype = "prototype"
    build = "build"
    killed = "killed"
    watchlist = "watchlist"


class HypothesisReadiness(StrEnum):
    preliminary = "preliminary"
    corroborating = "corroborating"
    research_ready = "research_ready"


class EvidenceStance(StrEnum):
    supporting = "supporting"
    contradicting = "contradicting"
    context = "context"


class ClusterLinkRole(StrEnum):
    origin = "origin"
    supporting = "supporting"
    context = "context"
    contradicting = "contradicting"


class ResearchStatus(StrEnum):
    planned = "planned"
    awaiting_configuration = "awaiting_configuration"
    queued = "queued"
    running = "running"
    collecting = "collecting"
    awaiting_analysis = "awaiting_analysis"
    analyzing = "analyzing"
    completed = "completed"
    failed = "failed"
    blocked = "blocked"


class ResearchLane(StrEnum):
    competition = "competition"
    economics = "economics"
    market = "market"
    distribution = "distribution"
    contradiction = "contradiction"


class FindingStance(StrEnum):
    supporting = "supporting"
    contradicting = "contradicting"
    neutral = "neutral"


class DecisionStatus(StrEnum):
    awaiting_analysis = "awaiting_analysis"
    analyzing = "analyzing"
    completed = "completed"
    failed = "failed"


class DecisionDisposition(StrEnum):
    advance = "advance"
    watchlist = "watchlist"
    kill = "kill"


class RiskSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    fatal = "fatal"


class ScoreDimension(StrEnum):
    pain_severity = "pain_severity"
    recurring_frequency = "recurring_frequency"
    existing_spend = "existing_spend"
    willingness_to_pay = "willingness_to_pay"
    competition_weakness = "competition_weakness"
    distribution_quality = "distribution_quality"
    retention = "retention"
    buildability = "buildability"
    time_to_value = "time_to_value"
    ai_advantage = "ai_advantage"
    defensibility = "defensibility"
    market_timing = "market_timing"
    reachable_tam = "reachable_tam"
    expansion = "expansion"


class ValidationStatus(StrEnum):
    planned = "planned"
    running = "running"
    completed = "completed"
    failed = "failed"


class ValidationVerdict(StrEnum):
    pending = "pending"
    strong = "strong"
    mixed = "mixed"
    weak = "weak"
    invalidated = "invalidated"


class ExperimentType(StrEnum):
    pain_interview = "pain_interview"
    cold_email = "cold_email"
    pricing = "pricing"
    paid_commitment = "paid_commitment"


class ExperimentStatus(StrEnum):
    planned = "planned"
    ready = "ready"
    running = "running"
    completed = "completed"
    cancelled = "cancelled"


class OutcomeEventType(StrEnum):
    outreach_positive = "outreach_positive"
    demo_booked = "demo_booked"
    pricing_accepted = "pricing_accepted"
    loi_signed = "loi_signed"
    pilot_paid = "pilot_paid"
    customer_activated = "customer_activated"
    customer_retained = "customer_retained"
    customer_churned = "customer_churned"
    mrr_observed = "mrr_observed"


class CalibrationStatus(StrEnum):
    insufficient_data = "insufficient_data"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"


class FreshnessStatus(StrEnum):
    current = "current"
    due = "due"
    refreshing = "refreshing"
    changed = "changed"
    failed = "failed"


class PortfolioState(StrEnum):
    improving = "improving"
    stable = "stable"
    deteriorating = "deteriorating"
    saturating = "saturating"
    invalidated = "invalidated"


class AlertStatus(StrEnum):
    unread = "unread"
    read = "read"
    archived = "archived"


class BuildSpecStatus(StrEnum):
    draft = "draft"
    approved = "approved"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Source(TimestampMixin, Base):
    __tablename__ = "sources"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(80), index=True)
    access_method: Mapped[str] = mapped_column(String(80))
    adapter_key: Mapped[str] = mapped_column(String(80), default="generic_apify")
    actor_id: Mapped[str | None] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reliability_weight: Mapped[float] = mapped_column(Float, default=0.5)
    access_risk: Mapped[AccessRisk] = mapped_column(
        Enum(AccessRisk), default=AccessRisk.review_required, index=True
    )
    collector_config: Mapped[dict] = mapped_column(JSON, default=dict)
    access_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class CollectionRun(TimestampMixin, Base):
    __tablename__ = "collection_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    external_run_id: Mapped[str | None] = mapped_column(String(200))
    external_dataset_id: Mapped[str | None] = mapped_column(String(200))
    trigger_type: Mapped[TriggerType] = mapped_column(Enum(TriggerType), default=TriggerType.manual)
    actor_input: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.queued)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_received: Mapped[int] = mapped_column(Integer, default=0)
    items_ingested: Mapped[int] = mapped_column(Integer, default=0)
    items_skipped: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    source: Mapped[Source] = relationship()


class RawDocument(TimestampMixin, Base):
    __tablename__ = "raw_documents"
    __table_args__ = (
        UniqueConstraint("source_id", "content_hash", name="uq_raw_document_source_hash"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection_runs.id"), index=True
    )
    source_external_id: Mapped[str | None] = mapped_column(String(240), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str | None] = mapped_column(String(240))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    language: Mapped[str | None] = mapped_column(String(16))
    raw_text: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[Source] = relationship()
    collection_run: Mapped[CollectionRun] = relationship()


class Signal(TimestampMixin, Base):
    __tablename__ = "signals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("raw_documents.id"), unique=True, index=True
    )
    canonical_signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signals.id"), index=True
    )
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus), default=ProcessingStatus.queued, index=True
    )
    normalized_title: Mapped[str] = mapped_column(Text, default="")
    normalized_text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), default="und", index=True)
    exact_hash: Mapped[str] = mapped_column(String(64), index=True)
    simhash: Mapped[str] = mapped_column(String(16), index=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    duplicate_kind: Mapped[DuplicateKind | None] = mapped_column(Enum(DuplicateKind))
    duplicate_score: Mapped[float | None] = mapped_column(Float)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(String(160))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    intelligence_status: Mapped[ProcessingStatus | None] = mapped_column(
        Enum(ProcessingStatus), index=True
    )
    intelligence_processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    intelligence_error: Mapped[str | None] = mapped_column(Text)
    intelligence_attempts: Mapped[int] = mapped_column(Integer, default=0)
    raw_document: Mapped[RawDocument] = relationship()
    canonical_signal: Mapped["Signal | None"] = relationship(remote_side="Signal.id")


class SignalExtraction(TimestampMixin, Base):
    __tablename__ = "signal_extractions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), unique=True, index=True)
    model_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_runs.id"), index=True)
    is_pain: Mapped[bool] = mapped_column(Boolean, index=True)
    pain_probability: Mapped[float] = mapped_column(Float, index=True)
    confidence: Mapped[float] = mapped_column(Float, index=True)
    industry: Mapped[str] = mapped_column(String(160), default="", index=True)
    user_role: Mapped[str] = mapped_column(String(160), default="", index=True)
    buyer_role: Mapped[str] = mapped_column(String(160), default="")
    recurrence: Mapped[str] = mapped_column(String(80), default="", index=True)
    urgency: Mapped[str] = mapped_column(String(80), default="", index=True)
    ontology: Mapped[dict] = mapped_column(JSON)
    evidence_spans: Mapped[list] = mapped_column(JSON)
    signal: Mapped[Signal] = relationship()
    model_run: Mapped["ModelRun"] = relationship()


class KnowledgeEntity(TimestampMixin, Base):
    __tablename__ = "knowledge_entities"
    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_value", name="uq_entity_type_value"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType), index=True)
    display_value: Mapped[str] = mapped_column(String(300))
    normalized_value: Mapped[str] = mapped_column(String(240), index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class SignalEntity(TimestampMixin, Base):
    __tablename__ = "signal_entities"
    __table_args__ = (
        UniqueConstraint("signal_id", "entity_id", "relation", name="uq_signal_entity_relation"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_entities.id"), index=True)
    relation: Mapped[str] = mapped_column(String(80), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    signal: Mapped[Signal] = relationship()
    entity: Mapped[KnowledgeEntity] = relationship()


class EntityEdge(TimestampMixin, Base):
    __tablename__ = "entity_edges"
    __table_args__ = (
        UniqueConstraint("source_entity_id", "target_entity_id", "relation", name="uq_entity_edge"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_entities.id"), index=True
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_entities.id"), index=True
    )
    relation: Mapped[str] = mapped_column(String(80), default="co_occurs", index=True)
    support_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    supporting_signal_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_entity: Mapped[KnowledgeEntity] = relationship(foreign_keys=[source_entity_id])
    target_entity: Mapped[KnowledgeEntity] = relationship(foreign_keys=[target_entity_id])


class EvidenceCluster(TimestampMixin, Base):
    __tablename__ = "evidence_clusters"
    __table_args__ = (UniqueConstraint("cluster_type", "cluster_key", name="uq_cluster_type_key"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_type: Mapped[ClusterType] = mapped_column(Enum(ClusterType), index=True)
    cluster_key: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ClusterStatus] = mapped_column(
        Enum(ClusterStatus), default=ClusterStatus.active, index=True
    )
    centroid: Mapped[list[float] | None] = mapped_column(Vector(1536))
    centroid_count: Mapped[int] = mapped_column(Integer, default=0)
    signal_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    evidence_type_count: Mapped[int] = mapped_column(Integer, default=0)
    corroboration_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    recurrence_score: Mapped[float] = mapped_column(Float, default=0.0)
    velocity_30d: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class ClusterMembership(TimestampMixin, Base):
    __tablename__ = "cluster_memberships"
    __table_args__ = (UniqueConstraint("cluster_id", "signal_id", name="uq_cluster_signal"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_clusters.id"), index=True)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), index=True)
    similarity: Mapped[float] = mapped_column(Float, default=1.0)
    method: Mapped[MembershipMethod] = mapped_column(Enum(MembershipMethod), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    cluster: Mapped[EvidenceCluster] = relationship()
    signal: Mapped[Signal] = relationship()


class ClusterEntity(TimestampMixin, Base):
    __tablename__ = "cluster_entities"
    __table_args__ = (
        UniqueConstraint("cluster_id", "entity_id", "relation", name="uq_cluster_entity"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_clusters.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_entities.id"), index=True)
    relation: Mapped[str] = mapped_column(String(80), default="contains", index=True)
    support_count: Mapped[int] = mapped_column(Integer, default=1)
    cluster: Mapped[EvidenceCluster] = relationship()
    entity: Mapped[KnowledgeEntity] = relationship()


class OpportunityHypothesis(TimestampMixin, Base):
    __tablename__ = "opportunity_hypotheses"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hypothesis_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    origin_cluster_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_clusters.id"), unique=True, index=True
    )
    track: Mapped[HypothesisTrack] = mapped_column(Enum(HypothesisTrack), index=True)
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus), default=OpportunityStatus.clustered, index=True
    )
    readiness: Mapped[HypothesisReadiness] = mapped_column(
        Enum(HypothesisReadiness), default=HypothesisReadiness.preliminary, index=True
    )
    name: Mapped[str] = mapped_column(String(300), index=True)
    industry: Mapped[str] = mapped_column(String(160), default="", index=True)
    icp: Mapped[str] = mapped_column(Text, default="")
    user_role: Mapped[str] = mapped_column(String(160), default="", index=True)
    buyer_role: Mapped[str] = mapped_column(String(160), default="", index=True)
    core_workflow: Mapped[str] = mapped_column(Text, default="")
    problem: Mapped[str] = mapped_column(Text, default="")
    frequency: Mapped[str] = mapped_column(String(160), default="")
    current_workaround: Mapped[str] = mapped_column(Text, default="")
    economic_cost: Mapped[str] = mapped_column(Text, default="")
    existing_spend: Mapped[str] = mapped_column(Text, default="")
    why_now: Mapped[str] = mapped_column(Text, default="")
    desired_outcome: Mapped[str] = mapped_column(Text, default="")
    solution_concept: Mapped[str] = mapped_column(Text, default="")
    value_proposition: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    confirming_signal_count: Mapped[int] = mapped_column(Integer, default=0)
    confirming_source_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_type_count: Mapped[int] = mapped_column(Integer, default=0)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0)
    buyer_identified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    recurring_problem: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    evidence_gate_passed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    thesis: Mapped[dict] = mapped_column(JSON, default=dict)
    genealogy: Mapped[dict] = mapped_column(JSON, default=dict)
    generation_version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    last_cluster_update_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin_cluster: Mapped[EvidenceCluster] = relationship()


class OpportunityClusterLink(TimestampMixin, Base):
    __tablename__ = "opportunity_cluster_links"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "cluster_id", "role", name="uq_opportunity_cluster"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_clusters.id"), index=True)
    role: Mapped[ClusterLinkRole] = mapped_column(Enum(ClusterLinkRole), index=True)
    shared_entity_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    opportunity: Mapped[OpportunityHypothesis] = relationship()
    cluster: Mapped[EvidenceCluster] = relationship()


class OpportunityEvidence(TimestampMixin, Base):
    __tablename__ = "opportunity_evidence"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "signal_id", "stance", name="uq_opportunity_signal_stance"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), index=True)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_clusters.id"), index=True
    )
    stance: Mapped[EvidenceStance] = mapped_column(Enum(EvidenceStance), index=True)
    evidence_type: Mapped[str] = mapped_column(String(120), index=True)
    claim: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    opportunity: Mapped[OpportunityHypothesis] = relationship()
    signal: Mapped[Signal] = relationship()


class OpportunityTransition(TimestampMixin, Base):
    __tablename__ = "opportunity_transitions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    from_status: Mapped[OpportunityStatus | None] = mapped_column(Enum(OpportunityStatus))
    to_status: Mapped[OpportunityStatus] = mapped_column(Enum(OpportunityStatus), index=True)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    reason: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    opportunity: Mapped[OpportunityHypothesis] = relationship()


class ResearchCampaign(TimestampMixin, Base):
    __tablename__ = "research_campaigns"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "version", name="uq_research_campaign_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    campaign_type: Mapped[str] = mapped_column(String(40), default="baseline", index=True)
    supersedes_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_campaigns.id"), index=True
    )
    status: Mapped[ResearchStatus] = mapped_column(
        Enum(ResearchStatus), default=ResearchStatus.planned, index=True
    )
    required_lane_count: Mapped[int] = mapped_column(Integer, default=5)
    completed_lane_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    failed_lane_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    opportunity: Mapped[OpportunityHypothesis] = relationship()


class ResearchTask(TimestampMixin, Base):
    __tablename__ = "research_tasks"
    __table_args__ = (UniqueConstraint("campaign_id", "lane", name="uq_research_campaign_lane"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_campaigns.id"), index=True)
    lane: Mapped[ResearchLane] = mapped_column(Enum(ResearchLane), index=True)
    status: Mapped[ResearchStatus] = mapped_column(
        Enum(ResearchStatus), default=ResearchStatus.planned, index=True
    )
    required: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    research_queries: Mapped[list] = mapped_column(JSON, default=list)
    actor_input: Mapped[dict] = mapped_column(JSON, default=dict)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_runs.id"), index=True
    )
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_runs.id"), index=True)
    documents_found: Mapped[int] = mapped_column(Integer, default=0)
    coverage_score: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    campaign: Mapped[ResearchCampaign] = relationship()
    collection_run: Mapped[CollectionRun | None] = relationship()
    model_run: Mapped["ModelRun | None"] = relationship()


class ResearchTarget(TimestampMixin, Base):
    __tablename__ = "research_targets"
    __table_args__ = (UniqueConstraint("task_id", "target_key", name="uq_research_task_target"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_tasks.id"), index=True)
    target_key: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(80), default="search_query", index=True)
    value: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ResearchStatus] = mapped_column(
        Enum(ResearchStatus), default=ResearchStatus.planned, index=True
    )
    task: Mapped[ResearchTask] = relationship()


class ResearchFinding(TimestampMixin, Base):
    __tablename__ = "research_findings"
    __table_args__ = (UniqueConstraint("task_id", "finding_key", name="uq_research_task_finding"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_campaigns.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_tasks.id"), index=True)
    lane: Mapped[ResearchLane] = mapped_column(Enum(ResearchLane), index=True)
    finding_key: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    stance: Mapped[FindingStance] = mapped_column(Enum(FindingStance), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    structured_data: Mapped[dict] = mapped_column(JSON)
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    document_ids: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    task: Mapped[ResearchTask] = relationship()


class CompetitorProfile(TimestampMixin, Base):
    __tablename__ = "competitor_profiles"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "normalized_name", name="uq_opportunity_competitor_name"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_findings.id"), index=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    normalized_name: Mapped[str] = mapped_column(String(240), index=True)
    website: Mapped[str] = mapped_column(Text, default="")
    positioning: Mapped[str] = mapped_column(Text, default="")
    icp: Mapped[str] = mapped_column(Text, default="")
    pricing: Mapped[str] = mapped_column(Text, default="")
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    weaknesses: Mapped[list] = mapped_column(JSON, default=list)
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class OpportunityDecision(TimestampMixin, Base):
    __tablename__ = "opportunity_decisions"
    __table_args__ = (
        UniqueConstraint("campaign_id", "version", name="uq_campaign_decision_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_campaigns.id"), index=True)
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_runs.id"), index=True)
    version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    status: Mapped[DecisionStatus] = mapped_column(
        Enum(DecisionStatus), default=DecisionStatus.awaiting_analysis, index=True
    )
    disposition: Mapped[DecisionDisposition | None] = mapped_column(
        Enum(DecisionDisposition), index=True
    )
    raw_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    adjusted_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    research_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    hard_kill_triggered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    penalties: Mapped[dict] = mapped_column(JSON, default=dict)
    hard_kills: Mapped[list] = mapped_column(JSON, default=list)
    thesis: Mapped[dict] = mapped_column(JSON, default=dict)
    red_team: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    opportunity: Mapped[OpportunityHypothesis] = relationship()
    campaign: Mapped[ResearchCampaign] = relationship()
    model_run: Mapped["ModelRun | None"] = relationship()


class OpportunityScore(TimestampMixin, Base):
    __tablename__ = "opportunity_scores"
    __table_args__ = (
        UniqueConstraint("decision_id", "dimension", name="uq_decision_score_dimension"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_decisions.id"), index=True
    )
    dimension: Mapped[ScoreDimension] = mapped_column(Enum(ScoreDimension), index=True)
    score: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)
    weighted_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[OpportunityDecision] = relationship()


class OpportunityRisk(TimestampMixin, Base):
    __tablename__ = "opportunity_risks"
    __table_args__ = (UniqueConstraint("decision_id", "risk_key", name="uq_decision_risk"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_decisions.id"), index=True
    )
    risk_key: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    severity: Mapped[RiskSeverity] = mapped_column(Enum(RiskSeverity), index=True)
    claim: Mapped[str] = mapped_column(Text)
    implication: Mapped[str] = mapped_column(Text, default="")
    mitigation: Mapped[str] = mapped_column(Text, default="")
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    decision: Mapped[OpportunityDecision] = relationship()


class ValidationCampaign(TimestampMixin, Base):
    __tablename__ = "validation_campaigns"
    __table_args__ = (
        UniqueConstraint("decision_id", "version", name="uq_decision_validation_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    decision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_decisions.id"), index=True
    )
    version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus), default=ValidationStatus.planned, index=True
    )
    verdict: Mapped[ValidationVerdict] = mapped_column(
        Enum(ValidationVerdict), default=ValidationVerdict.pending, index=True
    )
    validation_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opportunity: Mapped[OpportunityHypothesis] = relationship()
    decision: Mapped[OpportunityDecision] = relationship()


class ValidationExperiment(TimestampMixin, Base):
    __tablename__ = "validation_experiments"
    __table_args__ = (
        UniqueConstraint("campaign_id", "experiment_type", name="uq_validation_experiment_type"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_campaigns.id"), index=True
    )
    experiment_type: Mapped[ExperimentType] = mapped_column(Enum(ExperimentType), index=True)
    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(ExperimentStatus), default=ExperimentStatus.planned, index=True
    )
    hypothesis: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(120), default="manual", index=True)
    positioning_angle: Mapped[str] = mapped_column(String(240), default="")
    price_point_usd: Mapped[float | None] = mapped_column(Float)
    sample_target: Mapped[int] = mapped_column(Integer, default=0)
    success_criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_brief: Mapped[dict] = mapped_column(JSON, default=dict)
    aggregate: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campaign: Mapped[ValidationCampaign] = relationship()


class ValidationResult(TimestampMixin, Base):
    __tablename__ = "validation_results"
    __table_args__ = (
        UniqueConstraint("experiment_id", "result_key", name="uq_experiment_result_key"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_experiments.id"), index=True
    )
    result_key: Mapped[str] = mapped_column(String(160), index=True)
    source: Mapped[str] = mapped_column(String(120), default="manual", index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    qualitative_feedback: Mapped[list] = mapped_column(JSON, default=list)
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    interpretation: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    experiment: Mapped[ValidationExperiment] = relationship()


class FailureMemory(TimestampMixin, Base):
    __tablename__ = "failure_memories"
    __table_args__ = (
        UniqueConstraint("campaign_id", "reason_key", name="uq_validation_failure_reason"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_campaigns.id"), index=True
    )
    reason_key: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    reason: Mapped[str] = mapped_column(Text)
    predicted: Mapped[dict] = mapped_column(JSON, default=dict)
    actual: Mapped[dict] = mapped_column(JSON, default=dict)
    reusable_lesson: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    campaign: Mapped[ValidationCampaign] = relationship()


class BusinessOutcome(TimestampMixin, Base):
    __tablename__ = "business_outcomes"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "event_key", name="uq_opportunity_outcome_event"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_decisions.id"), index=True
    )
    event_key: Mapped[str] = mapped_column(String(160), index=True)
    event_type: Mapped[OutcomeEventType] = mapped_column(Enum(OutcomeEventType), index=True)
    source: Mapped[str] = mapped_column(String(120), default="manual", index=True)
    value_usd: Mapped[float | None] = mapped_column(Float)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_urls: Mapped[list] = mapped_column(JSON, default=list)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    opportunity: Mapped[OpportunityHypothesis] = relationship()
    decision: Mapped[OpportunityDecision | None] = relationship()


class CalibrationRun(TimestampMixin, Base):
    __tablename__ = "calibration_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[CalibrationStatus] = mapped_column(Enum(CalibrationStatus), index=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    baseline_weights: Mapped[dict] = mapped_column(JSON, default=dict)
    proposed_weights: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    approved_by: Mapped[str | None] = mapped_column(String(120))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScoringProfile(TimestampMixin, Base):
    __tablename__ = "scoring_profiles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    calibration_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calibration_runs.id"), index=True
    )
    version: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    weights: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    approved_by: Mapped[str] = mapped_column(String(120))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    calibration_run: Mapped[CalibrationRun | None] = relationship()


class FreshnessAssessment(TimestampMixin, Base):
    __tablename__ = "freshness_assessments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), unique=True, index=True
    )
    active_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_campaigns.id"), index=True
    )
    status: Mapped[FreshnessStatus] = mapped_column(
        Enum(FreshnessStatus), default=FreshnessStatus.current, index=True
    )
    freshness_score: Mapped[float] = mapped_column(Float, default=1.0, index=True)
    priority: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    last_researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    due_topics: Mapped[list] = mapped_column(JSON, default=list)
    detected_changes: Mapped[list] = mapped_column(JSON, default=list)
    requires_rescore: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    error: Mapped[str | None] = mapped_column(Text)
    opportunity: Mapped[OpportunityHypothesis] = relationship()
    active_campaign: Mapped[ResearchCampaign | None] = relationship()


class PortfolioSnapshot(TimestampMixin, Base):
    __tablename__ = "portfolio_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), unique=True, index=True
    )
    current_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    previous_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_velocity: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    competition_velocity: Mapped[float] = mapped_column(Float, default=0.0)
    pain_velocity: Mapped[float] = mapped_column(Float, default=0.0)
    market_timing_velocity: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int | None] = mapped_column(Integer, index=True)
    previous_rank: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[PortfolioState] = mapped_column(
        Enum(PortfolioState), default=PortfolioState.stable, index=True
    )
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    opportunity: Mapped[OpportunityHypothesis] = relationship()


class OperationalAlert(TimestampMixin, Base):
    __tablename__ = "operational_alerts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    alert_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus), default=AlertStatus.unread, index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    telegram_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_error: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opportunity: Mapped[OpportunityHypothesis | None] = relationship()


class CustomerInterview(TimestampMixin, Base):
    __tablename__ = "customer_interviews"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "interview_key", name="uq_opportunity_interview"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    interview_key: Mapped[str] = mapped_column(String(160), index=True)
    company: Mapped[str] = mapped_column(String(240), default="")
    industry: Mapped[str] = mapped_column(String(160), default="", index=True)
    company_size: Mapped[str] = mapped_column(String(120), default="")
    participant_role: Mapped[str] = mapped_column(String(160), default="", index=True)
    buyer_or_user: Mapped[str] = mapped_column(String(40), default="user")
    interviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    transcript: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text)
    current_workflow: Mapped[str] = mapped_column(Text, default="")
    tools_used: Mapped[list] = mapped_column(JSON, default=list)
    pain_frequency: Mapped[str] = mapped_column(String(120), default="")
    time_cost_hours: Mapped[float | None] = mapped_column(Float)
    financial_cost_usd: Mapped[float | None] = mapped_column(Float)
    current_spend_usd: Mapped[float | None] = mapped_column(Float)
    complaints: Mapped[list] = mapped_column(JSON, default=list)
    desired_outcome: Mapped[str] = mapped_column(Text, default="")
    urgency: Mapped[str] = mapped_column(String(80), default="")
    budget_signal: Mapped[str] = mapped_column(String(120), default="")
    price_reaction: Mapped[str] = mapped_column(String(120), default="")
    objections: Mapped[list] = mapped_column(JSON, default=list)
    quotes: Mapped[list] = mapped_column(JSON, default=list)
    follow_up: Mapped[str] = mapped_column(Text, default="")
    evidence_strength: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    opportunity: Mapped[OpportunityHypothesis] = relationship()


class BuildSpecification(TimestampMixin, Base):
    __tablename__ = "build_specifications"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "version", name="uq_opportunity_build_spec"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_hypotheses.id"), index=True
    )
    decision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_decisions.id"), index=True
    )
    validation_campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_campaigns.id"), index=True
    )
    version: Mapped[str] = mapped_column(String(40))
    status: Mapped[BuildSpecStatus] = mapped_column(
        Enum(BuildSpecStatus), default=BuildSpecStatus.draft, index=True
    )
    content: Mapped[dict] = mapped_column(JSON)
    markdown: Mapped[str] = mapped_column(Text)
    source_manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_by: Mapped[str | None] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opportunity: Mapped[OpportunityHypothesis] = relationship()
    decision: Mapped[OpportunityDecision] = relationship()
    validation_campaign: Mapped[ValidationCampaign] = relationship()


class CollectionSchedule(TimestampMixin, Base):
    __tablename__ = "collection_schedules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), unique=True, index=True)
    cron_expression: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    input_overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[Source] = relationship()


class WebhookEvent(TimestampMixin, Base):
    __tablename__ = "webhook_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    event_key: Mapped[str] = mapped_column(String(240), unique=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class PromptVersion(TimestampMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_name_version"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(40))
    template: Mapped[str] = mapped_column(Text)
    output_schema: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelRun(TimestampMixin, Base):
    __tablename__ = "model_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id"))
    provider: Mapped[str] = mapped_column(String(80), default="openrouter")
    model: Mapped[str] = mapped_column(String(160))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.queued)
    error: Mapped[str | None] = mapped_column(Text)
    actual_model: Mapped[str | None] = mapped_column(String(160))
    cost_usd: Mapped[float | None] = mapped_column(Float)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class JobRun(TimestampMixin, Base):
    __tablename__ = "job_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(String(120), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.queued)
    error: Mapped[str | None] = mapped_column(Text)
