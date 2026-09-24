import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from opportunity_api.clients.openrouter import OpenRouterClient
from opportunity_api.config import Settings
from opportunity_api.models import (
    DuplicateKind,
    ModelRun,
    ProcessingStatus,
    PromptVersion,
    RawDocument,
    RunStatus,
    Signal,
    SignalExtraction,
    Source,
)
from opportunity_api.processing.normalization import (
    detect_language,
    evidence_spans,
    exact_content_hash,
    hamming_distance,
    normalize_text,
    simhash64,
)
from opportunity_api.processing.prompts import (
    PROMPT_NAME,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    messages,
    response_format,
)
from opportunity_api.processing.schemas import SignalOntology


async def ensure_prompt_version(session: AsyncSession) -> PromptVersion:
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
            output_schema=SignalOntology.model_json_schema(),
        )
        session.add(prompt)
        await session.flush()
    return prompt


def _completion_content(response: dict[str, Any]) -> dict[str, Any]:
    content = response["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if isinstance(content, str):
        return json.loads(content)
    if isinstance(content, dict):
        return content
    raise ValueError("Model response did not contain structured JSON content")


async def extract_ontology(
    session: AsyncSession,
    signal: Signal,
    document: RawDocument,
    source: Source,
    settings: Settings,
    client: OpenRouterClient,
) -> tuple[SignalOntology, ModelRun]:
    prompt = await ensure_prompt_version(session)
    input_hash = hashlib.sha256(f"{PROMPT_VERSION}\n{signal.exact_hash}".encode()).hexdigest()
    cached = await session.scalar(
        select(ModelRun)
        .where(
            ModelRun.prompt_version_id == prompt.id,
            ModelRun.input_hash == input_hash,
            ModelRun.status == RunStatus.succeeded,
        )
        .order_by(ModelRun.created_at.desc())
        .limit(1)
    )
    if cached:
        return SignalOntology.model_validate(cached.output), cached
    run = ModelRun(
        prompt_version_id=prompt.id,
        provider="openrouter",
        model=settings.openrouter_default_model,
        input_hash=input_hash,
        status=RunStatus.running,
    )
    session.add(run)
    await session.flush()
    started = time.perf_counter()
    try:
        response = await client.complete(
            messages(signal.normalized_title, signal.normalized_text, source.source_type),
            model=settings.openrouter_default_model,
            models=settings.model_route[1:],
            response_format=response_format(),
        )
        ontology = SignalOntology.model_validate(_completion_content(response))
        usage = response.get("usage") or {}
        run.actual_model = response.get("model") or settings.openrouter_default_model
        run.output = ontology.model_dump()
        run.usage = usage
        run.cost_usd = usage.get("cost")
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        run.status = RunStatus.succeeded
        return ontology, run
    except Exception as error:
        run.status = RunStatus.failed
        run.error = str(error)
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        raise


async def create_embedding(
    session: AsyncSession,
    signal: Signal,
    settings: Settings,
    client: OpenRouterClient,
) -> tuple[list[float], str]:
    run = ModelRun(
        provider="openrouter",
        model=settings.openrouter_embedding_model,
        input_hash=signal.exact_hash,
        status=RunStatus.running,
    )
    session.add(run)
    await session.flush()
    started = time.perf_counter()
    try:
        response = await client.embed(
            signal.normalized_text[:30000],
            model=settings.openrouter_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        vector = response["data"][0]["embedding"]
        if len(vector) != settings.embedding_dimensions:
            raise ValueError(
                f"Embedding has {len(vector)} dimensions; expected {settings.embedding_dimensions}"
            )
        usage = response.get("usage") or {}
        model = response.get("model") or settings.openrouter_embedding_model
        run.actual_model = model
        run.output = {"dimensions": len(vector)}
        run.usage = usage
        run.cost_usd = usage.get("cost")
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        run.status = RunStatus.succeeded
        return vector, model
    except Exception as error:
        run.status = RunStatus.failed
        run.error = str(error)
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        raise


async def _deterministic_duplicate(
    session: AsyncSession, signal: Signal, settings: Settings
) -> tuple[Signal | None, DuplicateKind | None, float | None]:
    exact = await session.scalar(
        select(Signal)
        .where(Signal.id != signal.id, Signal.exact_hash == signal.exact_hash)
        .order_by(Signal.created_at)
        .limit(1)
    )
    if exact:
        canonical = (
            await session.get(Signal, exact.canonical_signal_id)
            if exact.canonical_signal_id
            else exact
        )
        return canonical, DuplicateKind.exact, 1.0

    candidates = list(
        (
            await session.scalars(
                select(Signal)
                .where(
                    Signal.id != signal.id,
                    Signal.is_duplicate.is_(False),
                    Signal.status.in_(
                        [ProcessingStatus.succeeded, ProcessingStatus.awaiting_model]
                    ),
                )
                .order_by(Signal.created_at.desc())
                .limit(500)
            )
        ).all()
    )
    for candidate in candidates:
        distance = hamming_distance(signal.simhash, candidate.simhash)
        if distance <= settings.near_duplicate_hamming_threshold:
            return candidate, DuplicateKind.near, 1 - (distance / 64)
    return None, None, None


async def _semantic_duplicate(
    session: AsyncSession, signal: Signal, settings: Settings
) -> tuple[Signal | None, float | None]:
    distance = Signal.embedding.cosine_distance(signal.embedding)
    row = (
        await session.execute(
            select(Signal, distance.label("distance"))
            .where(
                Signal.id != signal.id,
                Signal.embedding.is_not(None),
                Signal.is_duplicate.is_(False),
            )
            .order_by(distance)
            .limit(1)
        )
    ).first()
    if row is None:
        return None, None
    candidate, cosine_distance = row
    similarity = 1 - float(cosine_distance)
    if similarity >= settings.semantic_duplicate_threshold:
        return candidate, similarity
    return None, similarity


async def process_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    settings: Settings,
    *,
    client: OpenRouterClient | None = None,
) -> Signal:
    document = await session.get(RawDocument, document_id)
    if document is None:
        raise LookupError(f"Raw document {document_id} does not exist")
    source = await session.get(Source, document.source_id)
    if source is None:
        raise LookupError(f"Source {document.source_id} does not exist")

    title = normalize_text(document.title)
    text = normalize_text(document.raw_text)
    if not text:
        raise ValueError("Raw document has no processable text")
    signal = await session.scalar(select(Signal).where(Signal.raw_document_id == document.id))
    if signal is None:
        signal = Signal(
            raw_document_id=document.id,
            status=ProcessingStatus.running,
            normalized_title=title,
            normalized_text=text,
            language=document.language or detect_language(text),
            exact_hash=exact_content_hash(title, text),
            simhash=simhash64(f"{title} {text}"),
        )
        session.add(signal)
        await session.flush()
    elif signal.status == ProcessingStatus.succeeded:
        return signal
    else:
        signal.status = ProcessingStatus.running
        signal.error = None
    await session.commit()

    duplicate, kind, score = await _deterministic_duplicate(session, signal, settings)
    if duplicate:
        signal.canonical_signal_id = duplicate.id
        signal.is_duplicate = True
        signal.duplicate_kind = kind
        signal.duplicate_score = score
        signal.status = ProcessingStatus.succeeded
        signal.processed_at = datetime.now(UTC)
        await session.commit()
        return signal

    owns_client = client is None
    router = client or OpenRouterClient(settings)
    if not router.configured:
        signal.status = ProcessingStatus.awaiting_model
        await session.commit()
        await session.refresh(signal)
        if owns_client:
            await router.close()
        return signal

    signal.attempts += 1
    await session.commit()
    try:
        ontology, model_run = await extract_ontology(
            session, signal, document, source, settings, router
        )
        if signal.embedding is None:
            vector, embedding_model = await create_embedding(session, signal, settings, router)
            signal.embedding = vector
            signal.embedding_model = embedding_model
        await session.flush()

        semantic_match, similarity = await _semantic_duplicate(session, signal, settings)
        if semantic_match:
            signal.canonical_signal_id = semantic_match.id
            signal.is_duplicate = True
            signal.duplicate_kind = DuplicateKind.semantic
            signal.duplicate_score = similarity

        extraction = await session.scalar(
            select(SignalExtraction).where(SignalExtraction.signal_id == signal.id)
        )
        values = ontology.model_dump()
        spans = evidence_spans(signal.normalized_text, values.pop("evidence"))
        if extraction is None:
            extraction = SignalExtraction(signal_id=signal.id, model_run_id=model_run.id)
            session.add(extraction)
        extraction.model_run_id = model_run.id
        extraction.is_pain = ontology.is_pain
        extraction.pain_probability = ontology.pain_probability
        extraction.confidence = ontology.confidence
        extraction.industry = ontology.industry
        extraction.user_role = ontology.user_role
        extraction.buyer_role = ontology.buyer_role
        extraction.recurrence = ontology.recurrence
        extraction.urgency = ontology.urgency
        extraction.ontology = values
        extraction.evidence_spans = spans
        signal.status = ProcessingStatus.succeeded
        signal.processed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(signal)
        return signal
    except Exception as error:
        signal.status = ProcessingStatus.failed
        signal.error = str(error)
        await session.commit()
        raise
    finally:
        if owns_client:
            await router.close()


def pending_documents_query(
    limit: int, *, include_model_retries: bool = False, retry_limit: int = 3
) -> Select[tuple[RawDocument]]:
    conditions = [Signal.id.is_(None)]
    if include_model_retries:
        conditions.append(
            Signal.status.in_([ProcessingStatus.awaiting_model, ProcessingStatus.failed])
            & (Signal.attempts < retry_limit)
        )
    return (
        select(RawDocument)
        .outerjoin(Signal, Signal.raw_document_id == RawDocument.id)
        .where(or_(*conditions))
        .order_by(RawDocument.collected_at)
        .limit(limit)
    )


async def processing_metrics(session: AsyncSession) -> dict[str, int]:
    async def count(statement) -> int:
        return int((await session.scalar(statement)) or 0)

    return {
        "total_documents": await count(select(func.count()).select_from(RawDocument)),
        "total_signals": await count(select(func.count()).select_from(Signal)),
        "awaiting_model": await count(
            select(func.count())
            .select_from(Signal)
            .where(Signal.status == ProcessingStatus.awaiting_model)
        ),
        "succeeded": await count(
            select(func.count())
            .select_from(Signal)
            .where(Signal.status == ProcessingStatus.succeeded)
        ),
        "failed": await count(
            select(func.count()).select_from(Signal).where(Signal.status == ProcessingStatus.failed)
        ),
        "duplicates": await count(
            select(func.count()).select_from(Signal).where(Signal.is_duplicate.is_(True))
        ),
        "pains": await count(
            select(func.count())
            .select_from(SignalExtraction)
            .where(SignalExtraction.is_pain.is_(True))
        ),
    }
