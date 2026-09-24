from collections.abc import Iterable
from dataclasses import dataclass

from opportunity_api.models import HypothesisReadiness, HypothesisTrack

EMPTY = {"", "unknown", "none", "n/a", "na", "not specified", "not available"}


@dataclass(frozen=True)
class GateResult:
    readiness: HypothesisReadiness
    passed: bool
    checks: dict[str, bool]
    confidence: float


def meaningful(value: object) -> bool:
    return isinstance(value, str) and value.strip().casefold() not in EMPTY


def first_value(records: list[dict], field: str) -> str:
    return next(
        (str(record.get(field, "")).strip() for record in records if meaningful(record.get(field))),
        "",
    )


def unique_values(records: list[dict], field: str, *, limit: int = 5) -> list[str]:
    values: list[str] = []
    for record in records:
        value = record.get(field)
        candidates: Iterable = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if meaningful(candidate) and str(candidate).strip() not in values:
                values.append(str(candidate).strip())
                if len(values) >= limit:
                    return values
    return values


def evaluate_gate(
    *,
    track: HypothesisTrack,
    signal_count: int,
    source_count: int,
    evidence_type_count: int,
    recurrence_score: float,
    buyer_identified: bool,
    economic_evidence_present: bool,
    corroboration_score: float,
    average_extraction_confidence: float,
    contradiction_count: int,
    has_confirming_pain_cluster: bool,
    minimum_signals: int,
    minimum_sources: int,
    minimum_evidence_types: int,
    minimum_recurrence: float,
) -> GateResult:
    checks = {
        "enough_signals": signal_count >= minimum_signals,
        "source_diversity": source_count >= minimum_sources,
        "evidence_diversity": evidence_type_count >= minimum_evidence_types,
        "recurring": recurrence_score >= minimum_recurrence,
        "buyer_identified": buyer_identified,
        "economic_evidence": economic_evidence_present,
        "contradiction_balance": contradiction_count < signal_count,
        "change_confirmed_by_pain": track == HypothesisTrack.pain_led
        or has_confirming_pain_cluster,
    }
    passed = all(checks.values())
    if passed:
        readiness = HypothesisReadiness.research_ready
    elif signal_count >= minimum_signals or source_count >= minimum_sources:
        readiness = HypothesisReadiness.corroborating
    else:
        readiness = HypothesisReadiness.preliminary
    contradiction_penalty = min(
        contradiction_count / max(signal_count + contradiction_count, 1), 0.4
    )
    confidence = min(
        1.0,
        max(
            0.0,
            0.55 * corroboration_score
            + 0.35 * average_extraction_confidence
            + (0.1 if passed else 0)
            - contradiction_penalty,
        ),
    )
    return GateResult(readiness, passed, checks, confidence)


def build_hypothesis_fields(
    track: HypothesisTrack,
    cluster_title: str,
    cluster_summary: str,
    records: list[dict],
) -> dict[str, str | dict]:
    industry = first_value(records, "industry")
    company_type = first_value(records, "company_type")
    company_size = first_value(records, "company_size")
    user_role = first_value(records, "user_role")
    buyer_role = first_value(records, "buyer_role")
    task = first_value(records, "task")
    trigger = first_value(records, "trigger")
    desired = first_value(records, "desired_outcome")
    summary = first_value(records, "summary") or cluster_summary
    workflow = unique_values(records, "current_workflow")
    manual_steps = unique_values(records, "manual_steps")
    workarounds = unique_values(records, "workaround")
    frequencies = unique_values(records, "frequency", limit=3)
    spends = unique_values(records, "current_spend", limit=3)
    costs = unique_values(records, "time_spent", limit=3)
    consequences = unique_values(records, "failure_consequence", limit=3)
    impacts = unique_values(records, "revenue_impact", limit=2)
    icp_parts = [part for part in (company_type, company_size, industry) if part]
    name_core = task or desired or cluster_title
    name = (
        f"{name_core} workflow for {industry}"
        if industry and industry.casefold() not in name_core.casefold()
        else name_core
    )
    action = f"achieve {desired}" if desired else f"automate {name_core.casefold()}"
    solution = f"A workflow system that helps {user_role or 'operators'} {action}."
    value = (
        f"Reduce the recurring manual work and failure risk in {task or cluster_title}"
        f" for {user_role or 'the operating team'}."
    )
    why_now = (
        cluster_summary
        if track == HypothesisTrack.change_led
        else "Recurring workflow evidence is appearing across the monitored sources."
    )
    return {
        "name": name[:300],
        "industry": industry,
        "icp": " / ".join(icp_parts),
        "user_role": user_role,
        "buyer_role": buyer_role,
        "core_workflow": " -> ".join(workflow) or task,
        "problem": summary,
        "frequency": "; ".join(frequencies),
        "current_workaround": "; ".join(workarounds),
        "economic_cost": "; ".join([*costs, *consequences, *impacts]),
        "existing_spend": "; ".join(spends),
        "why_now": why_now,
        "desired_outcome": desired,
        "solution_concept": solution,
        "value_proposition": value,
        "thesis": {
            "trigger": trigger,
            "task": task,
            "workflow": workflow,
            "manual_steps": manual_steps,
            "tools": unique_values(records, "tools"),
            "current_software": unique_values(records, "current_software"),
            "failure_consequences": consequences,
            "risk_impacts": unique_values(records, "risk_impact", limit=3),
            "compliance_impacts": unique_values(records, "compliance_impact", limit=3),
        },
    }
