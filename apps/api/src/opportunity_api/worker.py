import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from opportunity_api.collection.scheduling import next_scheduled_at
from opportunity_api.collection.service import (
    create_collection_run,
    ingest_apify_run,
    launch_apify_run,
)
from opportunity_api.config import get_settings
from opportunity_api.database import session_factory
from opportunity_api.decisions.service import (
    analyze_decision,
    create_decision,
    pending_decisions_query,
    scoring_ready_campaigns_query,
)
from opportunity_api.intelligence.service import cluster_signal, pending_signals_query
from opportunity_api.learning.service import assess_freshness, schedule_freshness_refresh
from opportunity_api.logging import configure_logging
from opportunity_api.models import (
    AccessRisk,
    CollectionRun,
    CollectionSchedule,
    FreshnessStatus,
    OpportunityHypothesis,
    OpportunityStatus,
    ProcessingStatus,
    ResearchStatus,
    ResearchTask,
    RunStatus,
    Signal,
    Source,
    TriggerType,
    WebhookEvent,
)
from opportunity_api.operations.service import deliver_telegram, sync_portfolio
from opportunity_api.opportunities.service import (
    generate_hypothesis,
    pending_hypothesis_clusters_query,
)
from opportunity_api.processing.service import pending_documents_query, process_document
from opportunity_api.research.service import (
    analysis_tasks_query,
    analyze_research_task,
    collecting_tasks_query,
    create_research_campaign,
    dispatch_research_task,
    research_ready_opportunities_query,
    sync_task_collection,
)
from opportunity_api.validation.service import (
    create_validation_campaign,
    validation_ready_decisions_query,
)

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


async def system_ping(_: dict[str, Any]) -> str:
    logger.info("worker_ping")
    return "ok"


async def launch_collection(_: dict[str, Any], run_id: str) -> str:
    async with session_factory() as session:
        run = await launch_apify_run(session, uuid.UUID(run_id), settings)
        logger.info(
            "collection_launched",
            extra={"run_id": str(run.id), "external_run_id": run.external_run_id},
        )
        return str(run.id)


async def process_apify_webhook(_: dict[str, Any], event_id: str) -> str:
    async with session_factory() as session:
        event = await session.get(WebhookEvent, uuid.UUID(event_id))
        if event is None:
            raise LookupError(f"Webhook event {event_id} does not exist")
        actor_run_id = event.payload.get("eventData", {}).get("actorRunId")
        run = await session.scalar(
            select(CollectionRun).where(CollectionRun.external_run_id == actor_run_id)
        )
        if run is None:
            event.error = f"No collection run found for Apify run {actor_run_id}"
            await session.commit()
            raise LookupError(event.error)
        await ingest_apify_run(session, run, settings)
        event.processed_at = datetime.now(UTC)
        await session.commit()
        logger.info(
            "collection_ingested",
            extra={
                "run_id": str(run.id),
                "received": run.items_received,
                "ingested": run.items_ingested,
                "skipped": run.items_skipped,
            },
        )
        return str(run.id)


async def process_signal_document(_: dict[str, Any], document_id: str) -> str:
    async with session_factory() as session:
        signal = await process_document(session, uuid.UUID(document_id), settings)
        logger.info(
            "signal_processed",
            extra={
                "signal_id": str(signal.id),
                "document_id": document_id,
                "status": signal.status,
                "duplicate": signal.is_duplicate,
            },
        )
        return str(signal.id)


async def enqueue_pending_processing(context: dict[str, Any]) -> int:
    async with session_factory() as session:
        documents = list(
            (
                await session.scalars(
                    pending_documents_query(
                        settings.processing_batch_size,
                        include_model_retries=bool(settings.openrouter_api_key),
                        retry_limit=settings.model_retry_limit,
                    )
                )
            ).all()
        )
    for document in documents:
        await context["redis"].enqueue_job("process_signal_document", str(document.id))
    return len(documents)


async def cluster_evidence_signal(_: dict[str, Any], signal_id: str) -> list[str]:
    async with session_factory() as session:
        try:
            clusters = await cluster_signal(session, uuid.UUID(signal_id), settings)
            logger.info(
                "signal_clustered",
                extra={
                    "signal_id": signal_id,
                    "cluster_ids": [str(cluster.id) for cluster in clusters],
                },
            )
            return [str(cluster.id) for cluster in clusters]
        except Exception as error:
            await session.rollback()
            signal = await session.get(Signal, uuid.UUID(signal_id))
            if signal:
                signal.intelligence_status = ProcessingStatus.failed
                signal.intelligence_error = str(error)
                await session.commit()
            raise


async def enqueue_pending_clustering(context: dict[str, Any]) -> int:
    async with session_factory() as session:
        signals = list(
            (
                await session.scalars(
                    pending_signals_query(
                        settings.clustering_batch_size,
                        include_failed=True,
                        retry_limit=settings.model_retry_limit,
                    )
                )
            ).all()
        )
    for signal in signals:
        await context["redis"].enqueue_job("cluster_evidence_signal", str(signal.id))
    return len(signals)


async def generate_opportunity_hypothesis(_: dict[str, Any], cluster_id: str) -> str:
    async with session_factory() as session:
        opportunity = await generate_hypothesis(session, uuid.UUID(cluster_id), settings)
        logger.info(
            "opportunity_hypothesis_generated",
            extra={
                "opportunity_id": str(opportunity.id),
                "cluster_id": cluster_id,
                "readiness": opportunity.readiness,
                "evidence_gate_passed": opportunity.evidence_gate_passed,
            },
        )
        return str(opportunity.id)


async def enqueue_pending_opportunities(context: dict[str, Any]) -> int:
    async with session_factory() as session:
        clusters = list(
            (
                await session.scalars(
                    pending_hypothesis_clusters_query(settings.opportunity_batch_size)
                )
            ).all()
        )
    for cluster in clusters:
        await context["redis"].enqueue_job("generate_opportunity_hypothesis", str(cluster.id))
    return len(clusters)


async def start_research_campaign(context: dict[str, Any], opportunity_id: str) -> str:
    async with session_factory() as session:
        campaign = await create_research_campaign(session, uuid.UUID(opportunity_id), settings)
        tasks = list(
            (
                await session.scalars(
                    select(ResearchTask).where(ResearchTask.campaign_id == campaign.id)
                )
            ).all()
        )
    for task in tasks:
        await context["redis"].enqueue_job("dispatch_research_task_job", str(task.id))
    logger.info(
        "research_campaign_started",
        extra={"campaign_id": str(campaign.id), "opportunity_id": opportunity_id},
    )
    return str(campaign.id)


async def dispatch_research_task_job(context: dict[str, Any], task_id: str) -> str:
    async with session_factory() as session:
        task, run = await dispatch_research_task(session, uuid.UUID(task_id), settings)
    if run and run.status.value == "queued":
        await context["redis"].enqueue_job("launch_collection", str(run.id))
    return str(task.id)


async def analyze_research_task_job(_: dict[str, Any], task_id: str) -> str:
    async with session_factory() as session:
        task = await analyze_research_task(session, uuid.UUID(task_id), settings)
        logger.info(
            "research_lane_analyzed",
            extra={
                "task_id": str(task.id),
                "lane": task.lane.value,
                "coverage": task.coverage_score,
            },
        )
        return str(task.id)


async def advance_research(context: dict[str, Any]) -> int:
    enqueued = 0
    async with session_factory() as session:
        opportunities = list(
            (
                await session.scalars(
                    research_ready_opportunities_query(settings.research_batch_size)
                )
            ).all()
        )
        collecting = list(
            (await session.scalars(collecting_tasks_query(settings.research_batch_size * 5))).all()
        )
        for task in collecting:
            await sync_task_collection(session, task)
        analysis = (
            list(
                (
                    await session.scalars(
                        analysis_tasks_query(
                            settings.research_batch_size * 5,
                            retry_limit=settings.model_retry_limit,
                        )
                    )
                ).all()
            )
            if settings.openrouter_api_key
            else []
        )
        source = await session.scalar(select(Source).where(Source.slug == "autonomous-research"))
        configuration_tasks = []
        if (
            settings.apify_api_token
            and settings.apify_research_actor_id
            and source
            and source.access_risk == AccessRisk.approved
        ):
            configuration_tasks = list(
                (
                    await session.scalars(
                        select(ResearchTask)
                        .where(ResearchTask.status == ResearchStatus.awaiting_configuration)
                        .order_by(ResearchTask.updated_at)
                        .limit(settings.research_batch_size * 5)
                    )
                ).all()
            )
    for opportunity in opportunities:
        await context["redis"].enqueue_job("start_research_campaign", str(opportunity.id))
        enqueued += 1
    for task in analysis:
        await context["redis"].enqueue_job("analyze_research_task_job", str(task.id))
        enqueued += 1
    for task in configuration_tasks:
        await context["redis"].enqueue_job("dispatch_research_task_job", str(task.id))
        enqueued += 1
    return enqueued


async def reconcile_running_collections(_: dict[str, Any]) -> int:
    if not settings.apify_api_token:
        return 0
    reconciled = 0
    async with session_factory() as session:
        runs = list(
            (
                await session.scalars(
                    select(CollectionRun)
                    .where(
                        CollectionRun.status == RunStatus.running,
                        CollectionRun.external_run_id.is_not(None),
                    )
                    .order_by(CollectionRun.started_at)
                    .limit(settings.collection_reconcile_batch_size)
                )
            ).all()
        )
        for run in runs:
            try:
                previous = run.status
                await ingest_apify_run(session, run, settings)
                reconciled += int(run.status != previous)
            except Exception:
                logger.exception(
                    "collection_reconciliation_failed",
                    extra={"run_id": str(run.id)},
                )
    return reconciled


async def create_opportunity_decision(context: dict[str, Any], campaign_id: str) -> str:
    async with session_factory() as session:
        decision = await create_decision(session, uuid.UUID(campaign_id))
    if settings.openrouter_api_key:
        await context["redis"].enqueue_job("analyze_opportunity_decision", str(decision.id))
    logger.info(
        "opportunity_decision_created",
        extra={"decision_id": str(decision.id), "campaign_id": campaign_id},
    )
    return str(decision.id)


async def analyze_opportunity_decision(_: dict[str, Any], decision_id: str) -> str:
    async with session_factory() as session:
        decision = await analyze_decision(session, uuid.UUID(decision_id), settings)
        logger.info(
            "opportunity_decision_completed",
            extra={
                "decision_id": str(decision.id),
                "disposition": (decision.disposition.value if decision.disposition else None),
                "adjusted_score": decision.adjusted_score,
                "confidence": decision.confidence_score,
            },
        )
        return str(decision.id)


async def advance_decisions(context: dict[str, Any]) -> int:
    enqueued = 0
    async with session_factory() as session:
        campaigns = list(
            (
                await session.scalars(scoring_ready_campaigns_query(settings.decision_batch_size))
            ).all()
        )
        pending = (
            list(
                (
                    await session.scalars(
                        pending_decisions_query(
                            settings.decision_batch_size,
                            retry_limit=settings.model_retry_limit,
                        )
                    )
                ).all()
            )
            if settings.openrouter_api_key
            else []
        )
    for campaign in campaigns:
        await context["redis"].enqueue_job("create_opportunity_decision", str(campaign.id))
        enqueued += 1
    for decision in pending:
        await context["redis"].enqueue_job("analyze_opportunity_decision", str(decision.id))
        enqueued += 1
    return enqueued


async def create_real_world_validation(_: dict[str, Any], decision_id: str) -> str:
    async with session_factory() as session:
        campaign = await create_validation_campaign(session, uuid.UUID(decision_id), settings)
        logger.info(
            "validation_campaign_created",
            extra={
                "campaign_id": str(campaign.id),
                "decision_id": decision_id,
                "execution": "manual",
            },
        )
        return str(campaign.id)


async def advance_validation(context: dict[str, Any]) -> int:
    async with session_factory() as session:
        decisions = list(
            (
                await session.scalars(
                    validation_ready_decisions_query(settings.validation_batch_size)
                )
            ).all()
        )
    for decision in decisions:
        await context["redis"].enqueue_job("create_real_world_validation", str(decision.id))
    return len(decisions)


async def refresh_portfolio_freshness(context: dict[str, Any]) -> int:
    enqueued = 0
    async with session_factory() as session:
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
                                OpportunityStatus.build,
                            }
                        )
                    )
                    .order_by(OpportunityHypothesis.confidence.desc())
                    .limit(settings.freshness_batch_size)
                )
            ).all()
        )
        source = await session.scalar(select(Source).where(Source.slug == "autonomous-research"))
        can_collect = bool(
            settings.apify_api_token
            and settings.apify_research_actor_id
            and source
            and source.access_risk == AccessRisk.approved
        )
        for opportunity in opportunities:
            assessment = await assess_freshness(session, opportunity, settings)
            if assessment.status == FreshnessStatus.due and can_collect:
                campaign = await schedule_freshness_refresh(session, assessment, settings)
                tasks = list(
                    (
                        await session.scalars(
                            select(ResearchTask).where(ResearchTask.campaign_id == campaign.id)
                        )
                    ).all()
                )
                for task in tasks:
                    await context["redis"].enqueue_job("dispatch_research_task_job", str(task.id))
                    enqueued += 1
    return enqueued


async def monitor_portfolio(_: dict[str, Any]) -> int:
    async with session_factory() as session:
        snapshots = await sync_portfolio(session, settings)
        await deliver_telegram(session, settings)
        return len(snapshots)


async def enqueue_due_sources(context: dict[str, Any]) -> int:
    now = datetime.now(UTC)
    enqueued = 0
    async with session_factory() as session:
        schedules = list(
            (
                await session.scalars(
                    select(CollectionSchedule).where(
                        CollectionSchedule.enabled.is_(True),
                        CollectionSchedule.next_run_at <= now,
                    )
                )
            ).all()
        )
        for schedule in schedules:
            source = await session.get(Source, schedule.source_id)
            if (
                source is None
                or not source.enabled
                or source.access_risk != AccessRisk.approved
                or not source.actor_id
            ):
                continue
            run = await create_collection_run(
                session,
                source,
                input_overrides=schedule.input_overrides,
                trigger_type=TriggerType.schedule,
            )
            await context["redis"].enqueue_job("launch_collection", str(run.id))
            schedule.last_enqueued_at = now
            schedule.next_run_at = next_scheduled_at(
                schedule.cron_expression, schedule.timezone, now
            )
            enqueued += 1
        await session.commit()
    return enqueued


async def startup(_: dict[str, Any]) -> None:
    logger.info("worker_started", extra={"environment": settings.app_env})


class WorkerSettings:
    functions = [
        system_ping,
        launch_collection,
        process_apify_webhook,
        process_signal_document,
        cluster_evidence_signal,
        generate_opportunity_hypothesis,
        start_research_campaign,
        dispatch_research_task_job,
        analyze_research_task_job,
        create_opportunity_decision,
        analyze_opportunity_decision,
        create_real_world_validation,
    ]
    cron_jobs = [
        cron(enqueue_due_sources, second={0}),
        cron(enqueue_pending_processing, second={10, 40}),
        cron(reconcile_running_collections, second={15, 45}),
        cron(enqueue_pending_clustering, second={20, 50}),
        cron(enqueue_pending_opportunities, second={25, 55}),
        cron(advance_research, second={30}),
        cron(advance_decisions, second={35}),
        cron(advance_validation, second={38}),
        cron(refresh_portfolio_freshness, minute={5, 35}, second={0}),
        cron(monitor_portfolio, minute={15, 45}, second={0}),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    max_tries = 3
    job_timeout = 600
