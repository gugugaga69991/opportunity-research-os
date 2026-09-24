import uuid

import pytest
from pydantic import ValidationError

from opportunity_api.main import app
from opportunity_api.models import OpportunityHypothesis, RawDocument, ResearchLane
from opportunity_api.research.contracts import CompetitionAnalysis
from opportunity_api.research.planner import actor_input, plan_research
from opportunity_api.research.prompts import response_format
from opportunity_api.research.service import _verify_references


def opportunity() -> OpportunityHypothesis:
    return OpportunityHypothesis(
        name="Invoice exception automation",
        industry="logistics",
        icp="regional freight brokers",
        user_role="operations manager",
        buyer_role="COO",
        core_workflow="resolve invoice exceptions",
        problem="invoice exceptions require repetitive manual reconciliation",
        thesis={
            "task": "invoice exception reconciliation",
            "current_software": ["transport management system"],
            "trigger": "hiring operations staff",
        },
    )


def competition_payload() -> dict:
    return {
        "lane": "competition",
        "summary": "A cited competitive summary.",
        "confidence": 0.8,
        "coverage": 0.7,
        "evidence": [
            {
                "url": "https://example.com/vendor",
                "quote": "Automates invoice exception reconciliation",
                "claim": "A direct competitor exists.",
                "verified": False,
            }
        ],
        "competitors": [],
        "direct_competition_level": "medium",
        "white_space": ["freight broker workflows"],
        "free_substitutes": ["spreadsheets"],
        "why_buy_us": "Narrower workflow fit.",
        "incumbent_response_risk": "medium",
    }


def test_research_planner_covers_every_lane_without_duplicate_queries() -> None:
    plan = plan_research(opportunity())
    assert set(plan) == set(ResearchLane)
    for targets in plan.values():
        queries = [target.query for target in targets]
        assert len(queries) >= 4
        assert len({query.casefold() for query in queries}) == len(queries)


def test_research_actor_input_is_bounded_and_lane_specific() -> None:
    targets = plan_research(opportunity())[ResearchLane.competition]
    payload = actor_input(ResearchLane.competition, targets, 40)
    assert payload["mode"] == "search"
    assert payload["researchLane"] == "competition"
    assert payload["maxItems"] == 40
    assert payload["maxResultsPerQuery"] >= 5
    assert payload["searchQueries"] == [target.query for target in targets]
    assert payload["discoveryActorId"] == "apify/google-search-scraper"
    assert payload["respectRobots"] is True


def test_specialist_contract_rejects_unexpected_fields() -> None:
    payload = competition_payload()
    payload["unsupported_guess"] = "not allowed"
    with pytest.raises(ValidationError):
        CompetitionAnalysis.model_validate(payload)


def test_specialist_response_schema_is_strict() -> None:
    schema = response_format(ResearchLane.competition)
    assert schema["type"] == "json_schema"
    assert schema["json_schema"]["strict"] is True
    assert schema["json_schema"]["schema"]["additionalProperties"] is False


def test_reference_verification_checks_quote_against_source_document() -> None:
    analysis = CompetitionAnalysis.model_validate(competition_payload())
    document = RawDocument(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        collection_run_id=uuid.uuid4(),
        source_url="https://example.com/vendor",
        canonical_url="https://example.com/vendor",
        document_type="web_page",
        raw_text="The product automates invoice exception reconciliation for freight teams.",
        content_hash="a" * 64,
    )
    assert _verify_references(analysis, [document]) == 1.0
    assert analysis.evidence[0].verified is True


def test_research_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert "/research/opportunities/{opportunity_id}/start" in paths
    assert "/research/backfill" in paths
    assert "/research/campaigns/{campaign_id}" in paths
    assert "/research/tasks/{task_id}/analyze" in paths
    assert "/research/findings" in paths
    assert "/research/competitors" in paths
    assert "/research/metrics" in paths
