from dataclasses import dataclass, replace
from typing import Any

from opportunity_api.decisions.contracts import DecisionAnalysis
from opportunity_api.models import (
    DecisionDisposition,
    OpportunityHypothesis,
    RiskSeverity,
    ScoreDimension,
)

WEIGHTS: dict[ScoreDimension, float] = {
    ScoreDimension.pain_severity: 0.12,
    ScoreDimension.recurring_frequency: 0.10,
    ScoreDimension.existing_spend: 0.09,
    ScoreDimension.willingness_to_pay: 0.08,
    ScoreDimension.competition_weakness: 0.10,
    ScoreDimension.distribution_quality: 0.10,
    ScoreDimension.retention: 0.08,
    ScoreDimension.buildability: 0.07,
    ScoreDimension.time_to_value: 0.06,
    ScoreDimension.ai_advantage: 0.05,
    ScoreDimension.defensibility: 0.05,
    ScoreDimension.market_timing: 0.04,
    ScoreDimension.reachable_tam: 0.03,
    ScoreDimension.expansion: 0.03,
}


@dataclass(frozen=True)
class DimensionResult:
    dimension: ScoreDimension
    score: float
    weight: float
    confidence: float
    rationale: str
    evidence_urls: list[str]
    inputs: dict[str, Any]

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight * 10


@dataclass(frozen=True)
class ScoreResult:
    dimensions: list[DimensionResult]
    raw_score: float
    confidence: float
    adjusted_score: float
    penalties: dict[str, float]
    hard_kills: list[dict]
    disposition: DecisionDisposition


def _finding(findings: dict[str, dict], lane: str) -> tuple[dict, float, list[str]]:
    item = findings.get(lane) or {}
    return (
        item.get("structured_data") or {},
        float(item.get("confidence") or 0),
        list(item.get("evidence_urls") or []),
    )


def _bounded(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 3)


def _result(
    dimension: ScoreDimension,
    score: float,
    confidence: float,
    rationale: str,
    urls: list[str],
    inputs: dict[str, Any],
) -> DimensionResult:
    return DimensionResult(
        dimension,
        _bounded(score),
        WEIGHTS[dimension],
        max(0.0, min(1.0, confidence)),
        rationale,
        sorted(set(urls)),
        inputs,
    )


def deterministic_dimensions(
    opportunity: OpportunityHypothesis,
    findings: dict[str, dict],
) -> list[DimensionResult]:
    economics, economics_confidence, economics_urls = _finding(findings, "economics")
    competition, competition_confidence, competition_urls = _finding(findings, "competition")
    distribution, distribution_confidence, distribution_urls = _finding(findings, "distribution")
    market, market_confidence, market_urls = _finding(findings, "market")

    frequency = (opportunity.frequency or "").casefold()
    recurrence = next(
        (
            score
            for term, score in (("daily", 10), ("weekly", 8), ("monthly", 6))
            if term in frequency
        ),
        7 if opportunity.recurring_problem else 2,
    )
    spend_verified = bool(economics.get("existing_spend_verified"))
    spend_examples = economics.get("existing_spend_examples") or []
    willingness = economics.get("willingness_to_pay_signals") or []
    competition_level = competition.get("direct_competition_level", "dominant")
    competition_score = {
        "none_found": 9,
        "low": 8,
        "medium": 6,
        "high": 3,
        "dominant": 1,
    }.get(competition_level, 3)
    if competition.get("white_space"):
        competition_score += 0.5
    if competition.get("free_substitutes"):
        competition_score -= 0.5
    discoverability = distribution.get("buyer_discoverability", "low")
    distribution_score = {"low": 3, "medium": 6, "high": 9}.get(discoverability, 3)
    friction = distribution.get("procurement_friction", "unknown")
    distribution_score += {"low": 1, "high": -1}.get(friction, 0)
    trend = market.get("market_trend", "unknown")
    timing_score = {"growing": 9, "stable": 6, "shrinking": 2, "unknown": 4}.get(trend, 4)
    reachable = market.get("reachable_accounts_base")
    if reachable is None:
        tam_score = 3
    elif reachable >= 100_000:
        tam_score = 10
    elif reachable >= 20_000:
        tam_score = 9
    elif reachable >= 5_000:
        tam_score = 8
    elif reachable >= 1_000:
        tam_score = 6
    elif reachable >= 50:
        tam_score = 4
    else:
        tam_score = 1
    hypothesis_confidence = float(opportunity.confidence or 0)
    return [
        _result(
            ScoreDimension.pain_severity,
            5 + hypothesis_confidence * 5,
            hypothesis_confidence,
            "Derived from corroborated pain confidence.",
            [],
            {
                "hypothesis_confidence": hypothesis_confidence,
                "supporting_signal_ids": (opportunity.genealogy or {}).get(
                    "supporting_signal_ids", []
                ),
            },
        ),
        _result(
            ScoreDimension.recurring_frequency,
            recurrence,
            hypothesis_confidence,
            "Derived from observed frequency and the recurrence gate.",
            [],
            {"frequency": opportunity.frequency, "recurring": opportunity.recurring_problem},
        ),
        _result(
            ScoreDimension.existing_spend,
            9 if spend_verified else 7 if spend_examples else 3,
            economics_confidence,
            "Rewards verified current software or service spend.",
            economics_urls,
            {"verified": spend_verified, "examples": spend_examples},
        ),
        _result(
            ScoreDimension.willingness_to_pay,
            3 + min(len(willingness), 5) + (1 if spend_verified else 0),
            economics_confidence,
            "Uses explicit willingness-to-pay and existing-spend signals.",
            economics_urls,
            {"signals": willingness, "spend_verified": spend_verified},
        ),
        _result(
            ScoreDimension.competition_weakness,
            competition_score,
            competition_confidence,
            "Inverts direct competition strength and adjusts for white-space and free substitutes.",
            competition_urls,
            {
                "level": competition_level,
                "white_space": competition.get("white_space") or [],
                "free_substitutes": competition.get("free_substitutes") or [],
            },
        ),
        _result(
            ScoreDimension.distribution_quality,
            distribution_score,
            distribution_confidence,
            "Combines buyer discoverability with procurement friction.",
            distribution_urls,
            {"discoverability": discoverability, "procurement_friction": friction},
        ),
        _result(
            ScoreDimension.market_timing,
            timing_score,
            market_confidence,
            "Uses the researched exact-fit market trajectory.",
            market_urls,
            {"market_trend": trend},
        ),
        _result(
            ScoreDimension.reachable_tam,
            tam_score,
            market_confidence,
            "Uses bottom-up exact-fit reachable account counts, not generic TAM.",
            market_urls,
            {"reachable_accounts_base": reachable},
        ),
    ]


def score_opportunity(
    opportunity: OpportunityHypothesis,
    findings: dict[str, dict],
    analysis: DecisionAnalysis,
    research_coverage: float,
    research_gate_passed: bool,
    verified_urls: set[str],
    *,
    advance_threshold: float,
    kill_threshold: float,
    minimum_confidence: float,
    weights: dict[ScoreDimension, float] | None = None,
) -> ScoreResult:
    dimensions = deterministic_dimensions(opportunity, findings)
    for item in analysis.expert_dimensions:
        urls = sorted(set(item.evidence_urls) & verified_urls)
        evidence_confidence_cap = 1.0 if urls else 0.25 if item.evidence_urls else 0.4
        dimensions.append(
            _result(
                item.dimension,
                item.score,
                min(
                    item.confidence,
                    analysis.confidence,
                    research_coverage,
                    evidence_confidence_cap,
                ),
                item.rationale,
                urls,
                {"assumptions": item.assumptions},
            )
        )
    active_weights = weights or WEIGHTS
    dimensions = [replace(item, weight=active_weights[item.dimension]) for item in dimensions]
    dimensions.sort(key=lambda item: item.dimension.value)
    raw_score = round(sum(item.weighted_score for item in dimensions), 3)
    confidence = round(
        sum(item.confidence * item.weight for item in dimensions) / sum(active_weights.values()),
        4,
    )
    low_confidence_count = sum(item.confidence < 0.5 for item in dimensions)
    high_risk_count = sum(
        item.severity == RiskSeverity.high and bool(set(item.evidence_urls) & verified_urls)
        for item in analysis.risks
    )
    penalties = {
        "research_coverage": round(max(0.0, 0.75 - research_coverage) * 20, 3),
        "low_confidence_dimensions": min(low_confidence_count * 1.5, 12.0),
        "high_risks": min(high_risk_count * 2.0, 10.0),
        "red_team_watchlist": 5.0 if analysis.red_team_verdict == "watchlist" else 0.0,
        "unsupported_red_team_kill": (10.0 if analysis.red_team_verdict == "kill" else 0.0),
    }
    adjusted_score = round(max(0.0, raw_score - sum(penalties.values())), 3)
    hard_kills: list[dict] = []
    contradiction = findings.get("contradiction", {}).get("structured_data") or {}
    if contradiction.get("verdict") == "kill":
        hard_kills.append(
            {
                "criterion": "contradiction_research_kill",
                "rationale": contradiction.get("kill_reason", ""),
            }
        )
    market, market_confidence, _ = _finding(findings, "market")
    if (
        market.get("reachable_accounts_high") is not None
        and market["reachable_accounts_high"] < 50
        and market_confidence >= 0.6
    ):
        hard_kills.append(
            {
                "criterion": "market_controlled_by_fewer_than_50_customers",
                "rationale": "Verified reachable market is below 50 accounts.",
            }
        )
    for item in analysis.hard_kills:
        cited = sorted(set(item.evidence_urls) & verified_urls)
        if item.triggered and cited:
            hard_kills.append(
                {"criterion": item.criterion, "rationale": item.rationale, "evidence_urls": cited}
            )
    if any(
        item.severity == RiskSeverity.fatal and set(item.evidence_urls) & verified_urls
        for item in analysis.risks
    ):
        hard_kills.append(
            {
                "criterion": "fatal_red_team_risk",
                "rationale": "A source-supported fatal risk was identified.",
            }
        )
    if hard_kills or adjusted_score < kill_threshold:
        disposition = DecisionDisposition.kill
    elif (
        adjusted_score >= advance_threshold
        and confidence >= minimum_confidence
        and research_gate_passed
        and analysis.red_team_verdict == "advance"
    ):
        disposition = DecisionDisposition.advance
    else:
        disposition = DecisionDisposition.watchlist
    return ScoreResult(
        dimensions,
        raw_score,
        confidence,
        adjusted_score,
        penalties,
        hard_kills,
        disposition,
    )
