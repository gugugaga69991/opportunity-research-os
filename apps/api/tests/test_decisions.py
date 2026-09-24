import pytest

from opportunity_api.decisions.contracts import (
    EXPERT_DIMENSIONS,
    DecisionAnalysis,
    validate_expert_dimensions,
)
from opportunity_api.decisions.scoring import WEIGHTS, score_opportunity
from opportunity_api.main import app
from opportunity_api.models import (
    DecisionDisposition,
    OpportunityHypothesis,
    RiskSeverity,
    ScoreDimension,
)


def opportunity() -> OpportunityHypothesis:
    return OpportunityHypothesis(
        name="Invoice exception automation",
        industry="logistics",
        icp="regional freight brokers",
        user_role="operations manager",
        buyer_role="COO",
        core_workflow="resolve invoice exceptions",
        problem="repetitive manual reconciliation causes delayed billing",
        frequency="weekly",
        current_workaround="spreadsheets and email",
        economic_cost="$4,000 monthly labor and delay cost",
        existing_spend="$2,000 monthly outsourcing",
        desired_outcome="resolve exceptions automatically",
        solution_concept="workflow automation",
        value_proposition="reduce delays and labor",
        confidence=0.8,
        recurring_problem=True,
        confirming_signal_count=8,
        confirming_source_count=4,
        evidence_type_count=3,
        contradiction_count=1,
        thesis={},
    )


def findings(*, reachable_high: int = 50_000) -> dict[str, dict]:
    common = {"confidence": 0.85, "evidence_urls": ["https://example.com/evidence"]}
    return {
        "economics": {
            **common,
            "structured_data": {
                "existing_spend_verified": True,
                "existing_spend_examples": ["outsourcing"],
                "willingness_to_pay_signals": ["active budget", "requested pricing"],
            },
        },
        "competition": {
            **common,
            "structured_data": {
                "direct_competition_level": "none_found",
                "white_space": ["freight-specific exception handling"],
                "free_substitutes": [],
            },
        },
        "distribution": {
            **common,
            "structured_data": {
                "buyer_discoverability": "high",
                "procurement_friction": "low",
            },
        },
        "market": {
            **common,
            "structured_data": {
                "market_trend": "growing",
                "reachable_accounts_base": 25_000,
                "reachable_accounts_high": reachable_high,
            },
        },
        "contradiction": {
            **common,
            "structured_data": {"verdict": "survives", "kill_reason": ""},
        },
    }


def analysis(*, verdict: str = "advance") -> DecisionAnalysis:
    dimensions = [
        {
            "dimension": dimension.value,
            "score": 9,
            "confidence": 0.85,
            "rationale": "Supported by the supplied workflow evidence.",
            "evidence_urls": ["https://example.com/evidence"],
            "assumptions": [],
        }
        for dimension in sorted(EXPERT_DIMENSIONS, key=lambda item: item.value)
    ]
    return DecisionAnalysis.model_validate(
        {
            "summary": "The opportunity survives technical and commercial review.",
            "confidence": 0.85,
            "evidence": [],
            "expert_dimensions": dimensions,
            "data_requirements": ["invoice and shipment data"],
            "integration_requirements": ["TMS API"],
            "ai_advantage": "classifies unstructured exception context",
            "defensibility": "workflow history and integrations",
            "expansion_path": ["billing analytics"],
            "realistic_time_to_value": "one week",
            "objections": ["integration effort"],
            "risks": [
                {
                    "category": "integration",
                    "severity": RiskSeverity.medium.value,
                    "claim": "Some systems may lack modern APIs.",
                    "implication": "Onboarding may be slower.",
                    "mitigation": "Support file imports.",
                    "evidence_urls": [],
                }
            ],
            "hard_kills": [],
            "kill_criteria": ["No buyer accepts a paid pilot."],
            "investment_case": {
                "why_market": "Many reachable brokers.",
                "why_workflow": "Recurring exception work.",
                "why_now": "Improved document models.",
                "economic_meaning": "Measured labor and delay cost.",
                "current_solution_gap": "Manual reconciliation remains.",
                "why_we_can_win": "Narrow workflow depth.",
                "monthly_value": "Recurring labor savings.",
                "retention_mechanism": "Embedded exception history.",
                "business_killers": "Unavailable integrations.",
                "disconfirming_evidence": "Low urgency or cheap incumbent feature.",
            },
            "red_team_verdict": verdict,
        }
    )


def test_score_weights_cover_exactly_fourteen_dimensions_and_sum_to_one() -> None:
    assert set(WEIGHTS) == set(ScoreDimension)
    assert len(WEIGHTS) == 14
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_high_quality_opportunity_advances_with_auditable_dimensions() -> None:
    result = score_opportunity(
        opportunity(),
        findings(),
        analysis(),
        0.85,
        True,
        {"https://example.com/evidence"},
        advance_threshold=70,
        kill_threshold=40,
        minimum_confidence=0.65,
    )
    assert result.disposition == DecisionDisposition.advance
    assert len(result.dimensions) == 14
    assert result.adjusted_score >= 70
    assert result.confidence >= 0.65
    assert not result.hard_kills


def test_verified_market_below_fifty_accounts_is_a_hard_kill() -> None:
    result = score_opportunity(
        opportunity(),
        findings(reachable_high=20),
        analysis(),
        0.85,
        True,
        {"https://example.com/evidence"},
        advance_threshold=70,
        kill_threshold=40,
        minimum_confidence=0.65,
    )
    assert result.disposition == DecisionDisposition.kill
    assert result.hard_kills[0]["criterion"] == "market_controlled_by_fewer_than_50_customers"


def test_red_team_watchlist_prevents_advancement() -> None:
    result = score_opportunity(
        opportunity(),
        findings(),
        analysis(verdict="watchlist"),
        0.85,
        True,
        {"https://example.com/evidence"},
        advance_threshold=70,
        kill_threshold=40,
        minimum_confidence=0.65,
    )
    assert result.disposition == DecisionDisposition.watchlist
    assert result.penalties["red_team_watchlist"] == 5


def test_unsupported_red_team_kill_cannot_destroy_opportunity() -> None:
    result = score_opportunity(
        opportunity(),
        findings(),
        analysis(verdict="kill"),
        0.85,
        True,
        {"https://example.com/evidence"},
        advance_threshold=70,
        kill_threshold=40,
        minimum_confidence=0.65,
    )
    assert result.disposition == DecisionDisposition.watchlist
    assert not result.hard_kills
    assert result.penalties["unsupported_red_team_kill"] == 10


def test_expert_contract_requires_exact_dimension_set() -> None:
    payload = analysis().model_dump()
    payload["expert_dimensions"] = payload["expert_dimensions"][:-1]
    incomplete = DecisionAnalysis.model_validate(payload)
    with pytest.raises(ValueError, match="incomplete"):
        validate_expert_dimensions(incomplete)


def test_decision_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/decisions/campaigns/{campaign_id}/score" in paths
    assert "/decisions/backfill" in paths
    assert "/decisions/{decision_id}/analyze" in paths
    assert "/decisions/{decision_id}" in paths
    assert "/decisions/metrics" in paths
