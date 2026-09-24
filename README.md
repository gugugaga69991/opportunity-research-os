# Opportunity Research OS

An evidence-first research operating system for discovering recurring SaaS opportunities from real workflows and emerging market changes.

## Foundation stack

- Next.js dashboard
- FastAPI application API
- PostgreSQL with pgvector
- Durable PostgreSQL job queue with bounded batch runners
- OpenRouter model gateway
- Apify collection gateway
- Docker Compose local environment

## Start locally

1. Copy `.env.example` to `.env` and add credentials when available.
2. Run `docker compose up --build`.
3. Open `http://localhost:3000` for the dashboard.
4. Open `http://localhost:8000/docs` for API documentation.

The API runs database migrations automatically at startup. OpenRouter and Apify are optional for health checks; missing keys are reported as unconfigured rather than crashing the application.

## Repository map

```text
apps/web       Dashboard and research control center
apps/api       API, database models, integrations, and batch runner
infra          Deployment notes and future infrastructure definitions
```

## Common commands

```text
npm run dev:web
npm run build:web
docker compose up --build
docker compose down
docker compose --profile jobs run --rm jobs
```

Never commit `.env` or API keys.

## Cloud runtime

The production-shaped free-tier deployment is already described in code:

- `vercel.json` builds and serves the Next.js control center.
- `render.yaml` runs FastAPI and database migrations on Render.
- Neon supplies PostgreSQL and pgvector through `DATABASE_URL`.
- `.github/workflows/research-cycle.yml` schedules due research and drains a bounded PostgreSQL job batch. It remains manual until the hosted database and repository secrets are configured; the six-hour schedule is enabled after deployment.
- Apify runs collectors independently of the local computer.

The API and dashboard can sleep between requests. Collection and research do not depend on this PC staying on.

## Collection layer

Step 2 adds a configuration-driven source registry and a reusable custom Apify Actor under `actors/web-signal-collector`.

Key API operations:

```text
POST  /collection/sources/bootstrap
GET   /collection/sources
PATCH /collection/sources/{source_id}
PUT   /collection/sources/{source_id}/schedule
POST  /collection/sources/{source_id}/runs
GET   /collection/runs
GET   /collection/documents
POST  /collection/webhooks/apify/{secret}
```

Bootstrap creates the ten committed source families in `review_required` state. Before enabling collection for a source:

1. Configure its Actor and input.
2. Record its access/terms assessment.
3. Change `access_risk` to `approved`.
4. Start a manual run or configure its schedule.

Actor runs are asynchronous. Completion webhooks trigger paginated dataset retrieval, normalization into a stable contract, content-hash deduplication, and raw evidence persistence with full provenance.

## Signal processing layer

Step 3 turns raw evidence into traceable research signals. The batch runner automatically:

1. Normalizes text and detects its language.
2. Removes exact and near duplicates using SHA-256 and SimHash before spending on AI.
3. Extracts a strict workflow-and-pain ontology through OpenRouter with model fallbacks.
4. Verifies every evidence quote against the normalized source text.
5. Creates 1,536-dimension embeddings and uses pgvector for semantic deduplication.
6. Stores prompt version, requested and actual model, token usage, cost, latency, confidence, and evidence spans.

Without an OpenRouter key, deterministic work still completes and signals stop safely in `awaiting_model`. Adding the key and calling the backfill endpoint resumes them idempotently.

```text
POST /processing/documents/{document_id}
POST /processing/backfill
GET  /processing/signals
GET  /processing/signals/{signal_id}
GET  /processing/metrics
```

## Evidence intelligence layer

Step 4 converts processed signals into a queryable evidence graph and corroborated cluster system without making additional model calls.

It materializes industries, named companies, company types, roles, triggers, tasks, pain types, tools, software, workflow steps, workarounds, and desired outcomes as normalized entities. Supported co-occurrences become graph edges, while canonical signals can enter pain, workflow, and emerging-change clusters.

Cluster assignment uses stable fingerprints first, then embedding similarity with shared entity anchors. Each cluster tracks independent sources, evidence categories, recurrence, first and last observation, 30-day velocity, and a bounded corroboration score. Empty, failed, and stale jobs have explicit recoverable states.

```text
POST /intelligence/signals/{signal_id}/cluster
POST /intelligence/backfill
GET  /intelligence/clusters
GET  /intelligence/clusters/{cluster_id}
GET  /intelligence/entities
GET  /intelligence/relationships
GET  /intelligence/metrics
```

## Opportunity hypothesis layer

Step 5 converts pain and emerging-change clusters into structured SaaS hypotheses. It remains deterministic and evidence-first: no additional model call is needed to create a draft hypothesis.

Pain-led hypotheses originate from recurring pain clusters. Change-led hypotheses originate from news, regulatory, filing, or changelog clusters, but cannot pass the evidence gate until a related pain cluster confirms real operational burden.

Each hypothesis contains its ICP, user, buyer, workflow, problem, frequency, workaround, observed cost/spend, why-now context, desired outcome, cautious solution concept, and value proposition. Signal-level supporting and contradicting evidence, related clusters, source categories, gate checks, and lifecycle transitions form a permanent genealogy.

Automatic promotion to `screened` requires all of:

- Enough confirming signals
- Multiple independent sources
- Multiple evidence categories
- A recurring workflow
- An identifiable buyer
- Observed time, consequence, or spending evidence
- Supporting evidence that outweighs collected contradictions
- Confirming pain for change-led hypotheses

```text
POST  /opportunities/clusters/{cluster_id}/generate
POST  /opportunities/generate/backfill
GET   /opportunities
GET   /opportunities/{opportunity_id}
PATCH /opportunities/{opportunity_id}/state
POST  /opportunities/{opportunity_id}/refresh
GET   /opportunities/metrics
```

## Autonomous research layer

Step 6 opens a five-lane research campaign for every evidence-gated opportunity:

- Competition maps direct, adjacent, service, free, and internal substitutes.
- Economics verifies labor cost, consequence cost, existing spend, and budget signals.
- Market estimates exact-fit reachable accounts from bottom-up evidence.
- Distribution finds concrete buyer lists, communities, events, and triggers.
- Contradiction actively searches for reasons to reject the opportunity.

Each lane receives deterministic search queries and a bounded Apify collection contract. The
batch runner collects source documents, sends only those documents to a lane-specific strict OpenRouter
schema, verifies every cited quote against the stored source text, and materializes versioned
findings and competitor profiles. A campaign passes the research gate only when every required
lane completes, overall and per-lane coverage thresholds pass, and the contradiction lane does not
return a `kill` verdict.

Campaigns remain safely in `awaiting_configuration` when the research Actor, Apify credential,
OpenRouter credential, or source approval is absent. The scheduler resumes them automatically when
configuration becomes available.

```text
POST /research/opportunities/{opportunity_id}/start
POST /research/backfill
POST /research/campaigns/{campaign_id}/dispatch
POST /research/tasks/{task_id}/dispatch
POST /research/tasks/{task_id}/analyze
GET  /research/campaigns
GET  /research/campaigns/{campaign_id}
GET  /research/findings
GET  /research/competitors
GET  /research/metrics
```

## Opportunity decision layer

Step 7 converts completed research into a transparent investment decision. Eight dimensions are
calculated directly from evidence and six expert dimensions are assessed through a strict,
versioned red-team contract. The committed weights sum to 100 points:

```text
Pain severity 12%            Recurring frequency 10%
Existing spend 9%            Willingness to pay 8%
Competition weakness 10%     Distribution quality 10%
Retention 8%                  Buildability 7%
Time-to-value 6%              AI advantage 5%
Defensibility 5%              Market timing 4%
Reachable TAM 3%              Expansion 3%
```

Every dimension stores its score, weight, weighted contribution, confidence, rationale, inputs,
and verified evidence URLs. Research gaps, low-confidence dimensions, supported high risks, and a
red-team watchlist verdict create explicit penalties. Source-supported fatal risks, deterministic
hard-kill criteria, or a score below the kill threshold can kill an opportunity. Unsupported AI
kill opinions can only force watchlist review.

The final disposition is deterministic:

- `advance` promotes the opportunity from `RESEARCHING` to `THESIS_READY`.
- `watchlist` preserves the complete thesis and reason for later re-evaluation.
- `kill` records the exact hard kills and moves the opportunity to `KILLED`.

```text
POST /decisions/campaigns/{campaign_id}/score
POST /decisions/backfill
POST /decisions/{decision_id}/analyze
GET  /decisions
GET  /decisions/{decision_id}
GET  /decisions/metrics
```

## Decision control center

Step 8 replaces the foundation screen with a live operating surface at `http://localhost:3000`.
It reads the existing APIs rather than inventing a second dashboard data model.

The control center includes:

- A ranked evidence ledger covering scored and unscored opportunities
- Pipeline throughput from raw documents through completed decisions
- A selected-thesis aperture with confidence and five-lane research progress
- Full weighted score decomposition with per-dimension confidence
- Supporting and contradicting evidence, specialist findings, and source links
- Bottom-up market, economics, distribution, and competitor views
- Red-team risks, mitigations, kill criteria, and immutable lifecycle history
- Derived operational alerts for failures, hard kills, and access reviews
- Human controls to start research, run scoring, watchlist, or kill a thesis
- Explicit loading, empty, offline, and action-error states

Server rendering uses `API_INTERNAL_URL`; browser controls use `NEXT_PUBLIC_API_URL`. The Compose
configuration sets these to the internal API service and `http://localhost:8000` respectively.

The pre-Step-8 audit also hardened the underlying system: the custom Actor now supports bounded
Apify-native search discovery for all research lanes, Apify runs reconcile even when webhooks are unavailable,
and processing, intelligence, research, and decision model retries are cost-bounded.

## Real-world validation engine

Step 9 converts an `advance` decision into a controlled validation campaign. The system plans four
tests—pain interviews, cold outreach, pricing, and paid commitment—but deliberately leaves external
execution to the operator. Every test contains a causal hypothesis, one primary metric, guardrails,
a minimum sample, and a decision rule. Recording results recalculates the campaign without AI spend.

```text
POST  /validation/decisions/{decision_id}/campaigns
GET   /validation/campaigns
GET   /validation/campaigns/{campaign_id}
POST  /validation/experiments/{experiment_id}/results
PATCH /validation/experiments/{experiment_id}
POST  /validation/campaigns/{campaign_id}/evaluate
GET   /validation/metrics
```

Small samples remain `pending`; the engine does not stop early or promote vanity replies. A real
paid commitment produces a strong verdict and moves the opportunity to `pilot`. A sufficiently
large weak result moves it to `watchlist` and writes the exact miss into reusable failure memory.
Mixed evidence stays visible for further testing. Result keys are idempotent so repeated imports do
not double-count outcomes. The control center exposes the experiment ledger and manual outcome
recorders; it never sends outreach itself.

## Learning brain and research freshness

Step 10 closes the evidence-to-outcome loop without allowing the system to rewrite its own rules
silently. Immutable business outcome events connect decisions to demos, pricing acceptance, paid
pilots, activation, retention, churn, and observed revenue. Calibration compares those outcomes
with the original 14-dimension predictions only after the configured minimum sample is reached.
Every proposed weight change is bounded to two percentage points, normalized to 100%, and requires
explicit human approval before it becomes the scoring profile for future decisions.

```text
POST /learning/opportunities/{opportunity_id}/outcomes
GET  /learning/outcomes
POST /learning/calibration/runs
GET  /learning/calibration/runs
POST /learning/calibration/runs/{run_id}/review
POST /learning/freshness/backfill
GET  /learning/freshness
POST /learning/freshness/{assessment_id}/refresh
GET  /learning/metrics
```

The freshness monitor shortens review windows for high-scoring, pilot, and prototype opportunities.
Due opportunities receive a separately versioned refresh campaign across competitors, pricing,
regulation, launches, reviews, sentiment, APIs, and funding. A refresh never creates a new decision
automatically: detected changes are surfaced with a `requires_rescore` flag for operator review.
External collection runs only when the custom Apify Actor and an approved source are configured.

Outcome properties must contain operational metadata only—never contact names, email addresses, or
message bodies. The control center's Learning tab provides the outcome ledger, freshness queue,
calibration evidence, bounded weight deltas, and approval controls.

## Portfolio operations and build handoff

Step 11 completes the core OS. A scheduled portfolio monitor ranks completed decisions, retains the
previous score and rank, calculates pain, competition, market-timing, and score velocity, and assigns
one explicit state: `improving`, `stable`, `deteriorating`, `saturating`, or `invalidated`.

Only material events create deduplicated alerts: high scores, large score changes, top-ten entry,
competitor changes, strong or failed validation, and kills. The database outbox is canonical;
Telegram delivery is optional through `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

Customer interviews are stored as structured first-class evidence, including current behavior,
tools, time and financial cost, spend, urgency, budget signals, price reactions, objections, and
evidence strength. Repeated tools and complaints become portfolio-readable patterns.

A build handoff can be generated only from a completed strong validation campaign. It produces an
evidence-manifested product definition, strict MVP scope, user stories, workflow, technical and AI
architecture, data model, integrations, onboarding, pricing hypothesis, demo, positioning,
validation checklist, and 30/60/90-day plan. The draft requires human approval and can be downloaded
as Markdown.

```text
POST  /operations/portfolio/sync
GET   /operations/portfolio
GET   /operations/alerts
PATCH /operations/alerts/{alert_id}
POST  /operations/opportunities/{opportunity_id}/interviews
GET   /operations/opportunities/{opportunity_id}/interview-patterns
POST  /operations/opportunities/{opportunity_id}/build-spec
GET   /operations/build-specs/{spec_id}/markdown
POST  /operations/build-specs/{spec_id}/review
```
