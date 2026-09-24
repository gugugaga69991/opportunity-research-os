from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import RiskSeverity, ScoreDimension
from opportunity_api.research.contracts import EvidenceReference


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpertDimension(StrictModel):
    dimension: ScoreDimension
    score: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence_urls: list[str]
    assumptions: list[str]


class RiskAssessment(StrictModel):
    category: str = Field(min_length=1, max_length=120)
    severity: RiskSeverity
    claim: str
    implication: str
    mitigation: str
    evidence_urls: list[str]


class HardKillAssessment(StrictModel):
    criterion: str
    triggered: bool
    rationale: str
    evidence_urls: list[str]


class InvestmentCase(StrictModel):
    why_market: str
    why_workflow: str
    why_now: str
    economic_meaning: str
    current_solution_gap: str
    why_we_can_win: str
    monthly_value: str
    retention_mechanism: str
    business_killers: str
    disconfirming_evidence: str


class DecisionAnalysis(StrictModel):
    summary: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference]
    expert_dimensions: list[ExpertDimension]
    data_requirements: list[str]
    integration_requirements: list[str]
    ai_advantage: str
    defensibility: str
    expansion_path: list[str]
    realistic_time_to_value: str
    objections: list[str]
    risks: list[RiskAssessment]
    hard_kills: list[HardKillAssessment]
    kill_criteria: list[str]
    investment_case: InvestmentCase
    red_team_verdict: Literal["advance", "watchlist", "kill"]


EXPERT_DIMENSIONS = {
    ScoreDimension.retention,
    ScoreDimension.buildability,
    ScoreDimension.time_to_value,
    ScoreDimension.ai_advantage,
    ScoreDimension.defensibility,
    ScoreDimension.expansion,
}


def validate_expert_dimensions(analysis: DecisionAnalysis) -> None:
    dimensions = [item.dimension for item in analysis.expert_dimensions]
    if len(dimensions) != len(set(dimensions)):
        raise ValueError("Expert assessment contains duplicate score dimensions")
    if set(dimensions) != EXPERT_DIMENSIONS:
        missing = sorted(item.value for item in EXPERT_DIMENSIONS - set(dimensions))
        extra = sorted(item.value for item in set(dimensions) - EXPERT_DIMENSIONS)
        raise ValueError(f"Expert dimensions are incomplete; missing={missing}, extra={extra}")
