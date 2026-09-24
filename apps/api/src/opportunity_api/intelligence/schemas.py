import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import (
    ClusterStatus,
    ClusterType,
    EntityType,
    MembershipMethod,
)


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    entity_type: EntityType
    display_value: str
    normalized_value: str
    aliases: list
    metadata: dict = Field(validation_alias="metadata_")


class RelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relation: str
    support_count: int
    confidence: float
    supporting_signal_ids: list


class ClusterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    cluster_type: ClusterType
    title: str
    summary: str
    status: ClusterStatus
    signal_count: int
    source_count: int
    evidence_type_count: int
    corroboration_score: float
    recurrence_score: float
    velocity_30d: float
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    metrics: dict
    created_at: datetime


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    signal_id: uuid.UUID
    similarity: float
    method: MembershipMethod
    is_primary: bool


class ClusterEntityRead(BaseModel):
    entity_id: uuid.UUID
    entity_type: EntityType
    display_value: str
    relation: str
    support_count: int


class ClusterDetail(ClusterRead):
    memberships: list[MembershipRead]
    entities: list[ClusterEntityRead]


class IntelligenceMetrics(BaseModel):
    entities: int
    relationships: int
    clusters: int
    pain_clusters: int
    workflow_clusters: int
    change_clusters: int
    clustered_signals: int
    corroborated_clusters: int


class IntelligenceBackfill(BaseModel):
    limit: int = Field(default=500, ge=1, le=5000)
