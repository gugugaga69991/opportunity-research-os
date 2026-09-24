from opportunity_api.config import Settings
from opportunity_api.processing.prompts import response_format
from opportunity_api.processing.schemas import SignalOntology
from opportunity_api.processing.service import pending_documents_query


def complete_ontology() -> dict:
    return {
        "is_pain": True,
        "pain_probability": 0.92,
        "confidence": 0.87,
        "pain_type": "manual_work",
        "industry": "Accounting",
        "subindustry": "Bookkeeping",
        "company_type": "Agency",
        "company_size": "10-50",
        "user_role": "Bookkeeper",
        "buyer_role": "Owner",
        "trigger": "Month end",
        "task": "Reconcile invoices",
        "current_workflow": ["Export", "Compare", "Correct"],
        "tools": ["Spreadsheet"],
        "inputs": ["Invoices"],
        "outputs": ["Reconciled ledger"],
        "manual_steps": ["Compare rows"],
        "frequency": "Monthly",
        "recurrence": "recurring",
        "time_spent": "four hours",
        "workaround": "Spreadsheet macros",
        "current_spend": "$500/month",
        "failure_consequence": "Late close",
        "revenue_impact": "Delayed billing",
        "risk_impact": "Incorrect books",
        "compliance_impact": "Audit exposure",
        "urgency": "high",
        "current_software": ["QuickBooks"],
        "desired_outcome": "Automatic reconciliation",
        "summary": "Manual invoice reconciliation delays close.",
        "evidence": [{"field": "time_spent", "quote": "four hours"}],
    }


def test_ontology_rejects_unknown_fields() -> None:
    payload = complete_ontology()
    assert SignalOntology.model_validate(payload).is_pain is True
    payload["invented"] = "not allowed"
    try:
        SignalOntology.model_validate(payload)
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown fields must be rejected")


def test_openrouter_contract_is_strict_and_routed() -> None:
    contract = response_format()
    assert contract["type"] == "json_schema"
    assert contract["json_schema"]["strict"] is True
    assert contract["json_schema"]["schema"]["additionalProperties"] is False
    settings = Settings(
        openrouter_default_model="model/primary",
        openrouter_fallback_models="model/backup-one, model/backup-two",
    )
    assert settings.model_route == ["model/primary", "model/backup-one", "model/backup-two"]


def test_failed_processing_retries_are_bounded() -> None:
    statement = str(pending_documents_query(10, include_model_retries=True, retry_limit=3))
    assert "signals.attempts <" in statement
