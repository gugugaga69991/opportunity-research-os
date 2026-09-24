from opportunity_api.models import HypothesisReadiness, HypothesisTrack
from opportunity_api.opportunities.generator import build_hypothesis_fields, evaluate_gate


def gate(**overrides):
    values = {
        "track": HypothesisTrack.pain_led,
        "signal_count": 4,
        "source_count": 3,
        "evidence_type_count": 3,
        "recurrence_score": 0.85,
        "buyer_identified": True,
        "economic_evidence_present": True,
        "corroboration_score": 0.82,
        "average_extraction_confidence": 0.86,
        "contradiction_count": 0,
        "has_confirming_pain_cluster": True,
        "minimum_signals": 2,
        "minimum_sources": 2,
        "minimum_evidence_types": 2,
        "minimum_recurrence": 0.5,
    }
    values.update(overrides)
    return evaluate_gate(**values)


def test_pain_hypothesis_passes_only_complete_evidence_gate() -> None:
    result = gate()
    assert result.passed is True
    assert result.readiness == HypothesisReadiness.research_ready
    assert all(result.checks.values())

    missing_buyer = gate(buyer_identified=False)
    assert missing_buyer.passed is False
    assert missing_buyer.readiness == HypothesisReadiness.corroborating
    assert missing_buyer.checks["buyer_identified"] is False

    no_economics = gate(economic_evidence_present=False)
    assert no_economics.passed is False
    assert no_economics.checks["economic_evidence"] is False


def test_change_hypothesis_requires_confirming_pain() -> None:
    unconfirmed = gate(
        track=HypothesisTrack.change_led,
        has_confirming_pain_cluster=False,
    )
    assert unconfirmed.passed is False
    assert unconfirmed.checks["change_confirmed_by_pain"] is False
    confirmed = gate(track=HypothesisTrack.change_led, has_confirming_pain_cluster=True)
    assert confirmed.passed is True


def test_contradictions_reduce_confidence_without_erasing_hypothesis() -> None:
    supported = gate(contradiction_count=0)
    challenged = gate(contradiction_count=3)
    assert challenged.confidence < supported.confidence
    assert challenged.passed is True
    overwhelmed = gate(contradiction_count=4)
    assert overwhelmed.passed is False
    assert overwhelmed.checks["contradiction_balance"] is False


def test_structured_hypothesis_is_derived_from_workflow_evidence() -> None:
    records = [
        {
            "industry": "Accounting",
            "company_type": "Bookkeeping agency",
            "company_size": "10-50",
            "user_role": "Bookkeeper",
            "buyer_role": "Owner",
            "trigger": "Month end",
            "task": "Reconcile invoices",
            "current_workflow": ["Export transactions", "Compare rows"],
            "manual_steps": ["Correct mismatches"],
            "frequency": "Weekly",
            "workaround": "Spreadsheet macros",
            "current_spend": "$500/month",
            "time_spent": "Four hours/week",
            "failure_consequence": "Late close",
            "revenue_impact": "Delayed billing",
            "risk_impact": "Incorrect books",
            "compliance_impact": "Audit exposure",
            "desired_outcome": "Automatic reconciliation",
            "tools": ["Excel"],
            "current_software": ["QuickBooks"],
            "summary": "Manual reconciliation delays the close.",
        }
    ]
    fields = build_hypothesis_fields(
        HypothesisTrack.pain_led,
        "Invoice reconciliation",
        "Recurring accounting workflow",
        records,
    )
    assert fields["name"] == "Reconcile invoices workflow for Accounting"
    assert fields["buyer_role"] == "Owner"
    assert fields["core_workflow"] == "Export transactions -> Compare rows"
    assert fields["existing_spend"] == "$500/month"
    assert fields["thesis"]["tools"] == ["Excel"]
    assert "Automatic reconciliation" in fields["solution_concept"]
