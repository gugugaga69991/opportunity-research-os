import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import (
    DecisionDisposition,
    DecisionStatus,
    RiskSeverity,
    ScoreDimension,
)


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    campaign_id: uuid.UUID
    model_run_id: uuid.UUID | None
    version: str
    status: DecisionStatus
    disposition: DecisionDisposition | None
    raw_score: float
    confidence_score: float
    adjusted_score: float
    research_coverage: float
    hard_kill_triggered: bool
    penalties: dict
    hard_kills: list[dict]
    thesis: dict
    red_team: dict
    cost_usd: float
    attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class ScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    dimension: ScoreDimension
    score: float
    weight: float
    weighted_score: float
    confidence: float
    rationale: str
    evidence_urls: list[str]
    inputs: dict


class RiskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    category: str
    severity: RiskSeverity
    claim: str
    implication: str
    mitigation: str
    evidence_urls: list[str]
    active: bool


class DecisionDetail(DecisionRead):
    scores: list[ScoreRead]
    risks: list[RiskRead]


class DecisionBackfill(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)


class DecisionMetrics(BaseModel):
    total: int
    awaiting_analysis: int
    completed: int
    failed: int
    advance: int
    watchlist: int
    killed: int
    hard_kills: int
    average_adjusted_score: float
    total_cost_usd: float
