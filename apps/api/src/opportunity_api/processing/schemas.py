import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import DuplicateKind, ProcessingStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceClaim(StrictModel):
    field: str = Field(description="Ontology field supported by the quotation")
    quote: str = Field(description="Exact, short quotation copied from the source text")


class SignalOntology(StrictModel):
    is_pain: bool
    pain_probability: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    pain_type: str
    industry: str
    subindustry: str
    company_type: str
    company_size: str
    user_role: str
    buyer_role: str
    trigger: str
    task: str
    current_workflow: list[str]
    tools: list[str]
    inputs: list[str]
    outputs: list[str]
    manual_steps: list[str]
    frequency: str
    recurrence: str
    time_spent: str
    workaround: str
    current_spend: str
    failure_consequence: str
    revenue_impact: str
    risk_impact: str
    compliance_impact: str
    urgency: str
    current_software: list[str]
    desired_outcome: str
    summary: str
    evidence: list[EvidenceClaim]


class EvidenceSpan(BaseModel):
    field: str
    quote: str
    start: int
    end: int
    verified: bool


class SignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    raw_document_id: uuid.UUID
    canonical_signal_id: uuid.UUID | None
    status: ProcessingStatus
    language: str
    exact_hash: str
    is_duplicate: bool
    duplicate_kind: DuplicateKind | None
    duplicate_score: float | None
    embedding_model: str | None
    processed_at: datetime | None
    error: str | None
    created_at: datetime


class ExtractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    signal_id: uuid.UUID
    is_pain: bool
    pain_probability: float
    confidence: float
    industry: str
    user_role: str
    buyer_role: str
    recurrence: str
    urgency: str
    ontology: dict
    evidence_spans: list[dict]


class SignalDetail(SignalRead):
    normalized_title: str
    normalized_text: str
    extraction: ExtractionRead | None = None


class ProcessingMetrics(BaseModel):
    total_documents: int
    total_signals: int
    awaiting_model: int
    succeeded: int
    failed: int
    duplicates: int
    pains: int


class BackfillRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=5000)
