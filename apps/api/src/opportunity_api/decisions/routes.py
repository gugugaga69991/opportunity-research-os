import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.collection.queue import enqueue_job
from opportunity_api.database import get_session
from opportunity_api.decisions.schemas import (
    DecisionBackfill,
    DecisionDetail,
    DecisionMetrics,
    DecisionRead,
    RiskRead,
    ScoreRead,
)
from opportunity_api.decisions.service import (
    create_decision,
    scoring_ready_campaigns_query,
)
from opportunity_api.models import (
    DecisionDisposition,
    DecisionStatus,
    OpportunityDecision,
    OpportunityRisk,
    OpportunityScore,
    ResearchCampaign,
)

router = APIRouter(prefix="/decisions", tags=["opportunity decisions"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/campaigns/{campaign_id}/score", status_code=202)
async def score_campaign(campaign_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    if await session.get(ResearchCampaign, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Research campaign not found")
    try:
        decision = await create_decision(session, campaign_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    job_id = await enqueue_job("analyze_opportunity_decision", str(decision.id))
    return {"status": "queued", "decision_id": str(decision.id), "job_id": job_id or ""}


@router.post("/backfill", status_code=202)
async def backfill(payload: DecisionBackfill, session: SessionDep) -> dict[str, int]:
    campaigns = list((await session.scalars(scoring_ready_campaigns_query(payload.limit))).all())
    for campaign in campaigns:
        await enqueue_job("create_opportunity_decision", str(campaign.id))
    return {"queued": len(campaigns)}


@router.post("/{decision_id}/analyze", status_code=202)
async def analyze(decision_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    decision = await session.get(OpportunityDecision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Opportunity decision not found")
    if decision.status == DecisionStatus.completed:
        raise HTTPException(status_code=409, detail="Opportunity decision is already complete")
    job_id = await enqueue_job("analyze_opportunity_decision", str(decision.id))
    return {"status": "queued", "decision_id": str(decision.id), "job_id": job_id or ""}


@router.get("", response_model=list[DecisionRead])
async def list_decisions(
    session: SessionDep,
    status: DecisionStatus | None = None,
    disposition: DecisionDisposition | None = None,
    opportunity_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OpportunityDecision]:
    statement = (
        select(OpportunityDecision)
        .order_by(
            OpportunityDecision.adjusted_score.desc(),
            OpportunityDecision.confidence_score.desc(),
        )
        .limit(limit)
    )
    if status:
        statement = statement.where(OpportunityDecision.status == status)
    if disposition:
        statement = statement.where(OpportunityDecision.disposition == disposition)
    if opportunity_id:
        statement = statement.where(OpportunityDecision.opportunity_id == opportunity_id)
    return list((await session.scalars(statement)).all())


@router.get("/metrics", response_model=DecisionMetrics)
async def metrics(session: SessionDep) -> dict[str, int | float]:
    status_rows = dict(
        (
            await session.execute(
                select(OpportunityDecision.status, func.count()).group_by(
                    OpportunityDecision.status
                )
            )
        ).all()
    )
    disposition_rows = dict(
        (
            await session.execute(
                select(OpportunityDecision.disposition, func.count())
                .where(OpportunityDecision.disposition.is_not(None))
                .group_by(OpportunityDecision.disposition)
            )
        ).all()
    )
    averages = (
        await session.execute(
            select(
                func.coalesce(func.avg(OpportunityDecision.adjusted_score), 0.0),
                func.coalesce(func.sum(OpportunityDecision.cost_usd), 0.0),
            ).where(OpportunityDecision.status == DecisionStatus.completed)
        )
    ).one()
    return {
        "total": sum(status_rows.values()),
        "awaiting_analysis": status_rows.get(DecisionStatus.awaiting_analysis, 0),
        "completed": status_rows.get(DecisionStatus.completed, 0),
        "failed": status_rows.get(DecisionStatus.failed, 0),
        "advance": disposition_rows.get(DecisionDisposition.advance, 0),
        "watchlist": disposition_rows.get(DecisionDisposition.watchlist, 0),
        "killed": disposition_rows.get(DecisionDisposition.kill, 0),
        "hard_kills": int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(OpportunityDecision)
                    .where(OpportunityDecision.hard_kill_triggered.is_(True))
                )
            )
            or 0
        ),
        "average_adjusted_score": float(averages[0]),
        "total_cost_usd": float(averages[1]),
    }


@router.get("/{decision_id}", response_model=DecisionDetail)
async def get_decision(decision_id: uuid.UUID, session: SessionDep) -> DecisionDetail:
    decision = await session.get(OpportunityDecision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Opportunity decision not found")
    scores = list(
        (
            await session.scalars(
                select(OpportunityScore)
                .where(OpportunityScore.decision_id == decision.id)
                .order_by(OpportunityScore.weight.desc())
            )
        ).all()
    )
    risks = list(
        (
            await session.scalars(
                select(OpportunityRisk)
                .where(
                    OpportunityRisk.decision_id == decision.id,
                    OpportunityRisk.active.is_(True),
                )
                .order_by(OpportunityRisk.severity.desc())
            )
        ).all()
    )
    return DecisionDetail(
        **DecisionRead.model_validate(decision).model_dump(),
        scores=[ScoreRead.model_validate(item) for item in scores],
        risks=[RiskRead.model_validate(item) for item in risks],
    )
