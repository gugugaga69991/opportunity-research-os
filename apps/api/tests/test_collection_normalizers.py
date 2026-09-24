from datetime import UTC

from opportunity_api.collection.normalizers import (
    ApifyItemNormalizer,
    canonicalize_url,
    parse_datetime,
)


def test_canonicalize_url_removes_tracking_and_fragment() -> None:
    result = canonicalize_url("HTTPS://Example.COM/path/?utm_source=newsletter&keep=yes#section")
    assert result == "https://example.com/path?keep=yes"


def test_parse_datetime_supports_epoch_milliseconds() -> None:
    parsed = parse_datetime(1_700_000_000_000)
    assert parsed is not None
    assert parsed.tzinfo == UTC
    assert parsed.year == 2023


def test_generic_apify_item_normalizes_to_stable_contract() -> None:
    item = {
        "external_id": "article-7",
        "source_url": "https://example.com/story?utm_campaign=test",
        "canonical_url": "https://example.com/story",
        "title": "  New reporting rule  ",
        "author": "Analyst",
        "published_at": "2026-08-01T12:00:00Z",
        "language": "en",
        "raw_text": "Businesses must file a new report every month.",
    }
    document = ApifyItemNormalizer().normalize(
        item,
        source_slug="industry-news",
        adapter_key="generic_apify",
        config={"document_type": "news_article"},
        external_run_id="run-1",
        external_dataset_id="dataset-1",
    )
    assert document is not None
    assert document.title == "New reporting rule"
    assert document.document_type == "news_article"
    assert document.canonical_url == "https://example.com/story"
    assert len(document.content_hash) == 64
    assert document.provenance["external_run_id"] == "run-1"


def test_reddit_fallback_fields_and_invalid_items() -> None:
    normalizer = ApifyItemNormalizer()
    document = normalizer.normalize(
        {
            "id": "abc",
            "url": "https://reddit.com/r/ops/comments/abc",
            "title": "Manual process",
            "selfText": "We reconcile this in Excel every Friday.",
            "createdAt": 1_700_000_000,
        },
        source_slug="reddit-operators",
        adapter_key="reddit_apify",
        config={"document_type": "reddit_post"},
        external_run_id="run-2",
        external_dataset_id="dataset-2",
    )
    assert document is not None
    assert document.raw_text == "We reconcile this in Excel every Friday."
    assert (
        normalizer.normalize(
            {"title": "No usable content"},
            source_slug="bad",
            adapter_key="generic_apify",
            config={},
            external_run_id=None,
            external_dataset_id=None,
        )
        is None
    )
