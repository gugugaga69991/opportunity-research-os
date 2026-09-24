import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import AccessRisk, RunStatus, TriggerType


class SourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = ""
    source_type: str
    access_method: str = "apify"
    adapter_key: str = "generic_apify"
    actor_id: str | None = None
    enabled: bool = True
    reliability_weight: float = Field(default=0.5, ge=0, le=1)
    access_risk: AccessRisk = AccessRisk.review_required
    collector_config: dict[str, Any] = Field(default_factory=dict)
    access_metadata: dict[str, Any] = Field(default_factory=dict)


class SourceRead(SourceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SourceUpdate(BaseModel):
    description: str | None = None
    actor_id: str | None = None
    enabled: bool | None = None
    reliability_weight: float | None = Field(default=None, ge=0, le=1)
    access_risk: AccessRisk | None = None
    collector_config: dict[str, Any] | None = None
    access_metadata: dict[str, Any] | None = None


class CollectionStart(BaseModel):
    input_overrides: dict[str, Any] = Field(default_factory=dict)
    trigger_type: TriggerType = TriggerType.manual


class CollectionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_id: uuid.UUID
    external_run_id: str | None
    external_dataset_id: str | None
    trigger_type: TriggerType
    status: RunStatus
    items_received: int
    items_ingested: int
    items_skipped: int
    cost_usd: float | None
    metrics: dict[str, Any]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RawDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_id: uuid.UUID
    collection_run_id: uuid.UUID
    source_url: str
    canonical_url: str
    document_type: str
    title: str
    author: str | None
    published_at: datetime | None
    collected_at: datetime
    language: str | None
    raw_text: str
    provenance: dict[str, Any]
    content_hash: str


class ApifyWebhookPayload(BaseModel):
    event_type: str = Field(alias="eventType")
    event_data: dict[str, Any] = Field(alias="eventData")
    resource: dict[str, Any] = Field(default_factory=dict)


class ScheduleCreate(BaseModel):
    cron_expression: str
    timezone: str = "UTC"
    enabled: bool = True
    input_overrides: dict[str, Any] = Field(default_factory=dict)
    next_run_at: datetime


class ScheduleRead(ScheduleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_id: uuid.UUID
    last_enqueued_at: datetime | None
    created_at: datetime
    updated_at: datetime
