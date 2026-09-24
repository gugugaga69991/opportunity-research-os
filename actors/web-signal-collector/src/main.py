import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from apify import Actor
from bs4 import BeautifulSoup


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def selector_text(soup: BeautifulSoup, selector: str | None) -> str | None:
    if not selector:
        return None
    node = soup.select_one(selector)
    return text_or_none(node.get_text(" ", strip=True)) if node else None


def selector_attribute(
    soup: BeautifulSoup, selector: str | None, attribute: str
) -> str | None:
    if not selector:
        return None
    node = soup.select_one(selector)
    return text_or_none(node.get(attribute)) if node else None


async def robots_allows(client: httpx.AsyncClient, url: str, user_agent: str) -> bool:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        response = await client.get(robots_url)
        if response.status_code >= 400:
            return True
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch(user_agent, url)
    except httpx.HTTPError:
        return False


def page_record(
    response: httpx.Response,
    document_type: str,
    selectors: dict[str, str],
) -> dict[str, Any] | None:
    soup = BeautifulSoup(response.text, "html.parser")
    title = selector_text(soup, selectors.get("title"))
    if not title and soup.title:
        title = text_or_none(soup.title.string)
    content_selector = selectors.get("content")
    content_node = soup.select_one(content_selector) if content_selector else None
    content_node = (
        content_node or soup.find("article") or soup.find("main") or soup.body
    )
    raw_text = (
        text_or_none(content_node.get_text(" ", strip=True)) if content_node else None
    )
    if not raw_text:
        return None
    canonical = selector_attribute(soup, selectors.get("canonicalUrl"), "href")
    if not canonical:
        canonical_node = soup.select_one('link[rel="canonical"]')
        canonical = text_or_none(canonical_node.get("href")) if canonical_node else None
    canonical = urljoin(str(response.url), canonical or str(response.url))
    author = selector_text(soup, selectors.get("author"))
    if not author:
        author_node = soup.select_one('meta[name="author"]')
        author = text_or_none(author_node.get("content")) if author_node else None
    published = selector_attribute(soup, selectors.get("publishedAt"), "datetime")
    if not published:
        published_node = soup.select_one(
            'meta[property="article:published_time"], meta[name="date"]'
        )
        published = (
            text_or_none(published_node.get("content")) if published_node else None
        )
    language = text_or_none(soup.html.get("lang")) if soup.html else None
    return {
        "external_id": hashlib.sha256(canonical.encode()).hexdigest(),
        "source_url": str(response.url),
        "canonical_url": canonical,
        "title": title or "",
        "author": author,
        "published_at": published,
        "language": language,
        "raw_text": raw_text,
        "metadata": {
            "document_type": document_type,
            "status_code": response.status_code,
            "collected_at": datetime.now(UTC).isoformat(),
        },
    }


def feed_records(
    content: bytes,
    feed_url: str,
    document_type: str,
) -> list[dict[str, Any]]:
    parsed = feedparser.parse(content)
    records: list[dict[str, Any]] = []
    for entry in parsed.entries:
        source_url = text_or_none(entry.get("link")) or feed_url
        summary = entry.get("summary") or entry.get("description") or ""
        content_parts = entry.get("content") or []
        if content_parts:
            summary = " ".join(str(part.get("value", "")) for part in content_parts)
        raw_text = text_or_none(BeautifulSoup(summary, "html.parser").get_text(" "))
        if not raw_text:
            raw_text = text_or_none(entry.get("title"))
        if not raw_text:
            continue
        external_id = (
            text_or_none(entry.get("id"))
            or hashlib.sha256(source_url.encode()).hexdigest()
        )
        records.append(
            {
                "external_id": external_id,
                "source_url": source_url,
                "canonical_url": source_url,
                "title": text_or_none(entry.get("title")) or "",
                "author": text_or_none(entry.get("author")),
                "published_at": text_or_none(
                    entry.get("published") or entry.get("updated")
                ),
                "language": text_or_none(parsed.feed.get("language")),
                "raw_text": raw_text,
                "metadata": {
                    "document_type": document_type,
                    "feed_url": feed_url,
                    "collected_at": datetime.now(UTC).isoformat(),
                },
            }
        )
    return records


def search_result_urls(items: list[dict[str, Any]], max_results: int) -> list[str]:
    urls: list[str] = []
    for item in items:
        candidates = item.get("organicResults") or []
        for result in candidates:
            url = text_or_none(result.get("url")) if isinstance(result, dict) else None
            if not url or urlsplit(url).scheme not in {"http", "https"} or url in urls:
                continue
            urls.append(url)
            if len(urls) >= max_results:
                return urls
    return urls


def run_dataset_id(run: Any) -> str | None:
    dataset_id = getattr(run, "default_dataset_id", None)
    if dataset_id:
        return str(dataset_id)
    if isinstance(run, dict):
        return text_or_none(
            run.get("defaultDatasetId") or run.get("default_dataset_id")
        )
    return None


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        mode = actor_input.get("mode", "pages")
        document_type = actor_input.get("documentType", "web_document")
        selectors = actor_input.get("selectors") or {}
        max_items = int(actor_input.get("maxItems", 500))
        max_results_per_query = int(actor_input.get("maxResultsPerQuery", 8))
        discovery_actor_id = actor_input.get(
            "discoveryActorId", "apify/google-search-scraper"
        )
        concurrency = int(actor_input.get("maxConcurrency", 5))
        timeout = int(actor_input.get("requestTimeoutSecs", 30))
        respect_robots = bool(actor_input.get("respectRobots", True))
        user_agent = actor_input.get(
            "userAgent", "OpportunityResearchOS/0.1 (+internal-research)"
        )
        start_urls = [
            item["url"] if isinstance(item, dict) else item
            for item in actor_input.get("startUrls", [])
        ]
        semaphore = asyncio.Semaphore(concurrency)
        written = 0
        lock = asyncio.Lock()

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": user_agent},
        ) as client:
            query_by_url: dict[str, str] = {}
            if mode == "search":
                queries = [
                    text
                    for item in actor_input.get("searchQueries", [])[:30]
                    if (
                        text := text_or_none(
                            item.get("query") if isinstance(item, dict) else item
                        )
                    )
                ]

                if not queries:
                    Actor.log.warning("Search mode received no usable search queries")
                elif not discovery_actor_id:
                    raise ValueError("Search mode requires discoveryActorId")
                else:
                    discovery_run = await Actor.call(
                        discovery_actor_id,
                        run_input={
                            "queries": "\n".join(queries),
                            "maxPagesPerQuery": 1,
                            "resultsPerPage": max(10, min(max_results_per_query, 100)),
                            "languageCode": actor_input.get("searchLanguage", "en"),
                            "mobileResults": False,
                            "includeUnfilteredResults": False,
                            "saveHtml": False,
                            "saveHtmlToKeyValueStore": False,
                        },
                    )
                    dataset_id = run_dataset_id(discovery_run)
                    if not dataset_id:
                        raise RuntimeError("Discovery Actor did not return a dataset")
                    dataset = await Actor.open_dataset(id=dataset_id, force_cloud=True)
                    discovery_items = [
                        dict(item)
                        async for item in dataset.iterate_items(
                            limit=len(queries), clean=True
                        )
                    ]
                    for item in discovery_items:
                        search_query = item.get("searchQuery") or {}
                        query = text_or_none(
                            search_query.get("term")
                            if isinstance(search_query, dict)
                            else search_query
                        )
                        for url in search_result_urls([item], max_results_per_query):
                            query_by_url.setdefault(url, query or "unknown")
                start_urls.extend(query_by_url)
            start_urls = list(dict.fromkeys(start_urls))[:max_items]

            async def collect(url: str) -> None:
                nonlocal written
                async with semaphore:
                    if respect_robots and not await robots_allows(
                        client, url, user_agent
                    ):
                        Actor.log.warning("robots.txt denied %s", url)
                        return
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                    except httpx.HTTPError as error:
                        Actor.log.warning("Request failed for %s: %s", url, error)
                        return
                    records = (
                        feed_records(response.content, url, document_type)
                        if mode == "rss"
                        else [page_record(response, document_type, selectors)]
                    )
                    for record in records:
                        if record is None:
                            continue
                        async with lock:
                            if written >= max_items:
                                return
                            record["metadata"].update(
                                {
                                    "search_query": query_by_url.get(url),
                                    "research_lane": actor_input.get("researchLane"),
                                }
                            )
                            await Actor.push_data(record)
                            written += 1

            await asyncio.gather(*(collect(url) for url in start_urls))
        await Actor.set_status_message(f"Collected {written} documents")


if __name__ == "__main__":
    asyncio.run(main())
