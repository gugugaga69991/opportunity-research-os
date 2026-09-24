import hashlib
import re
import unicodedata
from dataclasses import dataclass

from opportunity_api.models import ClusterType, EntityType

SPACE_RE = re.compile(r"\s+")
PUNCTUATION_RE = re.compile(r"[^\w+#./ -]+", re.UNICODE)
EMPTY_VALUES = {"", "unknown", "none", "n/a", "na", "not specified", "not available"}


@dataclass(frozen=True)
class EntityCandidate:
    entity_type: EntityType
    relation: str
    display_value: str
    normalized_value: str
    confidence: float


@dataclass(frozen=True)
class ClusterDescriptor:
    cluster_type: ClusterType
    cluster_key: str
    title: str
    summary: str
    anchor_values: frozenset[str]
    recurrence_score: float


def normalize_entity_value(value: str) -> str:
    normalized = (value or "").translate(str.maketrans("", "", "™®©"))
    normalized = unicodedata.normalize("NFKC", normalized).casefold().strip()
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    return SPACE_RE.sub(" ", normalized).strip(" .-/")[:240]


def _candidate(
    entity_type: EntityType,
    relation: str,
    value: str,
    confidence: float,
) -> EntityCandidate | None:
    display = SPACE_RE.sub(" ", str(value or "")).strip()[:300]
    normalized = normalize_entity_value(display)
    if normalized in EMPTY_VALUES or len(normalized) < 2:
        return None
    return EntityCandidate(entity_type, relation, display, normalized, confidence)


def entities_from_ontology(ontology: dict, confidence: float) -> list[EntityCandidate]:
    scalar_fields = {
        "industry": (EntityType.industry, "industry"),
        "subindustry": (EntityType.subindustry, "subindustry"),
        "company_type": (EntityType.company_type, "company_type"),
        "company_size": (EntityType.company_size, "company_size"),
        "user_role": (EntityType.role, "user_role"),
        "buyer_role": (EntityType.role, "buyer_role"),
        "trigger": (EntityType.trigger, "trigger"),
        "task": (EntityType.task, "task"),
        "pain_type": (EntityType.pain_type, "pain_type"),
        "recurrence": (EntityType.recurrence, "recurrence"),
        "workaround": (EntityType.workaround, "workaround"),
        "desired_outcome": (EntityType.desired_outcome, "desired_outcome"),
    }
    list_fields = {
        "tools": (EntityType.tool, "uses_tool"),
        "current_software": (EntityType.software, "uses_software"),
        "inputs": (EntityType.input, "workflow_input"),
        "outputs": (EntityType.output, "workflow_output"),
        "current_workflow": (EntityType.workflow_step, "workflow_step"),
        "manual_steps": (EntityType.workflow_step, "manual_step"),
    }
    candidates: dict[tuple[EntityType, str, str], EntityCandidate] = {}
    for field, (entity_type, relation) in scalar_fields.items():
        item = _candidate(entity_type, relation, ontology.get(field, ""), confidence)
        if item:
            candidates[(item.entity_type, item.relation, item.normalized_value)] = item
    for field, (entity_type, relation) in list_fields.items():
        values = ontology.get(field) or []
        for value in values if isinstance(values, list) else []:
            item = _candidate(entity_type, relation, value, confidence)
            if item:
                candidates[(item.entity_type, item.relation, item.normalized_value)] = item
    return list(candidates.values())


def entities_from_document_context(payload: dict, confidence: float = 0.8) -> list[EntityCandidate]:
    candidates: dict[str, EntityCandidate] = {}
    for key in (
        "company",
        "companyName",
        "company_name",
        "employer",
        "organization",
        "organizationName",
        "organization_name",
        "vendor",
    ):
        value = payload.get(key)
        if isinstance(value, dict):
            value = value.get("name")
        if not isinstance(value, str):
            continue
        item = _candidate(EntityType.company, "mentions_company", value, confidence)
        if item:
            candidates[item.normalized_value] = item
    return list(candidates.values())


def recurrence_strength(ontology: dict) -> float:
    value = f"{ontology.get('recurrence', '')} {ontology.get('frequency', '')}".casefold()
    scores = {
        "hour": 1.0,
        "daily": 0.95,
        "day": 0.95,
        "weekly": 0.85,
        "week": 0.85,
        "monthly": 0.7,
        "month": 0.7,
        "quarter": 0.45,
        "annual": 0.25,
        "year": 0.25,
        "recurring": 0.75,
        "one-time": 0.1,
        "once": 0.1,
    }
    return max((score for token, score in scores.items() if token in value), default=0.4)


def _fingerprint(cluster_type: ClusterType, components: list[str]) -> str:
    stable = "|".join([cluster_type.value, *(normalize_entity_value(x) for x in components)])
    return hashlib.sha256(stable.encode()).hexdigest()


def cluster_descriptors(
    ontology: dict,
    *,
    is_pain: bool,
    source_type: str,
    document_type: str,
    fallback_title: str,
) -> list[ClusterDescriptor]:
    industry = ontology.get("industry", "")
    role = ontology.get("user_role", "")
    task = ontology.get("task", "")
    pain_type = ontology.get("pain_type", "")
    trigger = ontology.get("trigger", "")
    summary = ontology.get("summary", "") or fallback_title
    anchors = frozenset(
        value
        for value in map(normalize_entity_value, (industry, role, task, pain_type, trigger))
        if value not in EMPTY_VALUES
    )
    recurrence = recurrence_strength(ontology)
    descriptors: list[ClusterDescriptor] = []
    if is_pain:
        title = " / ".join(value for value in (task, role, industry) if value) or summary
        pain_components = [industry, role, task, pain_type]
        if sum(bool(normalize_entity_value(value)) for value in pain_components) < 2:
            pain_components.append(summary)
        descriptors.append(
            ClusterDescriptor(
                ClusterType.pain,
                _fingerprint(ClusterType.pain, pain_components),
                title[:300],
                summary,
                anchors,
                recurrence,
            )
        )
    if task or ontology.get("current_workflow"):
        title = " / ".join(value for value in (task, role) if value) or summary
        workflow_components = [industry, role, task]
        if not normalize_entity_value(task):
            workflow_components.extend(ontology.get("current_workflow") or [summary])
        descriptors.append(
            ClusterDescriptor(
                ClusterType.workflow,
                _fingerprint(ClusterType.workflow, workflow_components),
                title[:300],
                summary,
                anchors,
                recurrence,
            )
        )
    change_context = f"{source_type} {document_type}".casefold()
    if any(token in change_context for token in ("news", "regulat", "changelog", "filing")):
        title = fallback_title or trigger or summary
        descriptors.append(
            ClusterDescriptor(
                ClusterType.change,
                _fingerprint(ClusterType.change, [industry, trigger, title]),
                title[:300],
                summary,
                anchors,
                recurrence,
            )
        )
    return descriptors
