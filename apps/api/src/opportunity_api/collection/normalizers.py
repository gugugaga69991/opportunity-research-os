import hashlib
import json
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


class NormalizedDocument(BaseModel):
    source_external_id: str | None = None
    source_url: str
    canonical_url: str
    document_type: str
    title: str = ""
    author: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    raw_text: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    content_hash: str


def compact_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        parsed = datetime.fromtimestamp(timestamp, tz=UTC)
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError):
                return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def get_nested(item: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = item
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def document_hash(text: str, title: str, canonical_url: str) -> str:
    primary = compact_text(text).lower()
    fallback = f"{compact_text(title).lower()}|{canonical_url}"
    return hashlib.sha256((primary or fallback).encode("utf-8")).hexdigest()


class ApifyItemNormalizer:
    DEFAULT_MAP = {
        "source_external_id": "external_id",
        "source_url": "source_url",
        "canonical_url": "canonical_url",
        "title": "title",
        "author": "author",
        "published_at": "published_at",
        "language": "language",
        "raw_text": "raw_text",
    }

    REDDIT_MAP = {
        "source_external_id": "id",
        "source_url": "url",
        "canonical_url": "url",
        "title": "title",
        "author": "author",
        "published_at": "createdAt",
        "language": "language",
        "raw_text": "body",
    }

    def normalize(
        self,
        item: dict[str, Any],
        *,
        source_slug: str,
        adapter_key: str,
        config: dict[str, Any],
        external_run_id: str | None,
        external_dataset_id: str | None,
    ) -> NormalizedDocument | None:
        mapping = dict(self.REDDIT_MAP if adapter_key == "reddit_apify" else self.DEFAULT_MAP)
        mapping.update(config.get("field_map", {}))
        values = {field: get_nested(item, path) for field, path in mapping.items()}
        raw_text = compact_text(values.get("raw_text"))
        title = compact_text(values.get("title"))
        source_url = compact_text(values.get("source_url"))
        if adapter_key == "reddit_apify" and not raw_text:
            raw_text = compact_text(item.get("text") or item.get("selfText") or title)
        if not source_url:
            source_url = compact_text(item.get("url") or item.get("link") or item.get("sourceUrl"))
        if not raw_text or not source_url:
            return None
        canonical_url = canonicalize_url(compact_text(values.get("canonical_url")) or source_url)
        return NormalizedDocument(
            source_external_id=compact_text(values.get("source_external_id")) or None,
            source_url=source_url,
            canonical_url=canonical_url,
            document_type=config.get("document_type", "web_document"),
            title=title,
            author=compact_text(values.get("author")) or None,
            published_at=parse_datetime(values.get("published_at")),
            language=compact_text(values.get("language")) or None,
            raw_text=raw_text,
            raw_payload=json.loads(json.dumps(item, default=str)),
            provenance={
                "source_slug": source_slug,
                "adapter_key": adapter_key,
                "external_run_id": external_run_id,
                "external_dataset_id": external_dataset_id,
            },
            content_hash=document_hash(raw_text, title, canonical_url),
        )
