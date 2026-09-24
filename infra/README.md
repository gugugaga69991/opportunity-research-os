# Infrastructure

Local development uses Docker Compose. The production target remains cloud-neutral at the application boundary:

- Web and API are deployable services; scheduled research runs as bounded GitHub Actions jobs.
- PostgreSQL with pgvector is the system of record.
- PostgreSQL provides the durable job queue, removing the need for an always-on Redis worker.
- Raw object storage will use an S3-compatible interface.

AWS definitions will be added after the local end-to-end pipeline is operational.
