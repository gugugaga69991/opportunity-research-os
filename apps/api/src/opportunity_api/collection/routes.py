import hmac
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.collection.queue import enqueue_job
from opportunity_api.collection.schemas import (
    ApifyWebhookPayload,
    CollectionRunRead,
    CollectionStart,
    RawDocumentRead,
    ScheduleCreate,
    ScheduleRead,
    SourceCreate,
    SourceRead,
    SourceUpdate,
)
from opportunity_api.collection.service import (
    bootstrap_sources,
    create_collection_run,
    recent_runs_query,
    record_webhook,
)
from opportunity_api.config import get_settings
from opportunity_api.database import get_session
from opportunity_api.models import (
    AccessRisk,
    CollectionRun,
    CollectionSchedule,
    RawDocument,
    Source,
)

router = APIRouter(prefix="/collection", tags=["collection"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/sources/bootstrap", response_model=list[SourceRead])
async def bootstrap(
    session: SessionDep,
) -> list[Source]:
    return await bootstrap_sources(session, get_settings())


@router.post("/sources", response_model=SourceRead, status_code=201)
async def create_source(
    payload: SourceCreate,
    session: SessionDep,
) -> Source:
    existing = await session.scalar(select(Source).where(Source.slug == payload.slug))
    if existing:
        raise HTTPException(status_code=409, detail="Source slug already exists")
    source = Source(**payload.model_dump())
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


@router.get("/sources", response_model=list[SourceRead])
async def list_sources(
    session: SessionDep,
    enabled: bool | None = None,
) -> list[Source]:
    statement = select(Source).order_by(Source.name)
    if enabled is not None:
        statement = statement.where(Source.enabled == enabled)
    return list((await session.scalars(statement)).all())


@router.patch("/sources/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    session: SessionDep,
) -> Source:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, key, value)
    await session.commit()
    await session.refresh(source)
    return source


@router.put("/sources/{source_id}/schedule", response_model=ScheduleRead)
async def upsert_schedule(
    source_id: uuid.UUID,
    payload: ScheduleCreate,
    session: SessionDep,
) -> CollectionSchedule:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    schedule = await session.scalar(
        select(CollectionSchedule).where(CollectionSchedule.source_id == source_id)
    )
    values = payload.model_dump()
    if schedule is None:
        schedule = CollectionSchedule(source_id=source_id, **values)
        session.add(schedule)
    else:
        for key, value in values.items():
            setattr(schedule, key, value)
    await session.commit()
    await session.refresh(schedule)
    return schedule


@router.post("/sources/{source_id}/runs", response_model=CollectionRunRead, status_code=202)
async def start_collection(
    source_id: uuid.UUID,
    payload: CollectionStart,
    session: SessionDep,
) -> CollectionRun:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if not source.actor_id:
        raise HTTPException(status_code=409, detail="Source has no Apify Actor configured")
    if source.access_risk != AccessRisk.approved:
        raise HTTPException(status_code=409, detail="Source access has not been approved")
    run = await create_collection_run(
        session,
        source,
        input_overrides=payload.input_overrides,
        trigger_type=payload.trigger_type,
    )
    await enqueue_job("launch_collection", str(run.id))
    return run


@router.get("/runs", response_model=list[CollectionRunRead])
async def list_runs(
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CollectionRun]:
    return list((await session.scalars(recent_runs_query(limit))).all())


@router.get("/documents", response_model=list[RawDocumentRead])
async def list_documents(
    session: SessionDep,
    source_id: uuid.UUID | None = None,
    collected_after: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[RawDocument]:
    statement = select(RawDocument).order_by(RawDocument.collected_at.desc()).limit(limit)
    if source_id:
        statement = statement.where(RawDocument.source_id == source_id)
    if collected_after:
        statement = statement.where(RawDocument.collected_at >= collected_after)
    return list((await session.scalars(statement)).all())


@router.post("/webhooks/apify/{secret}", status_code=202)
async def apify_webhook(
    secret: str,
    payload: ApifyWebhookPayload,
    session: SessionDep,
) -> dict[str, str]:
    settings = get_settings()
    if not hmac.compare_digest(secret, settings.apify_webhook_secret):
        raise HTTPException(status_code=404, detail="Not found")
    actor_run_id = payload.event_data.get("actorRunId") or payload.resource.get("id")
    if not actor_run_id:
        raise HTTPException(status_code=422, detail="Webhook does not contain actorRunId")
    event, created = await record_webhook(
        session,
        event_type=payload.event_type,
        actor_run_id=actor_run_id,
        payload=payload.model_dump(by_alias=True),
    )
    if created:
        await enqueue_job("process_apify_webhook", str(event.id))
    return {"status": "queued" if created else "duplicate"}
