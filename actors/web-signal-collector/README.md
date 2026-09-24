# Opportunity OS Web Signal Collector

A reusable custom Apify Actor for approved public RSS feeds and web pages. It emits the stable dataset contract expected by the Opportunity Research OS collection service.

## Modes

- `rss`: extracts entries from RSS and Atom feeds.
- `pages`: extracts a full page using optional CSS selectors and semantic fallbacks.
- `search`: discovers public pages from bounded search queries, then extracts their full content.

The Actor respects `robots.txt` by default, limits concurrency and item volume, records canonical URLs, and does not perform login or access-control bypasses. Search mode delegates URL discovery to the maintained `apify/google-search-scraper` Actor (overridable with `discoveryActorId`), caps it at one result page per query, and then performs content extraction itself.

## Local use

```text
apify run
```

## Deploy

```text
apify login
apify push
```

After deployment, put its Actor ID in `APIFY_WEB_COLLECTOR_ACTOR_ID`. The existing Reddit Actor ID belongs in `APIFY_REDDIT_ACTOR_ID`.

The same deployed Actor can be used for autonomous research by also placing its ID in
`APIFY_RESEARCH_ACTOR_ID`. Research mode accepts `searchQueries`, `maxResultsPerQuery`,
`maxItems`, `discoveryActorId`, and `researchLane`; search discovery and page fetching are both bounded.

For long runs, configure `APIFY_WEBHOOK_URL` as the public URL ending in `/collection/webhooks/apify`; the application appends the private webhook secret.
