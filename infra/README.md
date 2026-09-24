# Infrastructure

Local development uses Docker Compose. The production target remains cloud-neutral at the application boundary:

- Web, API, and workers are Docker images.
- PostgreSQL with pgvector is the system of record.
- Redis provides local job queues and caching.
- Raw object storage will use an S3-compatible interface.

AWS definitions will be added after the local end-to-end pipeline is operational.
