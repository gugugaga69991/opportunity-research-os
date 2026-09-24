import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.collection.queue import enqueue_job
from opportunity_api.database import get_session
from opportunity_api.models import (
    CompetitorProfile,
    OpportunityHypothesis,
    ResearchCampaign,
    ResearchFinding,
    ResearchLane,
    ResearchStatus,
    ResearchTarget,
    ResearchTask,
)
from opportunity_api.research.schemas import (
    CampaignDetail,
    CampaignRead,
    CompetitorRead,
    FindingRead,
    ResearchBackfill,
    ResearchMetrics,
    TargetRead,
    TaskRead,
)
from opportunity_api.research.service import research_ready_opportunities_query

router = APIRouter(prefix="/research", tags=["autonomous research"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/opportunities/{opportunity_id}/start", status_code=202)
async def start_campaign(opportunity_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    opportunity = await session.get(OpportunityHypothesis, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity hypothesis not found")
    if not opportunity.evidence_gate_passed:
        raise HTTPException(status_code=409, detail="Opportunity has not passed its evidence gate")
    job_id = await enqueue_job("start_research_campaign", str(opportunity_id))
    return {"status": "queued", "opportunity_id": str(opportunity_id), "job_id": job_id or ""}


@router.post("/backfill", status_code=202)
async def backfill_campaigns(payload: ResearchBackfill, session: SessionDep) -> dict[str, int]:
    opportunities = list(
        (await session.scalars(research_ready_opportunities_query(payload.limit))).all()
    )
    for opportunity in opportunities:
        await enqueue_job("start_research_campaign", str(opportunity.id))
    return {"queued": len(opportunities)}


@router.post("/campaigns/{campaign_id}/dispatch", status_code=202)
async def dispatch_campaign(campaign_id: uuid.UUID, session: SessionDep) -> dict[str, int]:
    if await session.get(ResearchCampaign, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Research campaign not found")
    tasks = list(
        (
            await session.scalars(
                select(ResearchTask).where(
                    ResearchTask.campaign_id == campaign_id,
                    ResearchTask.collection_run_id.is_(None),
                )
            )
        ).all()
    )
    for task in tasks:
        await enqueue_job("dispatch_research_task_job", str(task.id))
    return {"queued": len(tasks)}


@router.post("/tasks/{task_id}/dispatch", status_code=202)
async def dispatch_task(task_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    if await session.get(ResearchTask, task_id) is None:
        raise HTTPException(status_code=404, detail="Research task not found")
    job_id = await enqueue_job("dispatch_research_task_job", str(task_id))
    return {"status": "queued", "task_id": str(task_id), "job_id": job_id or ""}


@router.post("/tasks/{task_id}/analyze", status_code=202)
async def analyze_task(task_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    task = await session.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Research task not found")
    if task.status != ResearchStatus.awaiting_analysis:
        raise HTTPException(status_code=409, detail="Research task is not awaiting analysis")
    job_id = await enqueue_job("analyze_research_task_job", str(task_id))
    return {"status": "queued", "task_id": str(task_id), "job_id": job_id or ""}


@router.get("/campaigns", response_model=list[CampaignRead])
async def list_campaigns(
    session: SessionDep,
    status: ResearchStatus | None = None,
    opportunity_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ResearchCampaign]:
    statement = select(ResearchCampaign).order_by(ResearchCampaign.updated_at.desc()).limit(limit)
    if status:
        statement = statement.where(ResearchCampaign.status == status)
    if opportunity_id:
        statement = statement.where(ResearchCampaign.opportunity_id == opportunity_id)
    return list((await session.scalars(statement)).all())


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(campaign_id: uuid.UUID, session: SessionDep) -> CampaignDetail:
    campaign = await session.get(ResearchCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Research campaign not found")
    tasks = list(
        (
            await session.scalars(
                select(ResearchTask).where(ResearchTask.campaign_id == campaign.id)
            )
        ).all()
    )
    task_ids = [task.id for task in tasks]
    targets = (
        list(
            (
                await session.scalars(
                    select(ResearchTarget).where(ResearchTarget.task_id.in_(task_ids))
                )
            ).all()
        )
        if task_ids
        else []
    )
    findings = list(
        (
            await session.scalars(
                select(ResearchFinding).where(ResearchFinding.campaign_id == campaign.id)
            )
        ).all()
    )
    competitors = list(
        (
            await session.scalars(
                select(CompetitorProfile).where(
                    CompetitorProfile.opportunity_id == campaign.opportunity_id
                )
            )
        ).all()
    )
    return CampaignDetail(
        **CampaignRead.model_validate(campaign).model_dump(),
        tasks=[TaskRead.model_validate(item) for item in tasks],
        targets=[TargetRead.model_validate(item) for item in targets],
        findings=[FindingRead.model_validate(item) for item in findings],
        competitors=[CompetitorRead.model_validate(item) for item in competitors],
    )


@router.get("/findings", response_model=list[FindingRead])
async def list_findings(
    session: SessionDep,
    opportunity_id: uuid.UUID | None = None,
    lane: ResearchLane | None = None,
    active: bool = True,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ResearchFinding]:
    statement = (
        select(ResearchFinding)
        .where(ResearchFinding.active == active)
        .order_by(ResearchFinding.confidence.desc())
        .limit(limit)
    )
    if opportunity_id:
        statement = statement.where(ResearchFinding.opportunity_id == opportunity_id)
    if lane:
        statement = statement.where(ResearchFinding.lane == lane)
    return list((await session.scalars(statement)).all())


@router.get("/competitors", response_model=list[CompetitorRead])
async def list_competitors(
    session: SessionDep,
    opportunity_id: uuid.UUID | None = None,
    active: bool = True,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CompetitorProfile]:
    statement = (
        select(CompetitorProfile)
        .where(CompetitorProfile.active == active)
        .order_by(CompetitorProfile.confidence.desc())
        .limit(limit)
    )
    if opportunity_id:
        statement = statement.where(CompetitorProfile.opportunity_id == opportunity_id)
    return list((await session.scalars(statement)).all())


@router.get("/metrics", response_model=ResearchMetrics)
async def metrics(session: SessionDep) -> dict[str, int]:
    status_rows = dict(
        (
            await session.execute(
                select(ResearchCampaign.status, func.count()).group_by(ResearchCampaign.status)
            )
        ).all()
    )
    summaries = list((await session.scalars(select(ResearchCampaign.summary))).all())
    return {
        "campaigns": sum(status_rows.values()),
        "awaiting_configuration": status_rows.get(ResearchStatus.awaiting_configuration, 0),
        "running": status_rows.get(ResearchStatus.running, 0),
        "completed": status_rows.get(ResearchStatus.completed, 0),
        "blocked": status_rows.get(ResearchStatus.blocked, 0),
        "gate_passed": sum(bool(item.get("research_gate_passed")) for item in summaries),
        "active_findings": int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(ResearchFinding)
                    .where(ResearchFinding.active.is_(True))
                )
            )
            or 0
        ),
        "active_competitors": int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(CompetitorProfile)
                    .where(CompetitorProfile.active.is_(True))
                )
            )
            or 0
        ),
    }
