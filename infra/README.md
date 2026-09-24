# Infrastructure

Local development uses Docker Compose. The production target remains cloud-neutral at the application boundary:

- Web and API are deployable services; scheduled research runs as bounded GitHub Actions jobs.
- PostgreSQL with pgvector is the system of record.
- PostgreSQL provides the durable job queue, removing the need for an always-on Redis worker.
- Raw object storage can use Cloudflare R2's S3-compatible interface when needed.

## Free-cloud targets

- Vercel serves the Next.js control center using the root `vercel.json`.
- Render serves FastAPI using the root `render.yaml`; sleeping between requests is expected.
- Neon provides PostgreSQL and pgvector through `DATABASE_URL`.
- GitHub Actions runs the bounded research cycle every six hours.
- Apify schedules and executes collection actors independently of the local computer.
