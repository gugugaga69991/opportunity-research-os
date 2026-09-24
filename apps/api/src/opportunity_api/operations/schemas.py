import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import AlertStatus, BuildSpecStatus, PortfolioState


class PortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    current_score: float
    previous_score: float
    score_velocity: float
    competition_velocity: float
    pain_velocity: float
    market_timing_velocity: float
    rank: int | None
    previous_rank: int | None
    state: PortfolioState
    reasons: list
    assessed_at: datetime


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID | None
    alert_type: str
    severity: str
    status: AlertStatus
    title: str
    message: str
    payload: dict
    telegram_delivered_at: datetime | None
    delivery_error: str | None
    created_at: datetime


class AlertUpdate(BaseModel):
    status: AlertStatus


class InterviewCreate(BaseModel):
    interview_key: str = Field(min_length=1, max_length=160)
    company: str = Field(default="", max_length=240)
    industry: str = Field(default="", max_length=160)
    company_size: str = Field(default="", max_length=120)
    participant_role: str = Field(default="", max_length=160)
    buyer_or_user: Literal["buyer", "user", "both"] = "user"
    interviewed_at: datetime
    transcript: str = ""
    summary: str = Field(min_length=1)
    current_workflow: str = ""
    tools_used: list[str] = Field(default_factory=list)
    pain_frequency: str = Field(default="", max_length=120)
    time_cost_hours: float | None = Field(default=None, ge=0)
    financial_cost_usd: float | None = Field(default=None, ge=0)
    current_spend_usd: float | None = Field(default=None, ge=0)
    complaints: list[str] = Field(default_factory=list)
    desired_outcome: str = ""
    urgency: str = Field(default="", max_length=80)
    budget_signal: str = Field(default="", max_length=120)
    price_reaction: str = Field(default="", max_length=120)
    objections: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    follow_up: str = ""
    evidence_strength: float = Field(default=0.5, ge=0, le=1)


class InterviewRead(InterviewCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    created_at: datetime


class BuildSpecRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    decision_id: uuid.UUID
    validation_campaign_id: uuid.UUID
    version: str
    status: BuildSpecStatus
    content: dict[str, Any]
    markdown: str
    source_manifest: dict
    approved_by: str | None
    approved_at: datetime | None
    created_at: datetime


class BuildSpecReview(BaseModel):
    action: Literal["approve"]
    actor: str = Field(min_length=1, max_length=120)


class SyncRequest(BaseModel):
    deliver: bool = True
