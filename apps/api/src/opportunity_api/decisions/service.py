import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.clients.openrouter import OpenRouterClient
from opportunity_api.config import Settings
from opportunity_api.decisions.contracts import DecisionAnalysis, validate_expert_dimensions
from opportunity_api.decisions.prompts import (
    PROMPT_NAME,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    messages,
    response_format,
)
from opportunity_api.decisions.scoring import score_opportunity
from opportunity_api.models import (
    DecisionDisposition,
    DecisionStatus,
    ModelRun,
    OpportunityDecision,
    OpportunityHypothesis,
    OpportunityRisk,
    OpportunityScore,
    OpportunityStatus,
    PromptVersion,
    RawDocument,
    ResearchCampaign,
    ResearchFinding,
    ResearchStatus,
    RunStatus,
    ScoreDimension,
    ScoringProfile,
)
from opportunity_api.opportunities.service import transition_opportunity

DECISION_VERSION = "1.0.0"


async def active_scoring_weights(
    session: AsyncSession,
) -> dict[ScoreDimension, float] | None:
    profile = await session.scalar(
        select(ScoringProfile)
        .where(ScoringProfile.active.is_(True))
        .order_by(ScoringProfile.activated_at.desc())
    )
    if profile is None:
        return None
    return {ScoreDimension(key): float(value) for key, value in profile.weights.items()}


def _response_content(response: dict[str, Any]) -> dict[str, Any]:
    content = response["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if isinstance(content, str):
        return json.loads(content)
    if isinstance(content, dict):
        return content
    raise ValueError("Decision model response did not contain structured JSON")


async def ensure_decision_prompt(session: AsyncSession) -> PromptVersion:
    prompt = await session.scalar(
        select(PromptVersion).where(
            PromptVersion.name == PROMPT_NAME,
            PromptVersion.version == PROMPT_VERSION,
        )
    )
    if prompt is None:
        prompt = PromptVersion(
            name=PROMPT_NAME,
            version=PROMPT_VERSION,
            template=SYSTEM_PROMPT,
            output_schema=DecisionAnalysis.model_json_schema(),
        )
        session.add(prompt)
        await session.flush()
    return prompt


async def create_decision(session: AsyncSession, campaign_id: uuid.UUID) -> OpportunityDecision:
    campaign = await session.get(ResearchCampaign, campaign_id)
    if campaign is None:
        raise LookupError(f"Research campaign {campaign_id} does not exist")
    if campaign.status != ResearchStatus.completed:
        raise ValueError("Research campaign must complete before final scoring")
    decision = await session.scalar(
        select(OpportunityDecision).where(
            OpportunityDecision.campaign_id == campaign.id,
            OpportunityDecision.version == DECISION_VERSION,
        )
    )
    if decision is None:
        decision = OpportunityDecision(
            opportunity_id=campaign.opportunity_id,
            campaign_id=campaign.id,
            version=DECISION_VERSION,
            status=DecisionStatus.awaiting_analysis,
            research_coverage=campaign.coverage_score,
        )
        session.add(decision)
        await session.commit()
        await session.refresh(decision)
    return decision


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
            "workaround": opportunity.current_workaround,
            "economic_cost": opportunity.economic_cost,
            "existing_spend": opportunity.existing_spend,
            "why_now": opportunity.why_now,
            "desired_outcome": opportunity.desired_outcome,
            "solution_concept": opportunity.solution_concept,
            "evidence_counts": {
                "signals": opportunity.confirming_signal_count,
                "sources": opportunity.confirming_source_count,
                "evidence_types": opportunity.evidence_type_count,
                "contradictions": opportunity.contradiction_count,
            },
            "thesis": opportunity.thesis,
        },
        ensure_ascii=False,
    )


def _research_packet(findings: list[ResearchFinding], documents: list[RawDocument]) -> str:
    finding_packet = [
        {
            "lane": finding.lane.value,
            "summary": finding.summary,
            "confidence": finding.confidence,
            "analysis": finding.structured_data,
            "evidence_urls": finding.evidence_urls,
        }
        for finding in findings
    ]
    parts = ["FINDINGS:\n" + json.dumps(finding_packet, ensure_ascii=False)]
    budget = 90_000
    for index, document in enumerate(documents, start=1):
        part = (
            f"\n---\nSOURCE {index}\nURL: {document.canonical_url}\n"
            f"TITLE: {document.title}\nTEXT:\n{document.raw_text[:6000]}"
        )
        if sum(len(item) for item in parts) + len(part) > budget:
            break
        parts.append(part)
    return "".join(parts)


def _verify_references(analysis: DecisionAnalysis, documents: list[RawDocument]) -> set[str]:
    by_url = {document.canonical_url: document.raw_text.casefold() for document in documents}
    verified_urls: set[str] = set()
    for reference in analysis.evidence:
        source_text = by_url.get(reference.url)
        reference.verified = bool(
            source_text and reference.quote and reference.quote.casefold() in source_text
        )
        if reference.verified:
            verified_urls.add(reference.url)
    return verified_urls


def _finding_map(findings: list[ResearchFinding]) -> dict[str, dict]:
    return {
        finding.lane.value: {
            "structured_data": finding.structured_data,
            "confidence": finding.confidence,
            "evidence_urls": finding.evidence_urls,
        }
        for finding in findings
    }


def _thesis(
    opportunity: OpportunityHypothesis,
    analysis: DecisionAnalysis,
    score: Any,
) -> dict:
    return {
        "name": opportunity.name,
        "industry": opportunity.industry,
        "icp": opportunity.icp,
        "user": opportunity.user_role,
        "buyer": opportunity.buyer_role,
        "workflow": opportunity.core_workflow,
        "problem": opportunity.problem,
        "frequency": opportunity.frequency,
        "current_workaround": opportunity.current_workaround,
        "economic_cost": opportunity.economic_cost,
        "existing_spend": opportunity.existing_spend,
        "why_now": opportunity.why_now,
        "solution_concept": opportunity.solution_concept,
        "value_proposition": opportunity.value_proposition,
        "data_requirements": analysis.data_requirements,
        "integration_requirements": analysis.integration_requirements,
        "ai_advantage": analysis.ai_advantage,
        "defensibility": analysis.defensibility,
        "expansion_path": analysis.expansion_path,
        "time_to_value": analysis.realistic_time_to_value,
        "kill_criteria": analysis.kill_criteria,
        "investment_case": analysis.investment_case.model_dump(),
        "score": score.adjusted_score,
        "confidence": score.confidence,
        "disposition": score.disposition.value,
    }


async def analyze_decision(
    session: AsyncSession,
    decision_id: uuid.UUID,
    settings: Settings,
    *,
    client: OpenRouterClient | None = None,
) -> OpportunityDecision:
    decision = await session.get(OpportunityDecision, decision_id)
    if decision is None:
        raise LookupError(f"Opportunity decision {decision_id} does not exist")
    if decision.status == DecisionStatus.completed:
        return decision
    campaign = await session.get(ResearchCampaign, decision.campaign_id)
    opportunity = await session.get(OpportunityHypothesis, decision.opportunity_id)
    if campaign is None or opportunity is None:
        raise LookupError("Decision campaign or opportunity does not exist")
    findings = list(
        (
            await session.scalars(
                select(ResearchFinding).where(
                    ResearchFinding.campaign_id == campaign.id,
                    ResearchFinding.active.is_(True),
                )
            )
        ).all()
    )
    document_ids = {
        uuid.UUID(document_id) for finding in findings for document_id in finding.document_ids
    }
    documents = (
        list(
            (
                await session.scalars(select(RawDocument).where(RawDocument.id.in_(document_ids)))
            ).all()
        )
        if document_ids
        else []
    )
    owns_client = client is None
    router = client or OpenRouterClient(settings)
    if not router.configured:
        decision.status = DecisionStatus.awaiting_analysis
        decision.error = "OPENROUTER_API_KEY is not configured"
        await session.commit()
        if owns_client:
            await router.close()
        return decision
    prompt = await ensure_decision_prompt(session)
    packet = _research_packet(findings, documents)
    input_hash = hashlib.sha256(f"{PROMPT_VERSION}:{opportunity.id}:{packet}".encode()).hexdigest()
    run = ModelRun(
        prompt_version_id=prompt.id,
        provider="openrouter",
        model=settings.openrouter_default_model,
        input_hash=input_hash,
        status=RunStatus.running,
    )
    session.add(run)
    await session.flush()
    decision.model_run_id = run.id
    decision.status = DecisionStatus.analyzing
    decision.attempts += 1
    decision.started_at = decision.started_at or datetime.now(UTC)
    decision.error = None
    await session.commit()
    started = time.perf_counter()
    try:
        response = await router.complete(
            messages(_opportunity_context(opportunity), packet),
            model=settings.openrouter_default_model,
            models=settings.model_route[1:],
            response_format=response_format(),
        )
        analysis = DecisionAnalysis.model_validate(_response_content(response))
        validate_expert_dimensions(analysis)
        verified_urls = _verify_references(analysis, documents)
        score = score_opportunity(
            opportunity,
            _finding_map(findings),
            analysis,
            campaign.coverage_score,
            bool(campaign.summary.get("research_gate_passed")),
            verified_urls,
            advance_threshold=settings.decision_advance_threshold,
            kill_threshold=settings.decision_kill_threshold,
            minimum_confidence=settings.decision_min_confidence,
            weights=await active_scoring_weights(session),
        )
        await session.execute(
            update(OpportunityRisk)
            .where(OpportunityRisk.decision_id == decision.id)
            .values(active=False)
        )
        for item in score.dimensions:
            record = await session.scalar(
                select(OpportunityScore).where(
                    OpportunityScore.decision_id == decision.id,
                    OpportunityScore.dimension == item.dimension,
                )
            )
            values = {
                "score": item.score,
                "weight": item.weight,
                "weighted_score": item.weighted_score,
                "confidence": item.confidence,
                "rationale": item.rationale,
                "evidence_urls": item.evidence_urls,
                "inputs": item.inputs,
            }
            if record is None:
                session.add(
                    OpportunityScore(
                        decision_id=decision.id,
                        dimension=item.dimension,
                        **values,
                    )
                )
            else:
                for field, value in values.items():
                    setattr(record, field, value)
        for risk in analysis.risks:
            key = hashlib.sha256(f"{risk.category}:{risk.claim}".casefold().encode()).hexdigest()
            record = await session.scalar(
                select(OpportunityRisk).where(
                    OpportunityRisk.decision_id == decision.id,
                    OpportunityRisk.risk_key == key,
                )
            )
            values = {
                "category": risk.category,
                "severity": risk.severity,
                "claim": risk.claim,
                "implication": risk.implication,
                "mitigation": risk.mitigation,
                "evidence_urls": sorted(set(risk.evidence_urls) & verified_urls),
                "active": True,
            }
            if record is None:
                session.add(
                    OpportunityRisk(
                        decision_id=decision.id,
                        risk_key=key,
                        **values,
                    )
                )
            else:
                for field, value in values.items():
                    setattr(record, field, value)
        usage = response.get("usage") or {}
        run.actual_model = response.get("model") or settings.openrouter_default_model
        run.output = analysis.model_dump()
        run.usage = usage
        run.cost_usd = usage.get("cost")
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        run.status = RunStatus.succeeded
        decision.status = DecisionStatus.completed
        decision.disposition = score.disposition
        decision.raw_score = score.raw_score
        decision.confidence_score = score.confidence
        decision.adjusted_score = score.adjusted_score
        decision.research_coverage = campaign.coverage_score
        decision.hard_kill_triggered = bool(score.hard_kills)
        decision.penalties = score.penalties
        decision.hard_kills = score.hard_kills
        decision.thesis = _thesis(opportunity, analysis, score)
        decision.red_team = {
            "summary": analysis.summary,
            "verdict": analysis.red_team_verdict,
            "objections": analysis.objections,
            "kill_criteria": analysis.kill_criteria,
            "verified_evidence_urls": sorted(verified_urls),
        }
        decision.cost_usd = float(run.cost_usd or 0)
        decision.completed_at = datetime.now(UTC)
        decision.error = None
        target = {
            DecisionDisposition.advance: OpportunityStatus.thesis_ready,
            DecisionDisposition.watchlist: OpportunityStatus.watchlist,
            DecisionDisposition.kill: OpportunityStatus.killed,
        }[score.disposition]
        await session.commit()
        if opportunity.status != target:
            await transition_opportunity(
                session,
                opportunity,
                target,
                (
                    f"Decision {score.disposition.value}: adjusted score "
                    f"{score.adjusted_score:.1f}, confidence {score.confidence:.2f}."
                ),
                "decision-engine",
            )
        await session.refresh(decision)
        return decision
    except Exception as error:
        run.status = RunStatus.failed
        run.error = str(error)
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        decision.status = DecisionStatus.failed
        decision.error = str(error)
        await session.commit()
        raise
    finally:
        if owns_client:
            await router.close()


def scoring_ready_campaigns_query(limit: int) -> Select[tuple[ResearchCampaign]]:
    return (
        select(ResearchCampaign)
        .outerjoin(
            OpportunityDecision,
            (OpportunityDecision.campaign_id == ResearchCampaign.id)
            & (OpportunityDecision.version == DECISION_VERSION),
        )
        .where(
            ResearchCampaign.status == ResearchStatus.completed,
            ResearchCampaign.campaign_type == "baseline",
            OpportunityDecision.id.is_(None),
        )
        .order_by(ResearchCampaign.completed_at)
        .limit(limit)
    )


def pending_decisions_query(
    limit: int, *, retry_limit: int = 3
) -> Select[tuple[OpportunityDecision]]:
    return (
        select(OpportunityDecision)
        .where(
            OpportunityDecision.status.in_(
                {DecisionStatus.awaiting_analysis, DecisionStatus.failed}
            ),
            OpportunityDecision.attempts < retry_limit,
        )
        .order_by(OpportunityDecision.updated_at)
        .limit(limit)
    )
