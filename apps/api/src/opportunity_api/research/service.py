import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.clients.openrouter import OpenRouterClient
from opportunity_api.collection.service import create_collection_run
from opportunity_api.config import Settings
from opportunity_api.intelligence.entities import normalize_entity_value
from opportunity_api.models import (
    AccessRisk,
    CollectionRun,
    CompetitorProfile,
    FindingStance,
    ModelRun,
    OpportunityHypothesis,
    OpportunityStatus,
    PromptVersion,
    RawDocument,
    ResearchCampaign,
    ResearchFinding,
    ResearchLane,
    ResearchStatus,
    ResearchTarget,
    ResearchTask,
    RunStatus,
    Source,
)
from opportunity_api.opportunities.service import transition_opportunity
from opportunity_api.research.contracts import CONTRACTS, AnalysisContract
from opportunity_api.research.planner import actor_input, plan_research
from opportunity_api.research.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    messages,
    prompt_name,
    response_format,
)

CAMPAIGN_VERSION = "1.0.0"
TERMINAL_TASK_STATES = {
    ResearchStatus.completed,
    ResearchStatus.failed,
    ResearchStatus.blocked,
}


def _response_content(response: dict[str, Any]) -> dict[str, Any]:
    content = response["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if isinstance(content, str):
        return json.loads(content)
    if isinstance(content, dict):
        return content
    raise ValueError("Specialist model response did not contain structured JSON")


async def ensure_research_source(session: AsyncSession, settings: Settings) -> Source:
    source = await session.scalar(select(Source).where(Source.slug == "autonomous-research"))
    if source is None:
        source = Source(
            name="Autonomous Research Discovery",
            slug="autonomous-research",
            description="Query-led web research for opportunity specialist lanes.",
            source_type="autonomous_research",
            access_method="apify",
            adapter_key="generic_apify",
            actor_id=settings.apify_research_actor_id or None,
            enabled=True,
            reliability_weight=0.65,
            access_risk=AccessRisk.review_required,
            collector_config={},
            access_metadata={
                "legal_review_required": True,
                "commercial_use_notes": (
                    "Approve the configured search Actor and target terms before enabling."
                ),
            },
        )
        session.add(source)
        await session.flush()
    elif settings.apify_research_actor_id and not source.actor_id:
        source.actor_id = settings.apify_research_actor_id
    return source


async def create_research_campaign(
    session: AsyncSession,
    opportunity_id: uuid.UUID,
    settings: Settings,
    *,
    version: str = CAMPAIGN_VERSION,
    campaign_type: str = "baseline",
    supersedes_campaign_id: uuid.UUID | None = None,
) -> ResearchCampaign:
    opportunity = await session.get(OpportunityHypothesis, opportunity_id)
    if opportunity is None:
        raise LookupError(f"Opportunity {opportunity_id} does not exist")
    if not opportunity.evidence_gate_passed:
        raise ValueError("Opportunity must pass the evidence gate before deep research")
    baseline_allowed = {OpportunityStatus.screened, OpportunityStatus.researching}
    refresh_allowed = {
        OpportunityStatus.thesis_ready,
        OpportunityStatus.validating,
        OpportunityStatus.pilot,
        OpportunityStatus.prototype,
        OpportunityStatus.watchlist,
    }
    allowed = baseline_allowed if campaign_type == "baseline" else refresh_allowed
    if opportunity.status not in allowed:
        raise ValueError(
            f"Opportunity status {opportunity.status} cannot start {campaign_type} research"
        )

    campaign = await session.scalar(
        select(ResearchCampaign).where(
            ResearchCampaign.opportunity_id == opportunity.id,
            ResearchCampaign.version == version,
        )
    )
    if campaign:
        return campaign
    source = await ensure_research_source(session, settings)
    configured = bool(
        settings.apify_api_token and source.actor_id and source.access_risk == AccessRisk.approved
    )
    if (
        configured
        and campaign_type == "baseline"
        and opportunity.status == OpportunityStatus.screened
    ):
        await transition_opportunity(
            session,
            opportunity,
            OpportunityStatus.researching,
            "Autonomous specialist research campaign started.",
            "system",
        )
    campaign = ResearchCampaign(
        opportunity_id=opportunity.id,
        version=version,
        campaign_type=campaign_type,
        supersedes_campaign_id=supersedes_campaign_id,
        status=(ResearchStatus.planned if configured else ResearchStatus.awaiting_configuration),
        required_lane_count=len(ResearchLane),
        summary={"research_gate_passed": False, "purpose": campaign_type},
    )
    session.add(campaign)
    await session.flush()
    plan = plan_research(opportunity)
    for lane in ResearchLane:
        targets = plan[lane]
        task = ResearchTask(
            campaign_id=campaign.id,
            lane=lane,
            status=(
                ResearchStatus.planned if configured else ResearchStatus.awaiting_configuration
            ),
            required=True,
            research_queries=[target.query for target in targets],
            actor_input=actor_input(
                lane,
                targets,
                settings.research_max_documents_per_lane,
                settings.apify_search_discovery_actor_id,
            ),
        )
        session.add(task)
        await session.flush()
        for target in targets:
            target_key = hashlib.sha256(target.query.casefold().encode()).hexdigest()
            session.add(
                ResearchTarget(
                    task_id=task.id,
                    target_key=target_key,
                    target_type="search_query",
                    value=target.query,
                    rationale=target.rationale,
                    status=task.status,
                )
            )
    await session.commit()
    await session.refresh(campaign)
    return campaign


async def dispatch_research_task(
    session: AsyncSession,
    task_id: uuid.UUID,
    settings: Settings,
) -> tuple[ResearchTask, CollectionRun | None]:
    task = await session.get(ResearchTask, task_id)
    if task is None:
        raise LookupError(f"Research task {task_id} does not exist")
    if task.collection_run_id:
        return task, await session.get(CollectionRun, task.collection_run_id)
    source = await ensure_research_source(session, settings)
    if (
        not settings.apify_api_token
        or not source.actor_id
        or source.access_risk != AccessRisk.approved
    ):
        task.status = ResearchStatus.awaiting_configuration
        task.error = "Research Actor, Apify token, or source approval is not configured"
        await session.commit()
        return task, None
    campaign = await session.get(ResearchCampaign, task.campaign_id)
    if campaign:
        opportunity = await session.get(OpportunityHypothesis, campaign.opportunity_id)
        if opportunity and opportunity.status == OpportunityStatus.screened:
            await transition_opportunity(
                session,
                opportunity,
                OpportunityStatus.researching,
                "Autonomous specialist research collection started.",
                "system",
            )
    run = await create_collection_run(session, source, input_overrides=task.actor_input)
    task.collection_run_id = run.id
    task.status = ResearchStatus.collecting
    task.started_at = task.started_at or datetime.now(UTC)
    task.attempts += 1
    task.error = None
    targets = list(
        (
            await session.scalars(select(ResearchTarget).where(ResearchTarget.task_id == task.id))
        ).all()
    )
    for target in targets:
        target.status = ResearchStatus.collecting
    if campaign:
        campaign.status = ResearchStatus.running
        campaign.started_at = campaign.started_at or datetime.now(UTC)
    await session.commit()
    await session.refresh(task)
    return task, run


async def sync_task_collection(session: AsyncSession, task: ResearchTask) -> ResearchTask:
    if not task.collection_run_id:
        return task
    run = await session.get(CollectionRun, task.collection_run_id)
    if run is None:
        task.status = ResearchStatus.failed
        task.error = "Linked collection run does not exist"
    elif run.status == RunStatus.succeeded:
        task.documents_found = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(RawDocument)
                    .where(RawDocument.collection_run_id == run.id)
                )
            )
            or 0
        )
        task.status = (
            ResearchStatus.awaiting_analysis if task.documents_found > 0 else ResearchStatus.blocked
        )
        task.error = None if task.documents_found else "Collection returned no research documents"
    elif run.status == RunStatus.failed:
        task.status = ResearchStatus.failed
        task.error = run.error or "Research collection failed"
    targets = list(
        (
            await session.scalars(select(ResearchTarget).where(ResearchTarget.task_id == task.id))
        ).all()
    )
    for target in targets:
        target.status = task.status
    await session.commit()
    await refresh_campaign(session, task.campaign_id)
    return task


async def ensure_research_prompt(session: AsyncSession, lane: ResearchLane) -> PromptVersion:
    name = prompt_name(lane)
    prompt = await session.scalar(
        select(PromptVersion).where(
            PromptVersion.name == name,
            PromptVersion.version == PROMPT_VERSION,
        )
    )
    if prompt is None:
        prompt = PromptVersion(
            name=name,
            version=PROMPT_VERSION,
            template=SYSTEM_PROMPT,
            output_schema=CONTRACTS[lane].model_json_schema(),
        )
        session.add(prompt)
        await session.flush()
    return prompt


def _opportunity_context(opportunity: OpportunityHypothesis) -> str:
    return json.dumps(
        {
            "name": opportunity.name,
            "industry": opportunity.industry,
            "icp": opportunity.icp,
            "user": opportunity.user_role,
            "buyer": opportunity.buyer_role,
            "workflow": opportunity.core_workflow,
            "problem": opportunity.problem,
            "frequency": opportunity.frequency,
            "current_workaround": opportunity.current_workaround,
            "observed_cost": opportunity.economic_cost,
            "observed_spend": opportunity.existing_spend,
            "why_now": opportunity.why_now,
            "thesis": opportunity.thesis,
        },
        ensure_ascii=False,
    )


def _document_packet(documents: list[RawDocument]) -> str:
    parts: list[str] = []
    budget = 60000
    for index, document in enumerate(documents, start=1):
        text = document.raw_text[:7000]
        part = (
            f"DOCUMENT {index}\nURL: {document.canonical_url}\n"
            f"TITLE: {document.title}\nTEXT:\n{text}\n"
        )
        if sum(len(item) for item in parts) + len(part) > budget:
            break
        parts.append(part)
    return "\n---\n".join(parts)


def _verify_references(analysis: AnalysisContract, documents: list[RawDocument]) -> float:
    by_url = {document.canonical_url: document.raw_text.casefold() for document in documents}
    verified = 0
    for reference in analysis.evidence:
        source_text = by_url.get(reference.url)
        reference.verified = bool(
            source_text and reference.quote and reference.quote.casefold() in source_text
        )
        verified += int(reference.verified)
    return verified / max(len(analysis.evidence), 1)


async def _materialize_competitors(
    session: AsyncSession,
    opportunity: OpportunityHypothesis,
    finding: ResearchFinding,
    analysis: AnalysisContract,
) -> None:
    if analysis.lane != ResearchLane.competition.value:
        return
    await session.execute(
        update(CompetitorProfile)
        .where(CompetitorProfile.opportunity_id == opportunity.id)
        .values(active=False)
    )
    allowed_urls = set(finding.evidence_urls)
    for competitor in analysis.competitors:
        normalized_name = normalize_entity_value(competitor.name)
        if not normalized_name:
            continue
        profile = await session.scalar(
            select(CompetitorProfile).where(
                CompetitorProfile.opportunity_id == opportunity.id,
                CompetitorProfile.normalized_name == normalized_name,
            )
        )
        values = {
            "finding_id": finding.id,
            "name": competitor.name,
            "website": competitor.website,
            "positioning": competitor.positioning,
            "icp": competitor.icp,
            "pricing": competitor.pricing,
            "strengths": competitor.strengths,
            "weaknesses": competitor.weaknesses,
            "evidence_urls": [url for url in competitor.evidence_urls if url in allowed_urls],
            "confidence": competitor.confidence,
            "active": True,
        }
        if profile is None:
            profile = CompetitorProfile(
                opportunity_id=opportunity.id,
                normalized_name=normalized_name,
                **values,
            )
            session.add(profile)
        else:
            for field, value in values.items():
                setattr(profile, field, value)


async def analyze_research_task(
    session: AsyncSession,
    task_id: uuid.UUID,
    settings: Settings,
    *,
    client: OpenRouterClient | None = None,
) -> ResearchTask:
    task = await session.get(ResearchTask, task_id)
    if task is None:
        raise LookupError(f"Research task {task_id} does not exist")
    if task.status == ResearchStatus.completed:
        return task
    if task.status != ResearchStatus.awaiting_analysis:
        raise ValueError(f"Research task is not ready for analysis: {task.status}")
    campaign = await session.get(ResearchCampaign, task.campaign_id)
    if campaign is None:
        raise LookupError("Research campaign does not exist")
    opportunity = await session.get(OpportunityHypothesis, campaign.opportunity_id)
    if opportunity is None:
        raise LookupError("Opportunity hypothesis does not exist")
    documents = list(
        (
            await session.scalars(
                select(RawDocument)
                .where(RawDocument.collection_run_id == task.collection_run_id)
                .order_by(RawDocument.published_at.desc().nullslast())
                .limit(settings.research_max_documents_per_lane)
            )
        ).all()
    )
    if not documents:
        task.status = ResearchStatus.blocked
        task.error = "No documents are available for specialist analysis"
        await session.commit()
        await refresh_campaign(session, task.campaign_id)
        return task

    owns_client = client is None
    router = client or OpenRouterClient(settings)
    if not router.configured:
        task.status = ResearchStatus.awaiting_analysis
        task.error = "OPENROUTER_API_KEY is not configured"
        await session.commit()
        if owns_client:
            await router.close()
        return task

    prompt = await ensure_research_prompt(session, task.lane)
    document_fingerprint = ":".join(sorted(document.content_hash for document in documents))
    input_hash = hashlib.sha256(
        f"{PROMPT_VERSION}:{task.lane}:{opportunity.id}:{document_fingerprint}".encode()
    ).hexdigest()
    run = ModelRun(
        prompt_version_id=prompt.id,
        provider="openrouter",
        model=settings.openrouter_default_model,
        input_hash=input_hash,
        status=RunStatus.running,
    )
    session.add(run)
    await session.flush()
    task.status = ResearchStatus.analyzing
    task.model_run_id = run.id
    task.attempts += 1
    await session.commit()
    started = time.perf_counter()
    try:
        response = await router.complete(
            messages(
                task.lane,
                _opportunity_context(opportunity),
                _document_packet(documents),
            ),
            model=settings.openrouter_default_model,
            models=settings.model_route[1:],
            response_format=response_format(task.lane),
        )
        contract = CONTRACTS[task.lane]
        analysis: AnalysisContract = contract.model_validate(_response_content(response))
        verification_ratio = _verify_references(analysis, documents)
        document_coverage = min(
            1.0, task.documents_found / settings.research_min_documents_per_lane
        )
        task.coverage_score = min(
            analysis.coverage,
            document_coverage,
            verification_ratio if analysis.evidence else 0.25,
        )
        evidence_urls = sorted(
            {reference.url for reference in analysis.evidence if reference.verified}
        )
        finding_key = hashlib.sha256(f"{task.lane}:{PROMPT_VERSION}:{task.id}".encode()).hexdigest()
        await session.execute(
            update(ResearchFinding).where(ResearchFinding.task_id == task.id).values(active=False)
        )
        finding = await session.scalar(
            select(ResearchFinding).where(
                ResearchFinding.task_id == task.id,
                ResearchFinding.finding_key == finding_key,
            )
        )
        stance = {
            ResearchLane.economics: FindingStance.supporting,
            ResearchLane.contradiction: FindingStance.contradicting,
        }.get(task.lane, FindingStance.neutral)
        values = {
            "title": f"{task.lane.value.title()} research",
            "summary": analysis.summary,
            "stance": stance,
            "confidence": analysis.confidence * task.coverage_score,
            "structured_data": analysis.model_dump(),
            "evidence_urls": evidence_urls,
            "document_ids": [str(document.id) for document in documents],
            "active": True,
            "last_seen_at": datetime.now(UTC),
        }
        if finding is None:
            finding = ResearchFinding(
                opportunity_id=opportunity.id,
                campaign_id=campaign.id,
                task_id=task.id,
                lane=task.lane,
                finding_key=finding_key,
                **values,
            )
            session.add(finding)
            await session.flush()
        else:
            for field, value in values.items():
                setattr(finding, field, value)
        await _materialize_competitors(session, opportunity, finding, analysis)
        usage = response.get("usage") or {}
        run.actual_model = response.get("model") or settings.openrouter_default_model
        run.output = analysis.model_dump()
        run.usage = usage
        run.cost_usd = usage.get("cost")
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        run.status = RunStatus.succeeded
        task.status = ResearchStatus.completed
        task.completed_at = datetime.now(UTC)
        task.error = None
        await session.commit()
        await refresh_campaign(session, campaign.id)
        await session.refresh(task)
        return task
    except Exception as error:
        run.status = RunStatus.failed
        run.error = str(error)
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        task.status = ResearchStatus.awaiting_analysis
        task.error = str(error)
        await session.commit()
        raise
    finally:
        if owns_client:
            await router.close()


async def refresh_campaign(session: AsyncSession, campaign_id: uuid.UUID) -> ResearchCampaign:
    campaign = await session.get(ResearchCampaign, campaign_id)
    if campaign is None:
        raise LookupError(f"Research campaign {campaign_id} does not exist")
    tasks = list(
        (
            await session.scalars(
                select(ResearchTask).where(ResearchTask.campaign_id == campaign.id)
            )
        ).all()
    )
    required = [task for task in tasks if task.required]
    completed = [task for task in required if task.status == ResearchStatus.completed]
    failed = [
        task for task in required if task.status in {ResearchStatus.failed, ResearchStatus.blocked}
    ]
    campaign.completed_lane_count = len(completed)
    campaign.failed_lane_count = len(failed)
    campaign.coverage_score = sum(task.coverage_score for task in required) / max(len(required), 1)
    campaign.cost_usd = float(
        (
            await session.scalar(
                select(func.coalesce(func.sum(ModelRun.cost_usd), 0.0))
                .select_from(ResearchTask)
                .join(ModelRun, ModelRun.id == ResearchTask.model_run_id)
                .where(ResearchTask.campaign_id == campaign.id)
            )
        )
        or 0.0
    )
    all_terminal = bool(required) and all(task.status in TERMINAL_TASK_STATES for task in required)
    if len(completed) == len(required) and required:
        campaign.status = ResearchStatus.completed
        campaign.completed_at = datetime.now(UTC)
    elif all_terminal and failed:
        campaign.status = ResearchStatus.blocked
    elif any(task.status == ResearchStatus.awaiting_configuration for task in required):
        campaign.status = ResearchStatus.awaiting_configuration
    elif any(
        task.status
        in {
            ResearchStatus.collecting,
            ResearchStatus.awaiting_analysis,
            ResearchStatus.analyzing,
            ResearchStatus.queued,
        }
        for task in required
    ):
        campaign.status = ResearchStatus.running
    verdict = await session.scalar(
        select(ResearchFinding.structured_data)
        .where(
            ResearchFinding.campaign_id == campaign.id,
            ResearchFinding.lane == ResearchLane.contradiction,
            ResearchFinding.active.is_(True),
        )
        .limit(1)
    )
    contradiction_verdict = (verdict or {}).get("verdict", "unknown")
    lane_coverage_passed = all(task.coverage_score >= 0.4 for task in required)
    campaign.summary = {
        "research_gate_passed": campaign.status == ResearchStatus.completed
        and campaign.coverage_score >= 0.6
        and lane_coverage_passed
        and contradiction_verdict != "kill",
        "lane_statuses": {task.lane.value: task.status.value for task in required},
        "lane_coverage": {task.lane.value: task.coverage_score for task in required},
        "contradiction_verdict": contradiction_verdict,
        "recommended_disposition": contradiction_verdict,
    }
    await session.commit()
    await session.refresh(campaign)
    return campaign


def collecting_tasks_query(limit: int) -> Select[tuple[ResearchTask]]:
    return (
        select(ResearchTask)
        .where(ResearchTask.status == ResearchStatus.collecting)
        .order_by(ResearchTask.updated_at)
        .limit(limit)
    )


def analysis_tasks_query(limit: int, *, retry_limit: int = 3) -> Select[tuple[ResearchTask]]:
    return (
        select(ResearchTask)
        .where(
            ResearchTask.status == ResearchStatus.awaiting_analysis,
            ResearchTask.attempts < retry_limit + 1,
        )
        .order_by(ResearchTask.updated_at)
        .limit(limit)
    )


def research_ready_opportunities_query(limit: int) -> Select[tuple[OpportunityHypothesis]]:
    return (
        select(OpportunityHypothesis)
        .outerjoin(
            ResearchCampaign,
            ResearchCampaign.opportunity_id == OpportunityHypothesis.id,
        )
        .where(
            OpportunityHypothesis.status == OpportunityStatus.screened,
            OpportunityHypothesis.evidence_gate_passed.is_(True),
            ResearchCampaign.id.is_(None),
        )
        .order_by(OpportunityHypothesis.confidence.desc())
        .limit(limit)
    )
