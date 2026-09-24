import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.config import Settings
from opportunity_api.models import (
    DecisionDisposition,
    DecisionStatus,
    ExperimentStatus,
    ExperimentType,
    FailureMemory,
    OpportunityDecision,
    OpportunityHypothesis,
    OpportunityStatus,
    ValidationCampaign,
    ValidationExperiment,
    ValidationResult,
    ValidationStatus,
    ValidationVerdict,
)
from opportunity_api.opportunities.service import transition_opportunity

VALIDATION_VERSION = "1.0.0"
METRIC_KEYS = {
    "sample_size",
    "delivered",
    "replies",
    "positive_replies",
    "pain_confirmations",
    "calls_booked",
    "pricing_acceptances",
    "lois",
    "paid_pilots",
    "deposits",
    "pre_sales",
    "revenue_usd",
    "bounces",
    "unsubscribes",
    "invalidated",
}
PAID_KEYS = ("paid_pilots", "deposits", "pre_sales")


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    return max(float(value or 0), 0.0)


def aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    aggregate = {key: 0.0 for key in METRIC_KEYS}
    for row in rows:
        for key in METRIC_KEYS:
            aggregate[key] += _number(row.get(key))
    delivered = aggregate["delivered"] or aggregate["sample_size"]
    replies = aggregate["replies"]
    aggregate.update(
        {
            "reply_rate": replies / delivered if delivered else 0.0,
            "positive_reply_rate": aggregate["positive_replies"] / delivered if delivered else 0.0,
            "pain_confirmation_rate": aggregate["pain_confirmations"] / aggregate["sample_size"]
            if aggregate["sample_size"]
            else 0.0,
            "pricing_acceptance_rate": aggregate["pricing_acceptances"] / replies
            if replies
            else 0.0,
            "bounce_rate": aggregate["bounces"] / (delivered + aggregate["bounces"])
            if delivered + aggregate["bounces"]
            else 0.0,
        }
    )
    return aggregate


def evaluate_metrics(
    metrics: dict[str, float], settings: Settings
) -> tuple[ValidationVerdict, float, list[str]]:
    paid = sum(metrics.get(key, 0) for key in PAID_KEYS)
    invalidated = metrics.get("invalidated", 0) > 0
    sample = metrics.get("delivered", 0) or metrics.get("sample_size", 0)
    positive_rate = metrics.get("positive_reply_rate", 0)
    pain = metrics.get("pain_confirmations", 0)
    pricing = metrics.get("pricing_acceptances", 0) + metrics.get("lois", 0)
    reasons: list[str] = []
    score = min(pain / max(settings.validation_min_pain_confirmations, 1), 1) * 30
    score += min(positive_rate / max(settings.validation_strong_positive_rate, 0.001), 1) * 25
    score += min(pricing, 1) * 20
    score += min(metrics.get("calls_booked", 0) / 3, 1) * 10
    score += min(paid, 1) * 15
    if invalidated:
        return (
            ValidationVerdict.invalidated,
            0.0,
            ["A recorded outcome explicitly invalidated the thesis."],
        )
    if paid:
        return ValidationVerdict.strong, max(score, 90.0), ["A prospect made a paid commitment."]
    sufficient = sample >= settings.validation_min_outreach_sample
    if (
        sufficient
        and positive_rate >= settings.validation_strong_positive_rate
        and pain >= settings.validation_min_pain_confirmations
        and pricing
    ):
        reasons.append("Precommitted outreach, pain, and pricing thresholds were met.")
        return ValidationVerdict.strong, score, reasons
    if sufficient and (positive_rate < settings.validation_weak_positive_rate or pain == 0):
        reasons.append("The minimum sample completed without enough buyer or pain confirmation.")
        return ValidationVerdict.weak, score, reasons
    if sufficient or pain >= settings.validation_min_pain_confirmations or pricing:
        reasons.append("Results are meaningful but do not meet every strong-validation threshold.")
        return ValidationVerdict.mixed, score, reasons
    reasons.append("The precommitted sample has not been reached; results remain preliminary.")
    return ValidationVerdict.pending, score, reasons


def experiment_specs(
    opportunity: OpportunityHypothesis, settings: Settings
) -> list[dict[str, Any]]:
    audience = f"{opportunity.buyer_role} at {opportunity.icp}".strip()
    pain = opportunity.problem or opportunity.core_workflow
    value = opportunity.value_proposition or opportunity.solution_concept
    return [
        {
            "experiment_type": ExperimentType.pain_interview,
            "hypothesis": (
                f"Because evidence shows recurring {pain}, at least half of interviewed "
                "buyers will confirm the problem and its recurring cost."
            ),
            "audience": audience,
            "channel": "interview",
            "positioning_angle": "problem discovery",
            "sample_target": 10,
            "success_criteria": {
                "primary_metric": "pain_confirmation_rate",
                "threshold": 0.5,
                "guardrail": "leading_questions",
                "minimum_sample": 10,
            },
            "execution_brief": {
                "questions": [
                    "How do you handle this today?",
                    "How often does it happen?",
                    "What time or money does it consume?",
                    "Are you actively trying to fix it?",
                ],
                "instruction": "Ask about current behavior before presenting a solution.",
            },
        },
        {
            "experiment_type": ExperimentType.cold_email,
            "hypothesis": (
                f"Because {pain} is recurring and costly, a specific {value} message will "
                "produce at least the configured positive-reply rate from the target buyer."
            ),
            "audience": audience,
            "channel": "manual_outreach",
            "positioning_angle": "measurable operational outcome",
            "sample_target": settings.validation_min_outreach_sample,
            "success_criteria": {
                "primary_metric": "positive_reply_rate",
                "threshold": settings.validation_strong_positive_rate,
                "guardrails": {"bounce_rate": 0.05, "unsubscribe_rate": 0.02},
                "minimum_sample": settings.validation_min_outreach_sample,
                "do_not_stop_early": True,
            },
            "execution_brief": {
                "variants": ["labor saved", "revenue recovered", "risk reduced"],
                "instruction": (
                    "Use equal cohorts and change only the positioning angle; "
                    "record each cohort separately."
                ),
            },
        },
        {
            "experiment_type": ExperimentType.pricing,
            "hypothesis": (
                "Because the workflow has verified economic cost, at least one qualified "
                "buyer will accept a concrete paid price discussion."
            ),
            "audience": audience,
            "channel": "sales_conversation",
            "positioning_angle": "price against verified cost",
            "price_point_usd": 699.0,
            "sample_target": 5,
            "success_criteria": {
                "primary_metric": "pricing_acceptances",
                "threshold": 1,
                "guardrail": "qualified_buyer_only",
                "minimum_sample": 5,
            },
            "execution_brief": {
                "price_points_usd": [299, 699, 1500, 3000],
                "instruction": (
                    "Test one price per comparable cohort; do not replace payment intent "
                    "with survey enthusiasm."
                ),
            },
        },
        {
            "experiment_type": ExperimentType.paid_commitment,
            "hypothesis": (
                "Because the proposed outcome has urgent business value, at least one "
                "qualified buyer will make a deposit, buy a pilot, or sign a commercial commitment."
            ),
            "audience": audience,
            "channel": "founder_sales",
            "positioning_angle": "paid pilot",
            "sample_target": 1,
            "success_criteria": {
                "primary_metric": "paid_pilots",
                "threshold": 1,
                "accepted_equivalents": ["deposits", "pre_sales"],
                "guardrail": "real_buyer_commitment",
            },
            "execution_brief": {
                "offers": ["paid pilot", "deposit", "design partnership with fee", "pre-sale"],
                "instruction": (
                    "Store proof and commercial terms; verbal interest is not a paid signal."
                ),
            },
        },
    ]


async def create_validation_campaign(
    session: AsyncSession, decision_id: uuid.UUID, settings: Settings
) -> ValidationCampaign:
    existing = await session.scalar(
        select(ValidationCampaign).where(
            ValidationCampaign.decision_id == decision_id,
            ValidationCampaign.version == VALIDATION_VERSION,
        )
    )
    if existing:
        return existing
    decision = await session.get(OpportunityDecision, decision_id)
    if decision is None:
        raise LookupError(f"Decision {decision_id} does not exist")
    if (
        decision.status != DecisionStatus.completed
        or decision.disposition != DecisionDisposition.advance
    ):
        raise ValueError("Only completed advance decisions can enter validation")
    opportunity = await session.get(OpportunityHypothesis, decision.opportunity_id)
    if opportunity is None:
        raise LookupError(f"Opportunity {decision.opportunity_id} does not exist")
    if opportunity.status not in {OpportunityStatus.thesis_ready, OpportunityStatus.validating}:
        raise ValueError("Opportunity must be thesis-ready before validation")
    specs = experiment_specs(opportunity, settings)
    campaign = ValidationCampaign(
        opportunity_id=opportunity.id,
        decision_id=decision.id,
        version=VALIDATION_VERSION,
        status=ValidationStatus.planned,
        verdict=ValidationVerdict.pending,
        experiment_count=len(specs),
        summary={
            "external_execution": "manual",
            "decision_rule": (
                "Paid commitment wins; otherwise precommitted pain, outreach, and pricing "
                "thresholds apply."
            ),
        },
    )
    session.add(campaign)
    await session.flush()
    for spec in specs:
        session.add(
            ValidationExperiment(
                campaign_id=campaign.id, status=ExperimentStatus.ready, aggregate={}, **spec
            )
        )
    if opportunity.status == OpportunityStatus.thesis_ready:
        await transition_opportunity(
            session,
            opportunity,
            OpportunityStatus.validating,
            "Real-world validation campaign planned.",
            "system",
        )
    else:
        await session.commit()
    await session.refresh(campaign)
    return campaign


async def record_result(
    session: AsyncSession, experiment: ValidationExperiment, payload: Any, settings: Settings
) -> ValidationResult:
    existing = await session.scalar(
        select(ValidationResult).where(
            ValidationResult.experiment_id == experiment.id,
            ValidationResult.result_key == payload.result_key,
        )
    )
    if existing:
        return existing
    metrics = {key: _number(value) for key, value in payload.metrics.items() if key in METRIC_KEYS}
    result = ValidationResult(
        experiment_id=experiment.id,
        result_key=payload.result_key,
        source=payload.source,
        metrics=metrics,
        qualitative_feedback=payload.qualitative_feedback,
        evidence_urls=payload.evidence_urls,
        interpretation=payload.interpretation,
        observed_at=payload.observed_at or datetime.now(UTC),
    )
    session.add(result)
    if experiment.status in {ExperimentStatus.planned, ExperimentStatus.ready}:
        experiment.status = ExperimentStatus.running
        experiment.started_at = datetime.now(UTC)
    await session.flush()
    await evaluate_campaign(session, experiment.campaign_id, settings)
    await session.commit()
    await session.refresh(result)
    return result


async def evaluate_campaign(
    session: AsyncSession, campaign_id: uuid.UUID, settings: Settings
) -> ValidationCampaign:
    campaign = await session.get(ValidationCampaign, campaign_id)
    if campaign is None:
        raise LookupError(f"Validation campaign {campaign_id} does not exist")
    experiments = list(
        (
            await session.scalars(
                select(ValidationExperiment).where(ValidationExperiment.campaign_id == campaign.id)
            )
        ).all()
    )
    all_metrics: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    completed = 0
    has_results = False
    for experiment in experiments:
        rows = list(
            (
                await session.scalars(
                    select(ValidationResult).where(ValidationResult.experiment_id == experiment.id)
                )
            ).all()
        )
        has_results = has_results or bool(rows)
        aggregate = aggregate_metrics([row.metrics for row in rows])
        experiment.aggregate = aggregate
        all_metrics.append(aggregate)
        observed = aggregate.get("delivered", 0) or aggregate.get("sample_size", 0)
        commitment = sum(aggregate.get(key, 0) for key in (*PAID_KEYS, "lois"))
        if observed >= experiment.sample_target or commitment or aggregate.get("invalidated", 0):
            experiment.status = ExperimentStatus.completed
            experiment.completed_at = now
            completed += 1
    aggregate = aggregate_metrics(all_metrics)
    verdict, score, reasons = evaluate_metrics(aggregate, settings)
    campaign.validation_score = round(score, 2)
    campaign.verdict = verdict
    campaign.completed_experiment_count = completed
    campaign.started_at = campaign.started_at or (now if has_results else None)
    if verdict in {
        ValidationVerdict.strong,
        ValidationVerdict.weak,
        ValidationVerdict.invalidated,
    }:
        campaign.status = ValidationStatus.completed
    elif has_results:
        campaign.status = ValidationStatus.running
    else:
        campaign.status = ValidationStatus.planned
    campaign.completed_at = now if campaign.status == ValidationStatus.completed else None
    campaign.summary = {
        **campaign.summary,
        "aggregate": aggregate,
        "reasons": reasons,
        "preliminary": verdict == ValidationVerdict.pending,
    }
    opportunity = await session.get(OpportunityHypothesis, campaign.opportunity_id)
    if (
        opportunity
        and verdict == ValidationVerdict.strong
        and sum(aggregate.get(key, 0) for key in PAID_KEYS)
        and opportunity.status == OpportunityStatus.validating
    ):
        await transition_opportunity(
            session,
            opportunity,
            OpportunityStatus.pilot,
            "Paid validation commitment recorded.",
            "system",
        )
    elif (
        opportunity
        and verdict in {ValidationVerdict.weak, ValidationVerdict.invalidated}
        and opportunity.status == OpportunityStatus.validating
    ):
        await _remember_failure(session, campaign, verdict, aggregate, reasons)
        await transition_opportunity(
            session, opportunity, OpportunityStatus.watchlist, reasons[0], "system"
        )
    await session.flush()
    return campaign


async def _remember_failure(
    session: AsyncSession,
    campaign: ValidationCampaign,
    verdict: ValidationVerdict,
    actual: dict,
    reasons: list[str],
) -> None:
    reason = reasons[0]
    key = hashlib.sha256(f"{verdict.value}:{reason}".encode()).hexdigest()
    existing = await session.scalar(
        select(FailureMemory).where(
            FailureMemory.campaign_id == campaign.id, FailureMemory.reason_key == key
        )
    )
    if not existing:
        session.add(
            FailureMemory(
                opportunity_id=campaign.opportunity_id,
                campaign_id=campaign.id,
                reason_key=key,
                category="buyer_validation",
                reason=reason,
                predicted={"decision_id": str(campaign.decision_id)},
                actual=actual,
                reusable_lesson=(
                    "Use this outcome to calibrate future ranking and validation assumptions."
                ),
            )
        )


def validation_ready_decisions_query(limit: int) -> Select[tuple[OpportunityDecision]]:
    return (
        select(OpportunityDecision)
        .outerjoin(ValidationCampaign, ValidationCampaign.decision_id == OpportunityDecision.id)
        .where(
            OpportunityDecision.status == DecisionStatus.completed,
            OpportunityDecision.disposition == DecisionDisposition.advance,
            ValidationCampaign.id.is_(None),
        )
        .order_by(OpportunityDecision.completed_at)
        .limit(limit)
    )


async def validation_metrics(session: AsyncSession) -> dict[str, int]:
    statuses = dict(
        (
            await session.execute(
                select(ValidationCampaign.status, func.count()).group_by(ValidationCampaign.status)
            )
        ).all()
    )
    verdicts = dict(
        (
            await session.execute(
                select(ValidationCampaign.verdict, func.count()).group_by(
                    ValidationCampaign.verdict
                )
            )
        ).all()
    )
    paid = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(ValidationExperiment)
                .where(
                    ValidationExperiment.experiment_type == ExperimentType.paid_commitment,
                    ValidationExperiment.status == ExperimentStatus.completed,
                )
            )
        )
        or 0
    )
    failures = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(FailureMemory)
                .where(FailureMemory.active.is_(True))
            )
        )
        or 0
    )
    return {
        "total": sum(statuses.values()),
        "planned": statuses.get(ValidationStatus.planned, 0),
        "running": statuses.get(ValidationStatus.running, 0),
        "completed": statuses.get(ValidationStatus.completed, 0),
        "strong": verdicts.get(ValidationVerdict.strong, 0),
        "mixed": verdicts.get(ValidationVerdict.mixed, 0),
        "weak": verdicts.get(ValidationVerdict.weak, 0),
        "invalidated": verdicts.get(ValidationVerdict.invalidated, 0),
        "paid_signals": paid,
        "failure_memories": failures,
    }
