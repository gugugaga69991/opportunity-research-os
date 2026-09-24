import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import (
    ClusterLinkRole,
    EvidenceStance,
    HypothesisReadiness,
    HypothesisTrack,
    OpportunityStatus,
)


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    origin_cluster_id: uuid.UUID
    track: HypothesisTrack
    status: OpportunityStatus
    readiness: HypothesisReadiness
    name: str
    industry: str
    icp: str
    user_role: str
    buyer_role: str
    problem: str
    solution_concept: str
    confidence: float
    confirming_signal_count: int
    confirming_source_count: int
    evidence_type_count: int
    contradiction_count: int
    buyer_identified: bool
    recurring_problem: bool
    evidence_gate_passed: bool
    created_at: datetime
    updated_at: datetime


class OpportunityEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    signal_id: uuid.UUID
    cluster_id: uuid.UUID | None
    stance: EvidenceStance
    evidence_type: str
    claim: str
    confidence: float
    active: bool
    last_seen_at: datetime
    metadata: dict = Field(validation_alias="metadata_")


class OpportunityClusterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    cluster_id: uuid.UUID
    role: ClusterLinkRole
    shared_entity_count: int
    confidence: float
    active: bool
    last_seen_at: datetime


class TransitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: OpportunityStatus | None
    to_status: OpportunityStatus
    actor: str
    reason: str
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime


class OpportunityDetail(OpportunityRead):
    core_workflow: str
    frequency: str
    current_workaround: str
    economic_cost: str
    existing_spend: str
    why_now: str
    desired_outcome: str
    value_proposition: str
    thesis: dict
    genealogy: dict
    evidence: list[OpportunityEvidenceRead]
    clusters: list[OpportunityClusterRead]
    transitions: list[TransitionRead]


class StateChange(BaseModel):
    status: OpportunityStatus
    reason: str = Field(min_length=3, max_length=1000)
    actor: str = Field(default="human", min_length=2, max_length=80)


class OpportunityBackfill(BaseModel):
    limit: int = Field(default=100, ge=1, le=5000)


class OpportunityMetrics(BaseModel):
    total: int
    preliminary: int
    corroborating: int
    research_ready: int
    pain_led: int
    change_led: int
    evidence_gated: int
    with_contradictions: int
