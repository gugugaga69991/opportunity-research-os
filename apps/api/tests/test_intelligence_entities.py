import uuid

from opportunity_api.intelligence.entities import (
    cluster_descriptors,
    entities_from_document_context,
    entities_from_ontology,
    normalize_entity_value,
    recurrence_strength,
)
from opportunity_api.intelligence.schemas import EntityRead
from opportunity_api.models import ClusterType, EntityType, KnowledgeEntity


def ontology() -> dict:
    return {
        "industry": "Accounting",
        "subindustry": "Bookkeeping",
        "company_type": "Agency",
        "company_size": "10-50",
        "user_role": "Bookkeeper",
        "buyer_role": "Owner",
        "trigger": "Month end",
        "task": "Reconcile invoices",
        "pain_type": "Manual work",
        "recurrence": "Recurring",
        "frequency": "Every week",
        "workaround": "Spreadsheet macros",
        "desired_outcome": "Automatic reconciliation",
        "tools": ["Excel", "Excel"],
        "current_software": ["QuickBooks"],
        "inputs": ["Invoices"],
        "outputs": ["Reconciled ledger"],
        "current_workflow": ["Export transactions", "Compare rows"],
        "manual_steps": ["Correct mismatches"],
        "summary": "Bookkeepers manually reconcile invoices at month end.",
    }


def test_entity_normalization_and_materialization() -> None:
    assert normalize_entity_value("  QuickBooks™  ") == "quickbooks"
    entities = entities_from_ontology(ontology(), 0.87)
    excel = [item for item in entities if item.normalized_value == "excel"]
    assert len(excel) == 1
    assert excel[0].entity_type == EntityType.tool
    assert excel[0].relation == "uses_tool"
    assert {item.relation for item in entities} >= {
        "industry",
        "user_role",
        "buyer_role",
        "task",
        "manual_step",
    }
    companies = entities_from_document_context(
        {"employer": {"name": "Ledger Labs"}, "companyName": "Ledger Labs"}
    )
    assert len(companies) == 1
    assert companies[0].entity_type == EntityType.company
    assert companies[0].normalized_value == "ledger labs"


def test_descriptors_cover_pain_workflow_and_change_tracks() -> None:
    descriptors = cluster_descriptors(
        ontology(),
        is_pain=True,
        source_type="regulatory_notices",
        document_type="regulatory_notice",
        fallback_title="New reporting mandate",
    )
    assert [item.cluster_type for item in descriptors] == [
        ClusterType.pain,
        ClusterType.workflow,
        ClusterType.change,
    ]
    assert all(len(item.cluster_key) == 64 for item in descriptors)
    assert descriptors[0].recurrence_score == 0.85


def test_fingerprints_are_stable_across_case_and_spacing() -> None:
    first = cluster_descriptors(
        ontology(),
        is_pain=True,
        source_type="forum",
        document_type="post",
        fallback_title="Complaint",
    )
    changed = ontology()
    changed["industry"] = "  accounting "
    changed["task"] = "RECONCILE INVOICES"
    second = cluster_descriptors(
        changed,
        is_pain=True,
        source_type="forum",
        document_type="post",
        fallback_title="Complaint",
    )
    assert first[0].cluster_key == second[0].cluster_key
    assert recurrence_strength({"frequency": "one-time", "recurrence": ""}) == 0.1


def test_entity_api_contract_maps_database_metadata() -> None:
    entity = KnowledgeEntity(
        id=uuid.uuid4(),
        entity_type=EntityType.software,
        display_value="QuickBooks",
        normalized_value="quickbooks",
        aliases=[],
        metadata_={"category": "accounting"},
    )
    payload = EntityRead.model_validate(entity).model_dump()
    assert payload["metadata"] == {"category": "accounting"}
