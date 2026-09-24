import uuid

from opportunity_api.config import Settings
from opportunity_api.models import (
    ExperimentType,
    HypothesisReadiness,
    HypothesisTrack,
    OpportunityHypothesis,
    OpportunityStatus,
    ValidationVerdict,
)
from opportunity_api.validation.service import (
    aggregate_metrics,
    evaluate_metrics,
    experiment_specs,
    validation_ready_decisions_query,
)


def opportunity() -> OpportunityHypothesis:
    return OpportunityHypothesis(
        id=uuid.uuid4(),
        origin_cluster_id=uuid.uuid4(),
        hypothesis_key="validation-test",
        track=HypothesisTrack.pain_led,
        status=OpportunityStatus.thesis_ready,
        readiness=HypothesisReadiness.research_ready,
        name="Freight reconciliation assistant",
        industry="Logistics",
        icp="mid-market freight brokers",
        user_role="controller",
        buyer_role="CFO",
        core_workflow="reconcile short-pay invoices",
        problem="weekly invoice exceptions consume six staff hours",
        solution_concept="automate exception matching",
        value_proposition="recover revenue without spreadsheet reconciliation",
    )


def test_validation_plan_has_precommitted_metrics_and_guardrails() -> None:
    specs = experiment_specs(opportunity(), Settings())
    assert {item["experiment_type"] for item in specs} == set(ExperimentType)
    for item in specs:
        assert item["hypothesis"].startswith("Because")
        assert item["sample_target"] > 0
        assert item["success_criteria"]["primary_metric"]
        assert "guardrail" in item["success_criteria"] or "guardrails" in item["success_criteria"]


def test_aggregate_metrics_calculates_rates_without_double_counting() -> None:
    aggregate = aggregate_metrics(
        [
            {"delivered": 50, "replies": 5, "positive_replies": 3, "bounces": 2},
            {"delivered": 50, "replies": 4, "positive_replies": 2, "bounces": 3},
        ]
    )
    assert aggregate["delivered"] == 100
    assert aggregate["positive_reply_rate"] == 0.05
    assert aggregate["bounce_rate"] == 5 / 105


def test_paid_commitment_is_strong_even_before_outreach_sample() -> None:
    verdict, score, reasons = evaluate_metrics(
        aggregate_metrics([{"sample_size": 1, "paid_pilots": 1, "revenue_usd": 1000}]),
        Settings(),
    )
    assert verdict == ValidationVerdict.strong
    assert score >= 90
    assert "paid commitment" in reasons[0]


def test_small_sample_stays_pending() -> None:
    verdict, _, reasons = evaluate_metrics(
        aggregate_metrics([{"delivered": 10, "positive_replies": 2}]), Settings()
    )
    assert verdict == ValidationVerdict.pending
    assert "precommitted sample" in reasons[0]


def test_sufficient_failed_sample_is_weak() -> None:
    verdict, _, _ = evaluate_metrics(
        aggregate_metrics([{"delivered": 100, "positive_replies": 1}]), Settings()
    )
    assert verdict == ValidationVerdict.weak


def test_validation_backfill_query_is_bounded() -> None:
    statement = validation_ready_decisions_query(7)
    assert statement._limit_clause.value == 7
