import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.config import Settings
from opportunity_api.models import (
    BuildSpecification,
    CompetitorProfile,
    CustomerInterview,
    DecisionStatus,
    EvidenceCluster,
    FreshnessAssessment,
    OperationalAlert,
    OpportunityDecision,
    OpportunityHypothesis,
    OpportunityScore,
    OpportunityStatus,
    PortfolioSnapshot,
    PortfolioState,
    ResearchFinding,
    ScoreDimension,
    ValidationCampaign,
    ValidationExperiment,
    ValidationStatus,
    ValidationVerdict,
)


def portfolio_state(
    status: OpportunityStatus,
    score_velocity: float,
    competition_velocity: float,
    pain_velocity: float,
    invalidated: bool,
    threshold: float,
) -> tuple[PortfolioState, list[str]]:
    reasons: list[str] = []
    if invalidated or status == OpportunityStatus.killed:
        return PortfolioState.invalidated, ["Validation or lifecycle state invalidated the thesis."]
    if competition_velocity >= 1 and score_velocity < 0:
        return PortfolioState.saturating, [
            "Competition increased while the opportunity score fell."
        ]
    if score_velocity <= -threshold:
        reasons.append(f"Score fell {abs(score_velocity):.1f} points.")
        return PortfolioState.deteriorating, reasons
    if score_velocity >= threshold:
        reasons.append(f"Score rose {score_velocity:.1f} points.")
        return PortfolioState.improving, reasons
    if pain_velocity >= 1:
        reasons.append("Underlying pain-signal velocity is rising.")
        return PortfolioState.improving, reasons
    return PortfolioState.stable, ["No material score or market movement detected."]


async def _alert(
    session: AsyncSession,
    opportunity_id: uuid.UUID | None,
    key: str,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    payload: dict[str, Any],
) -> OperationalAlert:
    existing = await session.scalar(
        select(OperationalAlert).where(OperationalAlert.alert_key == key)
    )
    if existing:
        return existing
    item = OperationalAlert(
        opportunity_id=opportunity_id,
        alert_key=key,
        alert_type=alert_type,
        severity=severity,
        title=title,
        message=message,
        payload=payload,
    )
    session.add(item)
    return item


async def sync_portfolio(session: AsyncSession, settings: Settings) -> list[PortfolioSnapshot]:
    opportunities = list((await session.scalars(select(OpportunityHypothesis))).all())
    latest_rows: list[
        tuple[OpportunityHypothesis, OpportunityDecision, OpportunityDecision | None]
    ] = []
    for opportunity in opportunities:
        decisions = list(
            (
                await session.scalars(
                    select(OpportunityDecision)
                    .where(
                        OpportunityDecision.opportunity_id == opportunity.id,
                        OpportunityDecision.status == DecisionStatus.completed,
                    )
                    .order_by(OpportunityDecision.completed_at.desc())
                    .limit(2)
                )
            ).all()
        )
        if decisions:
            latest_rows.append(
                (opportunity, decisions[0], decisions[1] if len(decisions) > 1 else None)
            )
    latest_rows.sort(key=lambda row: row[1].adjusted_score, reverse=True)
    snapshots: list[PortfolioSnapshot] = []
    now = datetime.now(UTC)
    for rank, (opportunity, current, previous) in enumerate(latest_rows, 1):
        snapshot = await session.scalar(
            select(PortfolioSnapshot).where(PortfolioSnapshot.opportunity_id == opportunity.id)
        )
        prior_rank = snapshot.rank if snapshot else None
        previous_score = previous.adjusted_score if previous else current.adjusted_score
        score_velocity = current.adjusted_score - previous_score
        cluster = await session.get(EvidenceCluster, opportunity.origin_cluster_id)
        pain_velocity = cluster.velocity_30d if cluster else 0.0
        freshness = await session.scalar(
            select(FreshnessAssessment).where(FreshnessAssessment.opportunity_id == opportunity.id)
        )
        competition_velocity = float(
            sum(
                1
                for change in (freshness.detected_changes if freshness else [])
                if "competition" in str(change).lower() or "competitor" in str(change).lower()
            )
        )
        validation = await session.scalar(
            select(ValidationCampaign)
            .where(ValidationCampaign.opportunity_id == opportunity.id)
            .order_by(ValidationCampaign.updated_at.desc())
        )
        state, reasons = portfolio_state(
            opportunity.status,
            score_velocity,
            competition_velocity,
            pain_velocity,
            bool(validation and validation.verdict == ValidationVerdict.invalidated),
            settings.portfolio_score_change_threshold,
        )
        if snapshot is None:
            snapshot = PortfolioSnapshot(opportunity_id=opportunity.id, assessed_at=now)
            session.add(snapshot)
        snapshot.previous_score = previous_score
        snapshot.current_score = current.adjusted_score
        snapshot.score_velocity = score_velocity
        snapshot.competition_velocity = competition_velocity
        snapshot.pain_velocity = pain_velocity
        snapshot.market_timing_velocity = score_velocity
        snapshot.previous_rank = prior_rank
        snapshot.rank = rank
        snapshot.state = state
        snapshot.reasons = reasons
        snapshot.assessed_at = now
        snapshots.append(snapshot)
        if current.adjusted_score >= settings.portfolio_high_score_threshold:
            await _alert(
                session,
                opportunity.id,
                f"high-score:{current.id}",
                "high_score",
                "high",
                f"High-score opportunity: {opportunity.name}",
                f"{current.adjusted_score:.1f}/100 with {current.confidence_score:.0%} confidence.",
                {"score": current.adjusted_score, "decision_id": str(current.id)},
            )
        if abs(score_velocity) >= settings.portfolio_score_change_threshold:
            direction = "increased" if score_velocity > 0 else "decreased"
            await _alert(
                session,
                opportunity.id,
                f"score-change:{current.id}",
                "score_change",
                "high",
                f"Opportunity score {direction}",
                f"{opportunity.name}: {previous_score:.1f} → {current.adjusted_score:.1f}.",
                {"previous_score": previous_score, "current_score": current.adjusted_score},
            )
        if rank <= 10 and (prior_rank is None or prior_rank > 10):
            await _alert(
                session,
                opportunity.id,
                f"top10:{current.id}",
                "top_ten",
                "medium",
                f"Entered the top 10: {opportunity.name}",
                f"Portfolio rank is now #{rank}.",
                {"rank": rank},
            )
        if competition_velocity and freshness:
            await _alert(
                session,
                opportunity.id,
                f"competitor-change:{freshness.active_campaign_id}",
                "competitor_change",
                "high",
                f"Competitor change: {opportunity.name}",
                "Fresh research detected material competition changes; review before rescoring.",
                {"changes": freshness.detected_changes},
            )
        if validation and validation.status == ValidationStatus.completed:
            if validation.verdict in {
                ValidationVerdict.strong,
                ValidationVerdict.weak,
                ValidationVerdict.invalidated,
            }:
                await _alert(
                    session,
                    opportunity.id,
                    f"validation:{validation.id}:{validation.verdict.value}",
                    "validation_result",
                    "high",
                    f"Validation {validation.verdict.value}: {opportunity.name}",
                    f"Validation score {validation.validation_score:.1f}/100.",
                    {"campaign_id": str(validation.id), "verdict": validation.verdict.value},
                )
        if opportunity.status == OpportunityStatus.killed:
            await _alert(
                session,
                opportunity.id,
                f"killed:{opportunity.id}",
                "opportunity_killed",
                "critical",
                f"Opportunity killed: {opportunity.name}",
                "The evidence and failure memory remain available for future calibration.",
                {},
            )
    await session.commit()
    return snapshots


async def deliver_telegram(session: AsyncSession, settings: Settings) -> int:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return 0
    alerts = list(
        (
            await session.scalars(
                select(OperationalAlert)
                .where(OperationalAlert.telegram_delivered_at.is_(None))
                .order_by(OperationalAlert.created_at)
                .limit(20)
            )
        ).all()
    )
    delivered = 0
    async with httpx.AsyncClient(timeout=20) as client:
        for alert in alerts:
            try:
                response = await client.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                    json={
                        "chat_id": settings.telegram_chat_id,
                        "text": f"{alert.title}\n\n{alert.message}",
                    },
                )
                response.raise_for_status()
                alert.telegram_delivered_at = datetime.now(UTC)
                alert.delivery_error = None
                delivered += 1
            except httpx.HTTPError as exc:
                alert.delivery_error = str(exc)[:1000]
    await session.commit()
    return delivered


def interview_patterns(interviews: list[CustomerInterview]) -> dict[str, Any]:
    tools = Counter(
        tool.strip().lower() for item in interviews for tool in item.tools_used if tool.strip()
    )
    complaints = Counter(
        value.strip().lower() for item in interviews for value in item.complaints if value.strip()
    )
    return {
        "interview_count": len(interviews),
        "buyer_count": sum(item.buyer_or_user in {"buyer", "both"} for item in interviews),
        "budget_signal_count": sum(bool(item.budget_signal) for item in interviews),
        "specific_spend_count": sum(item.current_spend_usd is not None for item in interviews),
        "average_evidence_strength": round(
            sum(item.evidence_strength for item in interviews) / len(interviews), 3
        )
        if interviews
        else 0.0,
        "top_tools": tools.most_common(5),
        "top_complaints": complaints.most_common(5),
    }


def _markdown(spec: dict[str, Any]) -> str:
    lines = [f"# {spec['product_definition']['name']} — Build Specification", ""]
    for title, value in spec.items():
        if title == "product_definition":
            lines.extend(
                [
                    "## Product definition",
                    *[
                        f"- **{key.replace('_', ' ').title()}:** {item}"
                        for key, item in value.items()
                    ],
                    "",
                ]
            )
        elif isinstance(value, dict):
            lines.extend(
                [
                    f"## {title.replace('_', ' ').title()}",
                    *[
                        f"- **{key.replace('_', ' ').title()}:** {item}"
                        for key, item in value.items()
                    ],
                    "",
                ]
            )
        elif isinstance(value, list):
            lines.extend(
                [f"## {title.replace('_', ' ').title()}", *[f"- {item}" for item in value], ""]
            )
    return "\n".join(lines)


async def generate_build_spec(
    session: AsyncSession, opportunity: OpportunityHypothesis
) -> BuildSpecification:
    decision = await session.scalar(
        select(OpportunityDecision)
        .where(
            OpportunityDecision.opportunity_id == opportunity.id,
            OpportunityDecision.status == DecisionStatus.completed,
        )
        .order_by(OpportunityDecision.completed_at.desc())
    )
    validation = await session.scalar(
        select(ValidationCampaign)
        .where(ValidationCampaign.opportunity_id == opportunity.id)
        .order_by(ValidationCampaign.updated_at.desc())
    )
    if not decision or not validation or validation.verdict != ValidationVerdict.strong:
        raise ValueError("A completed strong validation campaign is required before build handoff")
    existing = await session.scalar(
        select(BuildSpecification).where(
            BuildSpecification.opportunity_id == opportunity.id,
            BuildSpecification.decision_id == decision.id,
            BuildSpecification.validation_campaign_id == validation.id,
        )
    )
    if existing:
        return existing
    findings = list(
        (
            await session.scalars(
                select(ResearchFinding).where(
                    ResearchFinding.opportunity_id == opportunity.id,
                    ResearchFinding.active.is_(True),
                )
            )
        ).all()
    )
    competitors = list(
        (
            await session.scalars(
                select(CompetitorProfile).where(
                    CompetitorProfile.opportunity_id == opportunity.id,
                    CompetitorProfile.active.is_(True),
                )
            )
        ).all()
    )
    interviews = list(
        (
            await session.scalars(
                select(CustomerInterview).where(CustomerInterview.opportunity_id == opportunity.id)
            )
        ).all()
    )
    experiments = list(
        (
            await session.scalars(
                select(ValidationExperiment).where(
                    ValidationExperiment.campaign_id == validation.id
                )
            )
        ).all()
    )
    scores = list(
        (
            await session.scalars(
                select(OpportunityScore).where(OpportunityScore.decision_id == decision.id)
            )
        ).all()
    )
    patterns = interview_patterns(interviews)
    buildability = next(
        (item.score for item in scores if item.dimension == ScoreDimension.buildability), 0.0
    )
    research_text = " ".join(str(item.structured_data) for item in findings).lower()
    data_accessible = any(term in research_text for term in ("api", "csv", "export", "webhook"))
    product_name = opportunity.solution_concept or opportunity.name
    spec: dict[str, Any] = {
        "product_definition": {
            "name": product_name,
            "icp": opportunity.icp,
            "primary_user": opportunity.user_role,
            "buyer": opportunity.buyer_role,
            "job_to_be_done": opportunity.core_workflow,
            "promise": opportunity.value_proposition or opportunity.desired_outcome,
            "differentiator": (
                f"Resolve {opportunity.problem} with a narrower workflow than "
                f"{len(competitors)} mapped alternatives."
            ),
        },
        "mvp_scope": {
            "must_have": [
                "Connect or import the minimum required customer data",
                "Detect the target workflow problem",
                "Show evidence for every recommended action",
                "Produce the measurable promised outcome",
                "Retain an audit trail",
            ],
            "should_have": ["Recurring monitoring", "Operator review queue", "Outcome reporting"],
            "later": ["Secondary personas", "Adjacent workflows", "Advanced customization"],
            "do_not_build": [
                "Unvalidated adjacent features",
                "Autonomous irreversible actions",
                "A broad all-in-one platform",
            ],
        },
        "user_stories": [
            (
                f"As {opportunity.user_role}, I want to {opportunity.core_workflow}, "
                f"so I can {opportunity.desired_outcome}."
            ),
            (
                f"As {opportunity.buyer_role}, I want measurable proof of value "
                "before expanding usage."
            ),
        ],
        "product_workflow": [
            "Sign up",
            "Connect or import data",
            "Analyze historical data",
            "Reveal first verified result",
            "Review and act",
            "Run recurring automation",
            "Report realized value",
        ],
        "technical_requirements": [
            "Role-based authentication",
            "Encrypted integration credentials",
            "Idempotent background jobs",
            "Evidence-linked AI outputs",
            "Deterministic financial calculations",
            "Human review for consequential actions",
            "Immutable audit logs",
            "Usage and cost telemetry",
        ],
        "initial_data_model": [
            "workspace",
            "user",
            "data_connection",
            "source_record",
            "analysis_run",
            "finding",
            "recommended_action",
            "review_decision",
            "realized_outcome",
            "audit_event",
        ],
        "integration_plan": {
            "required": list(dict.fromkeys(tool for item in interviews for tool in item.tools_used))
            or ["CSV import for pilot"],
            "fallback": "CSV upload and manual export",
            "risk": "Verify API access, commercial rights, and rate limits before committing.",
        },
        "ai_architecture": {
            "use_ai_for": [
                "Unstructured-data classification",
                "Explanation drafts",
                "Exception prioritization",
            ],
            "deterministic_for": [
                "Identity, permissions, arithmetic, thresholds, billing, and final totals"
            ],
            "human_review": [
                "Low-confidence findings",
                "Irreversible actions",
                "Customer-facing high-impact decisions",
            ],
        },
        "onboarding": {
            "steps": [
                "Choose pilot workflow",
                "Connect one source",
                "Import a representative historical sample",
                "Confirm mappings",
                "Review first result",
            ],
            "time_to_first_value": "One working session",
            "demo_mode": "Use a redacted sample dataset when production access is delayed.",
        },
        "pricing_hypothesis": {
            "pilot": "Use the strongest validated price or a paid design-partner fee.",
            "production": opportunity.existing_spend
            or "Price against verified labor, revenue, or risk value.",
            "evidence": (
                f"{patterns['specific_spend_count']} interviews recorded specific current spend."
            ),
        },
        "demo_script": [
            "Import the last 90 days",
            "Detect the highest-value anomalies",
            "Open one finding and inspect its evidence",
            "Take the recommended action",
            "Show recovered value or time saved",
        ],
        "outreach_positioning": [
            f"Pain: {opportunity.problem}",
            f"ROI: {opportunity.value_proposition}",
            f"Trigger: {opportunity.why_now}",
            "CTA: test one historical dataset and review the result together",
        ],
        "validation_to_build_checklist": {
            "real_pain": patterns["interview_count"] > 0,
            "recurring_workflow": opportunity.recurring_problem,
            "buyer_identified": opportunity.buyer_identified,
            "existing_spend": bool(opportunity.existing_spend)
            or patterns["specific_spend_count"] > 0,
            "competition_mapped": bool(competitors),
            "data_accessible": data_accessible,
            "integration_feasible": buildability >= 6,
            "pricing_tested": any(
                item.experiment_type.value == "pricing" and item.status.value == "completed"
                for item in experiments
            ),
            "strong_validation": True,
        },
        "execution_plan": {
            "days_1_30": (
                "Build the narrow workflow, connect pilot data, and onboard design partners."
            ),
            "days_31_60": (
                "Measure activation, harden automation, fix onboarding, and retest pricing."
            ),
            "days_61_90": (
                "Measure retention and value, expand outbound, then scale, pivot, or stop."
            ),
        },
    }
    version = f"{decision.version}-{validation.version}-{validation.id.hex[:8]}"
    build = BuildSpecification(
        opportunity_id=opportunity.id,
        decision_id=decision.id,
        validation_campaign_id=validation.id,
        version=version,
        content=spec,
        markdown=_markdown(spec),
        source_manifest={
            "decision_id": str(decision.id),
            "validation_campaign_id": str(validation.id),
            "finding_ids": [str(item.id) for item in findings],
            "interview_ids": [str(item.id) for item in interviews],
            "competitor_ids": [str(item.id) for item in competitors],
        },
    )
    session.add(build)
    await session.commit()
    await session.refresh(build)
    return build
