import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import (
    CalibrationStatus,
    FreshnessStatus,
    OutcomeEventType,
)


class OutcomeCreate(BaseModel):
    event_key: str = Field(min_length=3, max_length=160)
    event_type: OutcomeEventType
    decision_id: uuid.UUID | None = None
    source: str = Field(default="manual", min_length=2, max_length=120)
    value_usd: float | None = Field(default=None, ge=0)
    properties: dict = Field(default_factory=dict)
    evidence_urls: list[str] = Field(default_factory=list, max_length=100)
    occurred_at: datetime | None = None


class OutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    decision_id: uuid.UUID | None
    event_key: str
    event_type: OutcomeEventType
    source: str
    value_usd: float | None
    properties: dict
    evidence_urls: list[str]
    occurred_at: datetime
    created_at: datetime


class CalibrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version: str
    status: CalibrationStatus
    sample_count: int
    baseline_weights: dict
    proposed_weights: dict
    metrics: dict
    recommendations: list[dict]
    approved_by: str | None
    reviewed_at: datetime | None
    created_at: datetime


class CalibrationReview(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    actor: str = Field(default="human", min_length=2, max_length=120)


class ScoringProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    calibration_run_id: uuid.UUID | None
    version: str
    weights: dict
    active: bool
    approved_by: str
    activated_at: datetime


class FreshnessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    active_campaign_id: uuid.UUID | None
    status: FreshnessStatus
    freshness_score: float
    priority: float
    last_researched_at: datetime | None
    next_check_at: datetime
    due_topics: list[str]
    detected_changes: list[dict]
    requires_rescore: bool
    error: str | None
    updated_at: datetime


class BackfillRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)
