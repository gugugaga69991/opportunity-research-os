import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import (
    ExperimentStatus,
    ExperimentType,
    ValidationStatus,
    ValidationVerdict,
)


class ValidationCampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    decision_id: uuid.UUID
    version: str
    status: ValidationStatus
    verdict: ValidationVerdict
    validation_score: float
    experiment_count: int
    completed_experiment_count: int
    summary: dict
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ValidationExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    campaign_id: uuid.UUID
    experiment_type: ExperimentType
    status: ExperimentStatus
    hypothesis: str
    audience: str
    channel: str
    positioning_angle: str
    price_point_usd: float | None
    sample_target: int
    success_criteria: dict
    execution_brief: dict
    aggregate: dict
    started_at: datetime | None
    completed_at: datetime | None


class ValidationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    experiment_id: uuid.UUID
    result_key: str
    source: str
    metrics: dict
    qualitative_feedback: list[str]
    evidence_urls: list[str]
    interpretation: str
    observed_at: datetime
    created_at: datetime


class FailureMemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    campaign_id: uuid.UUID
    category: str
    reason: str
    predicted: dict
    actual: dict
    reusable_lesson: str
    active: bool


class ValidationCampaignDetail(ValidationCampaignRead):
    experiments: list[ValidationExperimentRead]
    results: list[ValidationResultRead]
    failures: list[FailureMemoryRead]


class ResultCreate(BaseModel):
    result_key: str = Field(min_length=3, max_length=160)
    source: str = Field(default="manual", min_length=2, max_length=120)
    metrics: dict[str, float | int | bool] = Field(default_factory=dict)
    qualitative_feedback: list[str] = Field(default_factory=list, max_length=100)
    evidence_urls: list[str] = Field(default_factory=list, max_length=100)
    interpretation: str = Field(default="", max_length=4000)
    observed_at: datetime | None = None


class ExperimentStateChange(BaseModel):
    status: ExperimentStatus


class ValidationMetrics(BaseModel):
    total: int
    planned: int
    running: int
    completed: int
    strong: int
    mixed: int
    weak: int
    invalidated: int
    paid_signals: int
    failure_memories: int
