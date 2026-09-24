import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.config import get_settings
from opportunity_api.database import get_session
from opportunity_api.models import (
    AlertStatus,
    BuildSpecification,
    BuildSpecStatus,
    CustomerInterview,
    OperationalAlert,
    OpportunityHypothesis,
    PortfolioSnapshot,
)
from opportunity_api.operations.schemas import (
    AlertRead,
    AlertUpdate,
    BuildSpecRead,
    BuildSpecReview,
    InterviewCreate,
    InterviewRead,
    PortfolioRead,
    SyncRequest,
)
from opportunity_api.operations.service import (
    deliver_telegram,
    generate_build_spec,
    interview_patterns,
    sync_portfolio,
)

router = APIRouter(prefix="/operations", tags=["portfolio and build handoff"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
settings = get_settings()


@router.post("/portfolio/sync", response_model=list[PortfolioRead])
async def synchronize_portfolio(
    payload: SyncRequest,
    session: SessionDep,
) -> list[PortfolioSnapshot]:
    snapshots = await sync_portfolio(session, settings)
    if payload.deliver:
        await deliver_telegram(session, settings)
    return snapshots


@router.get("/portfolio", response_model=list[PortfolioRead])
async def list_portfolio(
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PortfolioSnapshot]:
    return list(
        (
            await session.scalars(
                select(PortfolioSnapshot).order_by(PortfolioSnapshot.rank).limit(limit)
            )
        ).all()
    )


@router.get("/alerts", response_model=list[AlertRead])
async def list_alerts(
    session: SessionDep,
    status: AlertStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OperationalAlert]:
    query = select(OperationalAlert)
    if status:
        query = query.where(OperationalAlert.status == status)
    return list(
        (
            await session.scalars(query.order_by(OperationalAlert.created_at.desc()).limit(limit))
        ).all()
    )


@router.patch("/alerts/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: uuid.UUID,
    payload: AlertUpdate,
    session: SessionDep,
) -> OperationalAlert:
    alert = await session.get(OperationalAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = payload.status
    alert.acknowledged_at = datetime.now(UTC) if payload.status != AlertStatus.unread else None
    await session.commit()
    await session.refresh(alert)
    return alert


@router.post("/opportunities/{opportunity_id}/interviews", response_model=InterviewRead)
async def create_interview(
    opportunity_id: uuid.UUID,
    payload: InterviewCreate,
    session: SessionDep,
) -> CustomerInterview:
    if not await session.get(OpportunityHypothesis, opportunity_id):
        raise HTTPException(status_code=404, detail="Opportunity not found")
    existing = await session.scalar(
        select(CustomerInterview).where(
            CustomerInterview.opportunity_id == opportunity_id,
            CustomerInterview.interview_key == payload.interview_key,
        )
    )
    if existing:
        return existing
    interview = CustomerInterview(opportunity_id=opportunity_id, **payload.model_dump())
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    return interview


@router.get("/interviews", response_model=list[InterviewRead])
async def list_interviews(
    session: SessionDep,
    opportunity_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[CustomerInterview]:
    query = select(CustomerInterview)
    if opportunity_id:
        query = query.where(CustomerInterview.opportunity_id == opportunity_id)
    return list(
        (
            await session.scalars(
                query.order_by(CustomerInterview.interviewed_at.desc()).limit(limit)
            )
        ).all()
    )


@router.get("/opportunities/{opportunity_id}/interview-patterns")
async def get_interview_patterns(
    opportunity_id: uuid.UUID,
    session: SessionDep,
) -> dict:
    interviews = list(
        (
            await session.scalars(
                select(CustomerInterview).where(CustomerInterview.opportunity_id == opportunity_id)
            )
        ).all()
    )
    return interview_patterns(interviews)


@router.post("/opportunities/{opportunity_id}/build-spec", response_model=BuildSpecRead)
async def create_build_spec(
    opportunity_id: uuid.UUID,
    session: SessionDep,
) -> BuildSpecification:
    opportunity = await session.get(OpportunityHypothesis, opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    try:
        return await generate_build_spec(session, opportunity)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/build-specs", response_model=list[BuildSpecRead])
async def list_build_specs(
    session: SessionDep,
    opportunity_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[BuildSpecification]:
    query = select(BuildSpecification)
    if opportunity_id:
        query = query.where(BuildSpecification.opportunity_id == opportunity_id)
    return list(
        (
            await session.scalars(query.order_by(BuildSpecification.created_at.desc()).limit(limit))
        ).all()
    )


@router.post("/build-specs/{spec_id}/review", response_model=BuildSpecRead)
async def review_build_spec(
    spec_id: uuid.UUID,
    payload: BuildSpecReview,
    session: SessionDep,
) -> BuildSpecification:
    spec = await session.get(BuildSpecification, spec_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Build specification not found")
    spec.status = BuildSpecStatus.approved
    spec.approved_by = payload.actor
    spec.approved_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(spec)
    return spec


@router.get("/build-specs/{spec_id}/markdown", response_class=PlainTextResponse)
async def download_build_spec(spec_id: uuid.UUID, session: SessionDep) -> PlainTextResponse:
    spec = await session.get(BuildSpecification, spec_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Build specification not found")
    filename = f"build-spec-{spec.opportunity_id}.md"
    return PlainTextResponse(
        spec.markdown,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/metrics")
async def metrics(session: SessionDep) -> dict[str, int]:
    portfolio = len(list((await session.scalars(select(PortfolioSnapshot.id))).all()))
    unread = len(
        list(
            (
                await session.scalars(
                    select(OperationalAlert.id).where(OperationalAlert.status == AlertStatus.unread)
                )
            ).all()
        )
    )
    interviews = len(list((await session.scalars(select(CustomerInterview.id))).all()))
    specs = len(list((await session.scalars(select(BuildSpecification.id))).all()))
    return {
        "portfolio": portfolio,
        "unread_alerts": unread,
        "interviews": interviews,
        "build_specs": specs,
    }
