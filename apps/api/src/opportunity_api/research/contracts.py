from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opportunity_api.models import ResearchLane


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceReference(StrictModel):
    url: str
    quote: str
    claim: str
    verified: bool


class Competitor(StrictModel):
    name: str
    website: str
    positioning: str
    icp: str
    pricing: str
    strengths: list[str]
    weaknesses: list[str]
    evidence_urls: list[str]
    confidence: float = Field(ge=0, le=1)


class CompetitionAnalysis(StrictModel):
    lane: Literal["competition"]
    summary: str
    confidence: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference]
    competitors: list[Competitor]
    direct_competition_level: Literal["none_found", "low", "medium", "high", "dominant"]
    white_space: list[str]
    free_substitutes: list[str]
    why_buy_us: str
    incumbent_response_risk: Literal["low", "medium", "high"]


class EconomicMetric(StrictModel):
    metric: str
    low_monthly_usd: float | None
    base_monthly_usd: float | None
    high_monthly_usd: float | None
    basis: str
    evidence_urls: list[str]


class EconomicsAnalysis(StrictModel):
    lane: Literal["economics"]
    summary: str
    confidence: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference]
    metrics: list[EconomicMetric]
    existing_spend_verified: bool
    existing_spend_examples: list[str]
    pain_cost_monthly_low: float | None
    pain_cost_monthly_base: float | None
    pain_cost_monthly_high: float | None
    pricing_hypothesis_monthly: str
    budget_owner: str
    willingness_to_pay_signals: list[str]


class MarketAnalysis(StrictModel):
    lane: Literal["market"]
    summary: str
    confidence: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference]
    exact_fit_definition: str
    geographies: list[str]
    reachable_accounts_low: int | None
    reachable_accounts_base: int | None
    reachable_accounts_high: int | None
    estimation_method: str
    demand_proxies: list[str]
    market_trend: Literal["shrinking", "stable", "growing", "unknown"]
    customer_concentration_risk: Literal["low", "medium", "high", "unknown"]


class DistributionChannel(StrictModel):
    channel: str
    audience: str
    discoverability: Literal["low", "medium", "high"]
    estimated_reachable_accounts: int | None
    trigger: str
    evidence_urls: list[str]


class DistributionAnalysis(StrictModel):
    lane: Literal["distribution"]
    summary: str
    confidence: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference]
    channels: list[DistributionChannel]
    buyer_discoverability: Literal["low", "medium", "high"]
    sales_cycle: Literal["self_serve", "one_call", "two_to_four_weeks", "enterprise", "unknown"]
    procurement_friction: Literal["low", "medium", "high", "unknown"]
    proof_of_value: str
    positioning_angles: list[str]


class Challenge(StrictModel):
    claim: str
    severity: Literal["low", "medium", "high", "fatal"]
    evidence_urls: list[str]
    implication: str


class ContradictionAnalysis(StrictModel):
    lane: Literal["contradiction"]
    summary: str
    confidence: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference]
    challenges: list[Challenge]
    strongest_disproof: str
    incumbent_feature_risk: Literal["low", "medium", "high", "fatal"]
    free_solution_risk: Literal["low", "medium", "high", "fatal"]
    budget_risk: Literal["low", "medium", "high", "fatal"]
    switching_risk: Literal["low", "medium", "high", "fatal"]
    verdict: Literal["survives", "watchlist", "kill"]
    kill_reason: str


AnalysisContract = (
    CompetitionAnalysis
    | EconomicsAnalysis
    | MarketAnalysis
    | DistributionAnalysis
    | ContradictionAnalysis
)

CONTRACTS: dict[ResearchLane, type[StrictModel]] = {
    ResearchLane.competition: CompetitionAnalysis,
    ResearchLane.economics: EconomicsAnalysis,
    ResearchLane.market: MarketAnalysis,
    ResearchLane.distribution: DistributionAnalysis,
    ResearchLane.contradiction: ContradictionAnalysis,
}
