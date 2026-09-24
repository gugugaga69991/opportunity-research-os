import math
import uuid
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.config import Settings
from opportunity_api.decisions.scoring import WEIGHTS
from opportunity_api.models import (
    BusinessOutcome,
    CalibrationRun,
    CalibrationStatus,
    DecisionStatus,
    FreshnessAssessment,
    FreshnessStatus,
    OpportunityDecision,
    OpportunityHypothesis,
    OpportunityScore,
    OpportunityStatus,
    OutcomeEventType,
    ResearchCampaign,
    ResearchFinding,
    ResearchStatus,
    ScoreDimension,
    ScoringProfile,
    ValidationCampaign,
    ValidationVerdict,
)
from opportunity_api.research.service import create_research_campaign

OUTCOME_VALUES = {
    OutcomeEventType.outreach_positive: 0.20,
    OutcomeEventType.demo_booked: 0.35,
    OutcomeEventType.pricing_accepted: 0.50,
    OutcomeEventType.loi_signed: 0.65,
    OutcomeEventType.pilot_paid: 0.75,
    OutcomeEventType.customer_activated: 0.85,
    OutcomeEventType.customer_retained: 1.00,
    OutcomeEventType.customer_churned: 0.05,
    OutcomeEventType.mrr_observed: 0.80,
}
FRESHNESS_TOPICS = [
    "competitors",
    "pricing",
    "regulations",
    "product_launches",
    "reviews",
    "market_sentiment",
    "apis",
    "funding",
]


def pearson(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or len(left) != len(right):
        return 0.0
    left_mean, right_mean = fmean(left), fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    return numerator / (left_scale * right_scale) if left_scale and right_scale else 0.0


def proposed_weights(
    correlations: dict[ScoreDimension, float], max_delta: float
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    baseline = WEIGHTS
    values = {dimension: correlations.get(dimension, 0.0) for dimension in ScoreDimension}
    mean_correlation = fmean(values.values())
    centered = {dimension: value - mean_correlation for dimension, value in values.items()}
    scale = max((abs(value) for value in centered.values()), default=0.0)
    deltas = {
        dimension: (value / scale * max_delta if scale else 0.0)
        for dimension, value in centered.items()
    }
    proposed = {
        dimension.value: round(baseline[dimension] + deltas[dimension], 8)
        for dimension in ScoreDimension
    }
    rounding_drift = round(1.0 - sum(proposed.values()), 8)
    for dimension in ScoreDimension:
        candidate = proposed[dimension.value] + rounding_drift
        if abs(candidate - baseline[dimension]) <= max_delta:
            proposed[dimension.value] = round(candidate, 8)
            break
    recommendations = [
        {
            "dimension": dimension.value,
            "correlation": round(correlations.get(dimension, 0.0), 4),
            "current_weight": baseline[dimension],
            "proposed_weight": proposed[dimension.value],
            "delta": round(proposed[dimension.value] - baseline[dimension], 6),
        }
        for dimension in ScoreDimension
    ]
    return proposed, recommendations


def outcome_strength(
    outcomes: list[BusinessOutcome], validation: ValidationCampaign | None
) -> float | None:
    values = [OUTCOME_VALUES[item.event_type] for item in outcomes]
    for item in outcomes:
        if item.event_type == OutcomeEventType.mrr_observed and item.value_usd:
            values.append(min(1.0, 0.65 + math.log10(max(item.value_usd, 1)) / 20))
    if validation:
        values.extend(
            {
                ValidationVerdict.strong: [0.70],
                ValidationVerdict.mixed: [0.40],
                ValidationVerdict.weak: [0.10],
                ValidationVerdict.invalidated: [0.0],
                ValidationVerdict.pending: [],
            }[validation.verdict]
        )
    return max(values) if values else None


async def run_calibration(session: AsyncSession, settings: Settings) -> CalibrationRun:
    decisions = list(
        (
            await session.scalars(
                select(OpportunityDecision)
                .where(OpportunityDecision.status == DecisionStatus.completed)
                .order_by(OpportunityDecision.completed_at.desc())
            )
        ).all()
    )
    samples: list[tuple[OpportunityDecision, float, dict[ScoreDimension, float]]] = []
    seen: set[uuid.UUID] = set()
    for decision in decisions:
        if decision.opportunity_id in seen:
            continue
        outcomes = list(
            (
                await session.scalars(
                    select(BusinessOutcome).where(
                        BusinessOutcome.opportunity_id == decision.opportunity_id
                    )
                )
            ).all()
        )
        validation = await session.scalar(
            select(ValidationCampaign)
            .where(ValidationCampaign.decision_id == decision.id)
            .order_by(ValidationCampaign.updated_at.desc())
        )
        actual = outcome_strength(outcomes, validation)
        if actual is None:
            continue
        scores = list(
            (
                await session.scalars(
                    select(OpportunityScore).where(OpportunityScore.decision_id == decision.id)
                )
            ).all()
        )
        if len(scores) != len(ScoreDimension):
            continue
        samples.append((decision, actual, {item.dimension: item.score / 10 for item in scores}))
        seen.add(decision.opportunity_id)
    correlations = {
        dimension: pearson(
            [sample[2][dimension] for sample in samples],
            [sample[1] for sample in samples],
        )
        for dimension in ScoreDimension
    }
    proposed, recommendations = proposed_weights(
        correlations, settings.calibration_max_weight_delta
    )
    predictions = [sample[0].adjusted_score / 100 for sample in samples]
    actuals = [sample[1] for sample in samples]
    status = (
        CalibrationStatus.pending_review
        if len(samples) >= settings.calibration_min_samples
        else CalibrationStatus.insufficient_data
    )
    run = CalibrationRun(
        version=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        status=status,
        sample_count=len(samples),
        baseline_weights={key.value: value for key, value in WEIGHTS.items()},
        proposed_weights=proposed,
        metrics={
            "prediction_outcome_correlation": round(pearson(predictions, actuals), 4),
            "mean_prediction": round(fmean(predictions), 4) if predictions else 0.0,
            "mean_outcome": round(fmean(actuals), 4) if actuals else 0.0,
            "minimum_samples": settings.calibration_min_samples,
        },
        recommendations=recommendations,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def approve_calibration(
    session: AsyncSession, run: CalibrationRun, actor: str
) -> ScoringProfile:
    if run.status != CalibrationStatus.pending_review:
        raise ValueError("Only a calibration pending review can be approved")
    await session.execute(update(ScoringProfile).values(active=False))
    now = datetime.now(UTC)
    profile = ScoringProfile(
        calibration_run_id=run.id,
        version=f"calibrated-{run.version}",
        weights=run.proposed_weights,
        active=True,
        approved_by=actor,
        activated_at=now,
    )
    run.status = CalibrationStatus.approved
    run.approved_by = actor
    run.reviewed_at = now
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


def freshness_window_days(score: float, status: OpportunityStatus, settings: Settings) -> int:
    if status in {OpportunityStatus.pilot, OpportunityStatus.prototype}:
        return 14
    if score >= 80:
        return settings.freshness_top_opportunity_days
    return settings.freshness_default_days


def freshness_values(
    last_researched_at: datetime | None,
    score: float,
    status: OpportunityStatus,
    settings: Settings,
    now: datetime,
) -> tuple[float, datetime, float]:
    window = freshness_window_days(score, status, settings)
    baseline = last_researched_at or now
    age_days = max((now - baseline).total_seconds() / 86400, 0)
    freshness = max(0.0, min(1.0, 1 - age_days / window))
    priority = round((score / 100) * (1 - freshness), 4)
    return round(freshness, 4), baseline + timedelta(days=window), priority


async def assess_freshness(
    session: AsyncSession, opportunity: OpportunityHypothesis, settings: Settings
) -> FreshnessAssessment:
    now = datetime.now(UTC)
    decision = await session.scalar(
        select(OpportunityDecision)
        .where(OpportunityDecision.opportunity_id == opportunity.id)
        .order_by(OpportunityDecision.completed_at.desc())
    )
    latest = await session.scalar(
        select(ResearchCampaign)
        .where(
            ResearchCampaign.opportunity_id == opportunity.id,
            ResearchCampaign.status == ResearchStatus.completed,
        )
        .order_by(ResearchCampaign.completed_at.desc())
    )
    assessment = await session.scalar(
        select(FreshnessAssessment).where(FreshnessAssessment.opportunity_id == opportunity.id)
    )
    if assessment is None:
        assessment = FreshnessAssessment(
            opportunity_id=opportunity.id,
            next_check_at=now,
            due_topics=FRESHNESS_TOPICS,
            detected_changes=[],
        )
        session.add(assessment)
    last_researched = latest.completed_at if latest else None
    score = decision.adjusted_score if decision else opportunity.confidence * 100
    freshness, next_check, priority = freshness_values(
        last_researched, score, opportunity.status, settings, now
    )
    assessment.last_researched_at = last_researched
    assessment.freshness_score = freshness
    assessment.next_check_at = next_check
    assessment.priority = priority
    assessment.status = FreshnessStatus.due if next_check <= now else FreshnessStatus.current
    assessment.due_topics = FRESHNESS_TOPICS
    if assessment.active_campaign_id:
        active = await session.get(ResearchCampaign, assessment.active_campaign_id)
        if active and active.status == ResearchStatus.completed:
            changes = await detect_research_changes(session, active)
            assessment.detected_changes = changes
            assessment.requires_rescore = bool(changes)
            assessment.status = FreshnessStatus.changed if changes else FreshnessStatus.current
            assessment.active_campaign_id = None
            assessment.last_researched_at = active.completed_at
            assessment.freshness_score = 1.0
            assessment.next_check_at = now + timedelta(
                days=freshness_window_days(score, opportunity.status, settings)
            )
        elif active and active.status not in {ResearchStatus.failed, ResearchStatus.blocked}:
            assessment.status = FreshnessStatus.refreshing
        elif active:
            assessment.status = FreshnessStatus.failed
            assessment.error = active.error
    await session.commit()
    await session.refresh(assessment)
    return assessment


async def detect_research_changes(
    session: AsyncSession, campaign: ResearchCampaign
) -> list[dict[str, str]]:
    if not campaign.supersedes_campaign_id:
        return []
    changes: list[dict[str, str]] = []
    for lane in ("competition", "economics", "market", "distribution", "contradiction"):
        current = list(
            (
                await session.scalars(
                    select(ResearchFinding)
                    .where(
                        ResearchFinding.campaign_id == campaign.id,
                        ResearchFinding.lane == lane,
                        ResearchFinding.active.is_(True),
                    )
                    .order_by(ResearchFinding.finding_key)
                )
            ).all()
        )
        previous = list(
            (
                await session.scalars(
                    select(ResearchFinding)
                    .where(
                        ResearchFinding.campaign_id == campaign.supersedes_campaign_id,
                        ResearchFinding.lane == lane,
                        ResearchFinding.active.is_(True),
                    )
                    .order_by(ResearchFinding.finding_key)
                )
            ).all()
        )
        current_data = [item.structured_data for item in current]
        previous_data = [item.structured_data for item in previous]
        if current and previous and current_data != previous_data:
            changes.append({"lane": lane, "summary": current[0].summary})
    return changes


async def schedule_freshness_refresh(
    session: AsyncSession,
    assessment: FreshnessAssessment,
    settings: Settings,
) -> ResearchCampaign:
    if assessment.active_campaign_id:
        campaign = await session.get(ResearchCampaign, assessment.active_campaign_id)
        if campaign:
            return campaign
    previous = await session.scalar(
        select(ResearchCampaign)
        .where(
            ResearchCampaign.opportunity_id == assessment.opportunity_id,
            ResearchCampaign.status == ResearchStatus.completed,
        )
        .order_by(ResearchCampaign.completed_at.desc())
    )
    campaign = await create_research_campaign(
        session,
        assessment.opportunity_id,
        settings,
        version=datetime.now(UTC).strftime("refresh-%Y%m%dT%H%M%SZ"),
        campaign_type="freshness",
        supersedes_campaign_id=previous.id if previous else None,
    )
    assessment.active_campaign_id = campaign.id
    assessment.status = FreshnessStatus.refreshing
    await session.commit()
    return campaign


async def learning_metrics(session: AsyncSession) -> dict[str, int | float]:
    return {
        "outcomes": int(
            (await session.scalar(select(func.count()).select_from(BusinessOutcome))) or 0
        ),
        "calibration_runs": int(
            (await session.scalar(select(func.count()).select_from(CalibrationRun))) or 0
        ),
        "active_profiles": int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(ScoringProfile)
                    .where(ScoringProfile.active.is_(True))
                )
            )
            or 0
        ),
        "freshness_due": int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(FreshnessAssessment)
                    .where(FreshnessAssessment.status == FreshnessStatus.due)
                )
            )
            or 0
        ),
        "freshness_changed": int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(FreshnessAssessment)
                    .where(FreshnessAssessment.requires_rescore.is_(True))
                )
            )
            or 0
        ),
    }
