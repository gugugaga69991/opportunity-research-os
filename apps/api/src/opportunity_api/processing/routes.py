import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.collection.queue import enqueue_job
from opportunity_api.database import get_session
from opportunity_api.models import Signal, SignalExtraction
from opportunity_api.processing.schemas import (
    BackfillRequest,
    ExtractionRead,
    ProcessingMetrics,
    SignalDetail,
    SignalRead,
)
from opportunity_api.processing.service import pending_documents_query, processing_metrics

router = APIRouter(prefix="/processing", tags=["processing"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/documents/{document_id}", status_code=202)
async def queue_document(document_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    from opportunity_api.models import RawDocument

    if await session.get(RawDocument, document_id) is None:
        raise HTTPException(status_code=404, detail="Raw document not found")
    await enqueue_job("process_signal_document", str(document_id))
    return {"status": "queued", "document_id": str(document_id)}


@router.post("/backfill", status_code=202)
async def queue_backfill(payload: BackfillRequest, session: SessionDep) -> dict[str, int]:
    documents = list(
        (
            await session.scalars(
                pending_documents_query(payload.limit, include_model_retries=True)
            )
        ).all()
    )
    for document in documents:
        await enqueue_job("process_signal_document", str(document.id))
    return {"queued": len(documents)}


@router.get("/signals", response_model=list[SignalRead])
async def list_signals(
    session: SessionDep,
    is_duplicate: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Signal]:
    statement = select(Signal).order_by(Signal.created_at.desc()).limit(limit)
    if is_duplicate is not None:
        statement = statement.where(Signal.is_duplicate == is_duplicate)
    return list((await session.scalars(statement)).all())


@router.get("/signals/{signal_id}", response_model=SignalDetail)
async def get_signal(signal_id: uuid.UUID, session: SessionDep) -> SignalDetail:
    signal = await session.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    extraction = await session.scalar(
        select(SignalExtraction).where(SignalExtraction.signal_id == signal.id)
    )
    payload = SignalDetail.model_validate(signal).model_dump()
    payload["extraction"] = ExtractionRead.model_validate(extraction) if extraction else None
    return SignalDetail.model_validate(payload)


@router.get("/metrics", response_model=ProcessingMetrics)
async def get_metrics(session: SessionDep) -> dict[str, int]:
    return await processing_metrics(session)
