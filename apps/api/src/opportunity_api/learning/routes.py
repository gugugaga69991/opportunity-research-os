import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.collection.queue import enqueue_job
from opportunity_api.config import get_settings
from opportunity_api.database import get_session
from opportunity_api.learning.schemas import (
    BackfillRequest,
    CalibrationRead,
    CalibrationReview,
    FreshnessRead,
    OutcomeCreate,
    OutcomeRead,
    ScoringProfileRead,
)
from opportunity_api.learning.service import (
    approve_calibration,
    assess_freshness,
    learning_metrics,
    run_calibration,
    schedule_freshness_refresh,
)
from opportunity_api.models import (
    BusinessOutcome,
    CalibrationRun,
    CalibrationStatus,
    FreshnessAssessment,
    OpportunityDecision,
    OpportunityHypothesis,
    OpportunityStatus,
    ResearchTask,
)

router = APIRouter(prefix="/learning", tags=["learning and freshness"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
settings = get_settings()


@router.post(
    "/opportunities/{opportunity_id}/outcomes", response_model=OutcomeRead, status_code=201
)
async def record_outcome(
    opportunity_id: uuid.UUID, payload: OutcomeCreate, session: SessionDep
) -> BusinessOutcome:
    opportunity = await session.get(OpportunityHypothesis, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    existing = await session.scalar(
        select(BusinessOutcome).where(
            BusinessOutcome.opportunity_id == opportunity_id,
            BusinessOutcome.event_key == payload.event_key,
        )
    )
    if existing:
        return existing
    if payload.decision_id:
        decision = await session.get(OpportunityDecision, payload.decision_id)
        if decision is None or decision.opportunity_id != opportunity_id:
            raise HTTPException(status_code=409, detail="Decision does not belong to opportunity")
    outcome = BusinessOutcome(
        opportunity_id=opportunity_id,
        occurred_at=payload.occurred_at or datetime.now(UTC),
        **payload.model_dump(exclude={"occurred_at"}),
    )
    session.add(outcome)
    await session.commit()
    await session.refresh(outcome)
    return outcome


@router.get("/outcomes", response_model=list[OutcomeRead])
async def list_outcomes(
    session: SessionDep,
    opportunity_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[BusinessOutcome]:
    statement = select(BusinessOutcome).order_by(BusinessOutcome.occurred_at.desc()).limit(limit)
    if opportunity_id:
        statement = statement.where(BusinessOutcome.opportunity_id == opportunity_id)
    return list((await session.scalars(statement)).all())


@router.post("/calibration/runs", response_model=CalibrationRead, status_code=201)
async def calibrate(session: SessionDep) -> CalibrationRun:
    return await run_calibration(session, settings)


@router.get("/calibration/runs", response_model=list[CalibrationRead])
async def calibration_runs(
    session: SessionDep, limit: int = Query(default=20, ge=1, le=100)
) -> list[CalibrationRun]:
    return list(
        (
            await session.scalars(
                select(CalibrationRun).order_by(CalibrationRun.created_at.desc()).limit(limit)
            )
        ).all()
    )


@router.post(
    "/calibration/runs/{run_id}/review", response_model=ScoringProfileRead | CalibrationRead
)
async def review_calibration(
    run_id: uuid.UUID, payload: CalibrationReview, session: SessionDep
) -> ScoringProfileRead | CalibrationRead:
    run = await session.get(CalibrationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Calibration run not found")
    if payload.action == "approve":
        try:
            return ScoringProfileRead.model_validate(
                await approve_calibration(session, run, payload.actor)
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    if run.status != CalibrationStatus.pending_review:
        raise HTTPException(status_code=409, detail="Only pending calibration can be rejected")
    run.status = CalibrationStatus.rejected
    run.approved_by = payload.actor
    run.reviewed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(run)
    return CalibrationRead.model_validate(run)


@router.post("/freshness/backfill", response_model=list[FreshnessRead])
async def freshness_backfill(
    payload: BackfillRequest, session: SessionDep
) -> list[FreshnessAssessment]:
    opportunities = list(
        (
            await session.scalars(
                select(OpportunityHypothesis)
                .where(
                    OpportunityHypothesis.status.not_in(
                        {
                            OpportunityStatus.raw,
                            OpportunityStatus.clustered,
                            OpportunityStatus.killed,
                        }
                    )
                )
                .order_by(OpportunityHypothesis.confidence.desc())
                .limit(payload.limit)
            )
        ).all()
    )
    return [await assess_freshness(session, item, settings) for item in opportunities]


@router.get("/freshness", response_model=list[FreshnessRead])
async def list_freshness(
    session: SessionDep,
    due_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[FreshnessAssessment]:
    statement = (
        select(FreshnessAssessment).order_by(FreshnessAssessment.priority.desc()).limit(limit)
    )
    if due_only:
        statement = statement.where(FreshnessAssessment.next_check_at <= datetime.now(UTC))
    return list((await session.scalars(statement)).all())


@router.post("/freshness/{assessment_id}/refresh", response_model=FreshnessRead, status_code=202)
async def refresh(assessment_id: uuid.UUID, session: SessionDep) -> FreshnessAssessment:
    assessment = await session.get(FreshnessAssessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Freshness assessment not found")
    try:
        campaign = await schedule_freshness_refresh(session, assessment, settings)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    tasks = list(
        (
            await session.scalars(
                select(ResearchTask).where(ResearchTask.campaign_id == campaign.id)
            )
        ).all()
    )
    for task in tasks:
        await enqueue_job("dispatch_research_task_job", str(task.id))
    await session.refresh(assessment)
    return assessment


@router.get("/metrics")
async def metrics(session: SessionDep) -> dict[str, int | float]:
    return await learning_metrics(session)
