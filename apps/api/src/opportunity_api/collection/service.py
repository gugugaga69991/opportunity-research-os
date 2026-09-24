import os
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.clients.apify import ApifyClient
from opportunity_api.collection.catalog import SOURCE_CATALOG
from opportunity_api.collection.normalizers import ApifyItemNormalizer
from opportunity_api.collection.schemas import SourceCreate
from opportunity_api.config import Settings
from opportunity_api.models import (
    AccessRisk,
    CollectionRun,
    RawDocument,
    RunStatus,
    Source,
    TriggerType,
    WebhookEvent,
)

TERMINAL_FAILURES = {"FAILED", "ABORTED", "TIMED-OUT"}


def source_catalog_entries(settings: Settings) -> list[SourceCreate]:
    entries: list[SourceCreate] = []
    for definition in SOURCE_CATALOG:
        payload = dict(definition)
        actor_env = payload.pop("actor_env")
        actor_id = os.getenv(actor_env, "") or getattr(settings, actor_env.lower(), "")
        entries.append(
            SourceCreate(
                **payload,
                actor_id=actor_id or None,
                access_method="apify",
                access_risk=AccessRisk.review_required,
                access_metadata={
                    "official_api_available": True,
                    "commercial_use_notes": "Review source-specific terms before enabling.",
                    "legal_review_required": True,
                },
            )
        )
    return entries


async def bootstrap_sources(session: AsyncSession, settings: Settings) -> list[Source]:
    saved: list[Source] = []
    for entry in source_catalog_entries(settings):
        source = await session.scalar(select(Source).where(Source.slug == entry.slug))
        if source is None:
            source = Source(**entry.model_dump())
            session.add(source)
        else:
            source.description = entry.description
            source.actor_id = source.actor_id or entry.actor_id
        saved.append(source)
    await session.commit()
    for source in saved:
        await session.refresh(source)
    return saved


async def create_collection_run(
    session: AsyncSession,
    source: Source,
    *,
    input_overrides: dict[str, Any] | None = None,
    trigger_type: TriggerType = TriggerType.manual,
) -> CollectionRun:
    actor_input = dict(source.collector_config)
    actor_input.update(input_overrides or {})
    run = CollectionRun(
        source_id=source.id,
        trigger_type=trigger_type,
        actor_input=actor_input,
        status=RunStatus.queued,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


def webhook_url(settings: Settings) -> str:
    if not settings.apify_webhook_url:
        return ""
    return f"{settings.apify_webhook_url.rstrip('/')}/{settings.apify_webhook_secret}"


async def launch_apify_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    settings: Settings,
    *,
    client: ApifyClient | None = None,
) -> CollectionRun:
    run = await session.get(CollectionRun, run_id)
    if run is None:
        raise LookupError(f"Collection run {run_id} does not exist")
    if run.external_run_id or run.status in {RunStatus.succeeded, RunStatus.failed}:
        return run
    source = await session.get(Source, run.source_id)
    if source is None:
        raise LookupError(f"Source {run.source_id} does not exist")
    if not source.enabled:
        raise ValueError("Source is disabled")
    if source.access_risk != AccessRisk.approved:
        raise ValueError("Source access must be approved before collection")
    if not source.actor_id:
        raise ValueError("Source has no Apify Actor configured")

    owns_client = client is None
    apify = client or ApifyClient(settings)
    try:
        external = await apify.start_actor(
            source.actor_id,
            run.actor_input,
            webhook_url=webhook_url(settings),
        )
        run.external_run_id = external["id"]
        run.external_dataset_id = external.get("defaultDatasetId")
        run.status = RunStatus.running
        run.started_at = datetime.now(UTC)
        run.metrics = {"apify_status": external.get("status", "READY")}
        await session.commit()
        await session.refresh(run)
        return run
    except Exception as error:
        run.status = RunStatus.failed
        run.error = str(error)
        run.finished_at = datetime.now(UTC)
        await session.commit()
        raise
    finally:
        if owns_client:
            await apify.close()


async def ingest_apify_run(
    session: AsyncSession,
    run: CollectionRun,
    settings: Settings,
    *,
    client: ApifyClient | None = None,
) -> CollectionRun:
    if run.status == RunStatus.succeeded:
        return run
    if not run.external_run_id:
        raise ValueError("Collection run has no Apify run ID")
    source = await session.get(Source, run.source_id)
    if source is None:
        raise LookupError(f"Source {run.source_id} does not exist")

    owns_client = client is None
    apify = client or ApifyClient(settings)
    try:
        external = await apify.get_run(run.external_run_id)
        status = external.get("status", "UNKNOWN")
        run.metrics = {
            **run.metrics,
            "apify_status": status,
            "stats": external.get("stats", {}),
        }
        if status in TERMINAL_FAILURES:
            run.status = RunStatus.failed
            run.error = external.get("statusMessage") or f"Apify run ended with {status}"
            run.finished_at = datetime.now(UTC)
            await session.commit()
            return run
        if status != "SUCCEEDED":
            return run

        dataset_id = external.get("defaultDatasetId") or run.external_dataset_id
        if not dataset_id:
            raise ValueError("Successful Apify run has no dataset ID")
        run.external_dataset_id = dataset_id
        items = await apify.get_dataset_items(dataset_id)
        normalizer = ApifyItemNormalizer()
        ingested = 0
        skipped = 0
        for item in items:
            document = normalizer.normalize(
                item,
                source_slug=source.slug,
                adapter_key=source.adapter_key,
                config=source.collector_config,
                external_run_id=run.external_run_id,
                external_dataset_id=dataset_id,
            )
            if document is None:
                skipped += 1
                continue
            statement = (
                insert(RawDocument)
                .values(
                    source_id=source.id,
                    collection_run_id=run.id,
                    **document.model_dump(),
                )
                .on_conflict_do_nothing(constraint="uq_raw_document_source_hash")
            )
            result = await session.execute(statement)
            if result.rowcount:
                ingested += 1
            else:
                skipped += 1

        run.status = RunStatus.succeeded
        run.finished_at = datetime.now(UTC)
        run.items_received = len(items)
        run.items_ingested = ingested
        run.items_skipped = skipped
        run.cost_usd = external.get("usageTotalUsd")
        await session.commit()
        await session.refresh(run)
        return run
    except httpx.HTTPError as error:
        run.error = f"Transient Apify request failure: {error}"
        await session.commit()
        raise
    except Exception as error:
        run.status = RunStatus.failed
        run.error = str(error)
        run.finished_at = datetime.now(UTC)
        await session.commit()
        raise
    finally:
        if owns_client:
            await apify.close()


async def record_webhook(
    session: AsyncSession,
    *,
    event_type: str,
    actor_run_id: str,
    payload: dict[str, Any],
) -> tuple[WebhookEvent, bool]:
    event_key = f"apify:{event_type}:{actor_run_id}"
    existing = await session.scalar(select(WebhookEvent).where(WebhookEvent.event_key == event_key))
    if existing:
        return existing, False
    event = WebhookEvent(
        provider="apify",
        event_key=event_key,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event, True


def recent_runs_query(limit: int = 100) -> Select[tuple[CollectionRun]]:
    return select(CollectionRun).order_by(CollectionRun.created_at.desc()).limit(limit)
