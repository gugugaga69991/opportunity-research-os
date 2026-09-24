import argparse
import asyncio
import hashlib
import json
import logging
import socket
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from opportunity_api.config import get_settings
from opportunity_api.database import engine, session_factory
from opportunity_api.logging import configure_logging
from opportunity_api.models import JobRun, RunStatus

logger = logging.getLogger(__name__)
settings = get_settings()
configure_logging(settings.log_level)
JobHandler = Callable[..., Awaitable[Any]]

JOB_HANDLERS = frozenset(
    {
        "system_ping",
        "launch_collection",
        "process_apify_webhook",
        "process_signal_document",
        "cluster_evidence_signal",
        "generate_opportunity_hypothesis",
        "start_research_campaign",
        "dispatch_research_task_job",
        "analyze_research_task_job",
        "create_opportunity_decision",
        "analyze_opportunity_decision",
        "create_real_world_validation",
    }
)

SCHEDULED_HANDLERS = (
    "enqueue_due_sources",
    "enqueue_pending_processing",
    "reconcile_running_collections",
    "enqueue_pending_clustering",
    "enqueue_pending_opportunities",
    "advance_research",
    "advance_decisions",
    "advance_validation",
    "refresh_portfolio_freshness",
    "monitor_portfolio",
)


def build_idempotency_key(
    function: str,
    args: Sequence[str],
    *,
    now: datetime | None = None,
) -> str:
    bucket = (now or datetime.now(UTC)).strftime("%Y%m%d%H%M")
    canonical = json.dumps([function, list(args), bucket], separators=(",", ":"))
    return f"{function}:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"


def get_handler(name: str) -> JobHandler:
    if name not in JOB_HANDLERS and name not in SCHEDULED_HANDLERS:
        raise LookupError(f"Unknown job handler: {name}")
    from opportunity_api import worker

    return getattr(worker, name)


async def enqueue(
    function: str,
    *args: str,
    idempotency_key: str | None = None,
    available_at: datetime | None = None,
    max_attempts: int | None = None,
) -> JobRun:
    if function not in JOB_HANDLERS:
        raise LookupError(f"Unknown queue job: {function}")
    key = idempotency_key or build_idempotency_key(function, args)
    job = JobRun(
        job_type=function,
        idempotency_key=key,
        payload={"args": list(args)},
        result={},
        status=RunStatus.queued,
        available_at=available_at or datetime.now(UTC),
        max_attempts=max_attempts or settings.job_max_attempts,
    )
    async with session_factory() as session:
        session.add(job)
        try:
            await session.commit()
            await session.refresh(job)
            return job
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(
                select(JobRun).where(JobRun.idempotency_key == key)
            )
            if existing is None:
                raise
            return existing


class DatabaseQueue:
    async def enqueue_job(self, function: str, *args: str) -> JobRun:
        return await enqueue(function, *args)


async def recover_stale_jobs(*, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    stale_before = current - timedelta(seconds=settings.job_lease_seconds)
    async with session_factory() as session:
        result = await session.execute(
            update(JobRun)
            .where(
                JobRun.status == RunStatus.running,
                or_(JobRun.locked_at.is_(None), JobRun.locked_at < stale_before),
            )
            .values(
                status=RunStatus.queued,
                available_at=current,
                locked_at=None,
                locked_by=None,
                error="Recovered after worker lease expired.",
            )
        )
        await session.commit()
        return result.rowcount or 0


async def claim_job(worker_id: str, *, now: datetime | None = None) -> JobRun | None:
    current = now or datetime.now(UTC)
    async with session_factory() as session:
        async with session.begin():
            job = await session.scalar(
                select(JobRun)
                .where(
                    JobRun.status == RunStatus.queued,
                    JobRun.available_at <= current,
                )
                .order_by(JobRun.available_at, JobRun.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.status = RunStatus.running
            job.locked_at = current
            job.locked_by = worker_id
            job.attempts += 1
        await session.refresh(job)
        return job


async def finish_job(job_id: Any, result: Any) -> None:
    payload = result if isinstance(result, dict) else {"value": result}
    async with session_factory() as session:
        job = await session.get(JobRun, job_id)
        if job is None:
            raise LookupError(f"Job {job_id} disappeared")
        job.status = RunStatus.succeeded
        job.result = payload
        job.error = None
        job.completed_at = datetime.now(UTC)
        job.locked_at = None
        job.locked_by = None
        await session.commit()


async def fail_job(job_id: Any, error: Exception) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        job = await session.get(JobRun, job_id)
        if job is None:
            raise LookupError(f"Job {job_id} disappeared")
        job.error = str(error)
        job.locked_at = None
        job.locked_by = None
        if job.attempts < job.max_attempts:
            job.status = RunStatus.queued
            job.available_at = now + timedelta(seconds=min(300, 2 ** job.attempts * 15))
        else:
            job.status = RunStatus.failed
            job.completed_at = now
        await session.commit()


async def run_one(worker_id: str) -> bool:
    job = await claim_job(worker_id)
    if job is None:
        return False
    try:
        handler = get_handler(job.job_type)
        args = job.payload.get("args", [])
        result = await handler({"queue": DatabaseQueue()}, *args)
        await finish_job(job.id, result)
    except Exception as error:
        logger.exception("job_failed", extra={"job_id": str(job.id), "job_type": job.job_type})
        await fail_job(job.id, error)
    return True


async def run_scheduled_cycle() -> dict[str, int]:
    context = {"queue": DatabaseQueue()}
    results: dict[str, int] = {}
    for name in SCHEDULED_HANDLERS:
        try:
            value = await get_handler(name)(context)
            results[name] = int(value)
        except Exception:
            logger.exception("scheduled_handler_failed", extra={"job_type": name})
            results[name] = -1
    return results


async def run_batch(
    *,
    max_jobs: int = 100,
    include_schedule: bool = True,
    worker_id: str | None = None,
) -> int:
    identity = worker_id or f"{socket.gethostname()}:{id(asyncio.current_task())}"
    await recover_stale_jobs()
    if include_schedule:
        await run_scheduled_cycle()
    completed = 0
    while completed < max_jobs and await run_one(identity):
        completed += 1
    return completed


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run one bounded Opportunity OS job batch.")
    parser.add_argument("--max-jobs", type=int, default=100)
    parser.add_argument("--skip-schedule", action="store_true")
    parser.add_argument("--worker-id")
    args = parser.parse_args()
    try:
        count = await run_batch(
            max_jobs=max(0, args.max_jobs),
            include_schedule=not args.skip_schedule,
            worker_id=args.worker_id,
        )
        logger.info("job_batch_finished", extra={"jobs_processed": count})
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
