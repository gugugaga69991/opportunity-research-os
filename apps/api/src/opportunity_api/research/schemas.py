import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import FindingStance, ResearchLane, ResearchStatus


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    version: str
    status: ResearchStatus
    required_lane_count: int
    completed_lane_count: int
    failed_lane_count: int
    coverage_score: float
    cost_usd: float
    started_at: datetime | None
    completed_at: datetime | None
    summary: dict
    error: str | None
    created_at: datetime
    updated_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    campaign_id: uuid.UUID
    lane: ResearchLane
    status: ResearchStatus
    required: bool
    research_queries: list[str]
    actor_input: dict
    collection_run_id: uuid.UUID | None
    model_run_id: uuid.UUID | None
    documents_found: int
    coverage_score: float
    attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class TargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID
    target_type: str
    value: str
    rationale: str
    status: ResearchStatus


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    campaign_id: uuid.UUID
    task_id: uuid.UUID
    lane: ResearchLane
    title: str
    summary: str
    stance: FindingStance
    confidence: float
    structured_data: dict
    evidence_urls: list[str]
    document_ids: list[str]
    active: bool
    last_seen_at: datetime


class CompetitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    opportunity_id: uuid.UUID
    finding_id: uuid.UUID
    name: str
    normalized_name: str
    website: str
    positioning: str
    icp: str
    pricing: str
    strengths: list[str]
    weaknesses: list[str]
    evidence_urls: list[str]
    confidence: float
    active: bool


class CampaignDetail(CampaignRead):
    tasks: list[TaskRead]
    targets: list[TargetRead]
    findings: list[FindingRead]
    competitors: list[CompetitorRead]


class ResearchBackfill(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)


class ResearchMetrics(BaseModel):
    campaigns: int
    awaiting_configuration: int
    running: int
    completed: int
    blocked: int
    gate_passed: int
    active_findings: int
    active_competitors: int
