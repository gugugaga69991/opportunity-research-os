from opportunity_api.collection.catalog import SOURCE_CATALOG
from opportunity_api.collection.service import source_catalog_entries
from opportunity_api.config import Settings


def test_catalog_covers_every_committed_source_family() -> None:
    slugs = {source["slug"] for source in SOURCE_CATALOG}
    assert slugs == {
        "reddit-operators",
        "industry-news",
        "regulatory-notices",
        "product-changelogs",
        "job-postings",
        "software-reviews",
        "niche-forums",
        "agency-services",
        "template-marketplaces",
        "competitor-websites",
    }


def test_catalog_resolves_actor_configuration() -> None:
    settings = Settings(
        apify_reddit_actor_id="account/reddit",
        apify_web_collector_actor_id="account/web-signals",
    )
    entries = {entry.slug: entry for entry in source_catalog_entries(settings)}
    assert entries["reddit-operators"].actor_id == "account/reddit"
    assert entries["industry-news"].actor_id == "account/web-signals"
    assert all(entry.access_metadata["legal_review_required"] for entry in entries.values())
