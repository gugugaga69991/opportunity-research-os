import importlib.util
from pathlib import Path

import httpx

MODULE_PATH = Path(__file__).parents[1] / "src" / "main.py"
SPEC = importlib.util.spec_from_file_location("web_signal_actor", MODULE_PATH)
assert SPEC and SPEC.loader
actor_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actor_module)


def test_page_record_uses_semantic_fallbacks() -> None:
    html = """
    <html lang="en"><head><title>New rule</title>
    <link rel="canonical" href="/canonical" />
    <meta name="author" content="Regulator" />
    <meta property="article:published_time" content="2026-08-01T10:00:00Z" />
    </head><body><article>Companies must reconcile reports monthly.</article></body></html>
    """
    request = httpx.Request("GET", "https://example.com/story")
    response = httpx.Response(200, text=html, request=request)
    record = actor_module.page_record(response, "regulatory_notice", {})
    assert record is not None
    assert record["title"] == "New rule"
    assert record["canonical_url"] == "https://example.com/canonical"
    assert record["author"] == "Regulator"
    assert "reconcile reports" in record["raw_text"]


def test_feed_records_emit_stable_dataset_contract() -> None:
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
    <title>Industry feed</title><language>en</language><item><guid>item-1</guid>
    <title>API changed</title><link>https://example.com/change</link>
    <description>Teams must update their integration.</description>
    <pubDate>Thu, 01 Aug 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
    records = actor_module.feed_records(
        feed, "https://example.com/feed", "news_article"
    )
    assert len(records) == 1
    assert records[0]["external_id"] == "item-1"
    assert records[0]["source_url"] == "https://example.com/change"
    assert records[0]["raw_text"] == "Teams must update their integration."


def test_search_result_urls_are_deduplicated_and_bounded() -> None:
    items = [
        {
            "organicResults": [
                {"url": "https://example.com/one"},
                {"url": "https://example.com/one"},
                {"url": "javascript:alert(1)"},
                {"url": "https://example.com/two"},
                {"url": "https://example.com/three"},
            ]
        }
    ]
    assert actor_module.search_result_urls(items, 2) == [
        "https://example.com/one",
        "https://example.com/two",
    ]


def test_run_dataset_id_supports_sdk_model_and_api_shape() -> None:
    class Run:
        default_dataset_id = "sdk-dataset"

    assert actor_module.run_dataset_id(Run()) == "sdk-dataset"
    assert (
        actor_module.run_dataset_id({"defaultDatasetId": "api-dataset"})
        == "api-dataset"
    )
