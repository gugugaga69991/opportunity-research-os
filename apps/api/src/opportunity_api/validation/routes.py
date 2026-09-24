import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.config import get_settings
from opportunity_api.database import get_session
from opportunity_api.models import (
    ExperimentStatus,
    FailureMemory,
    ValidationCampaign,
    ValidationExperiment,
    ValidationResult,
    ValidationVerdict,
)
from opportunity_api.validation.schemas import (
    ExperimentStateChange,
    FailureMemoryRead,
    ResultCreate,
    ValidationCampaignDetail,
    ValidationCampaignRead,
    ValidationExperimentRead,
    ValidationMetrics,
    ValidationResultRead,
)
from opportunity_api.validation.service import (
    create_validation_campaign,
    evaluate_campaign,
    record_result,
    validation_metrics,
)

router = APIRouter(prefix="/validation", tags=["real-world validation"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
settings = get_settings()


@router.post(
    "/decisions/{decision_id}/campaigns", response_model=ValidationCampaignRead, status_code=201
)
async def create_campaign(decision_id: uuid.UUID, session: SessionDep) -> ValidationCampaign:
    try:
        return await create_validation_campaign(session, decision_id, settings)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/campaigns", response_model=list[ValidationCampaignRead])
async def list_campaigns(
    session: SessionDep,
    opportunity_id: uuid.UUID | None = None,
    verdict: ValidationVerdict | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ValidationCampaign]:
    statement = (
        select(ValidationCampaign).order_by(ValidationCampaign.updated_at.desc()).limit(limit)
    )
    if opportunity_id:
        statement = statement.where(ValidationCampaign.opportunity_id == opportunity_id)
    if verdict:
        statement = statement.where(ValidationCampaign.verdict == verdict)
    return list((await session.scalars(statement)).all())


@router.get("/campaigns/{campaign_id}", response_model=ValidationCampaignDetail)
async def get_campaign(campaign_id: uuid.UUID, session: SessionDep) -> ValidationCampaignDetail:
    campaign = await session.get(ValidationCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Validation campaign not found")
    experiments = list(
        (
            await session.scalars(
                select(ValidationExperiment)
                .where(ValidationExperiment.campaign_id == campaign.id)
                .order_by(ValidationExperiment.created_at)
            )
        ).all()
    )
    experiment_ids = [item.id for item in experiments]
    results = (
        list(
            (
                await session.scalars(
                    select(ValidationResult)
                    .where(ValidationResult.experiment_id.in_(experiment_ids))
                    .order_by(ValidationResult.observed_at.desc())
                )
            ).all()
        )
        if experiment_ids
        else []
    )
    failures = list(
        (
            await session.scalars(
                select(FailureMemory).where(
                    FailureMemory.campaign_id == campaign.id, FailureMemory.active.is_(True)
                )
            )
        ).all()
    )
    return ValidationCampaignDetail(
        **ValidationCampaignRead.model_validate(campaign).model_dump(),
        experiments=[ValidationExperimentRead.model_validate(item) for item in experiments],
        results=[ValidationResultRead.model_validate(item) for item in results],
        failures=[FailureMemoryRead.model_validate(item) for item in failures],
    )


@router.post("/campaigns/{campaign_id}/evaluate", response_model=ValidationCampaignRead)
async def evaluate(campaign_id: uuid.UUID, session: SessionDep) -> ValidationCampaign:
    try:
        campaign = await evaluate_campaign(session, campaign_id, settings)
        await session.commit()
        await session.refresh(campaign)
        return campaign
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/experiments/{experiment_id}/results", response_model=ValidationResultRead, status_code=201
)
async def add_result(
    experiment_id: uuid.UUID, payload: ResultCreate, session: SessionDep
) -> ValidationResult:
    experiment = await session.get(ValidationExperiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Validation experiment not found")
    if experiment.status == ExperimentStatus.cancelled:
        raise HTTPException(status_code=409, detail="Cancelled experiments cannot accept results")
    return await record_result(session, experiment, payload, settings)


@router.patch("/experiments/{experiment_id}", response_model=ValidationExperimentRead)
async def change_experiment(
    experiment_id: uuid.UUID, payload: ExperimentStateChange, session: SessionDep
) -> ValidationExperiment:
    experiment = await session.get(ValidationExperiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Validation experiment not found")
    allowed = {
        ExperimentStatus.planned: {ExperimentStatus.ready, ExperimentStatus.cancelled},
        ExperimentStatus.ready: {ExperimentStatus.running, ExperimentStatus.cancelled},
        ExperimentStatus.running: {ExperimentStatus.completed, ExperimentStatus.cancelled},
        ExperimentStatus.completed: set(),
        ExperimentStatus.cancelled: set(),
    }
    if payload.status != experiment.status and payload.status not in allowed[experiment.status]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move experiment from {experiment.status} to {payload.status}",
        )
    experiment.status = payload.status
    await session.commit()
    await session.refresh(experiment)
    return experiment


@router.get("/metrics", response_model=ValidationMetrics)
async def metrics(session: SessionDep) -> dict[str, int]:
    return await validation_metrics(session)
