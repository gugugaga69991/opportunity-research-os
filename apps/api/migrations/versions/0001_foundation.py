"""Create foundation tables and pgvector extension."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
run_status = postgresql.ENUM(
    "queued", "running", "succeeded", "failed", name="runstatus", create_type=False
)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    run_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("access_method", sa.String(80), nullable=False),
        sa.Column("access_metadata", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_sources_source_type", "sources", ["source_type"])
    op.create_table(
        "collection_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False
        ),
        sa.Column("external_run_id", sa.String(200)),
        sa.Column("status", run_status, nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        *timestamps(),
    )
    op.create_index("ix_collection_runs_source_id", "collection_runs", ["source_id"])
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("name", "version", name="uq_prompt_name_version"),
    )
    op.create_table(
        "model_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prompt_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id")
        ),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("error", sa.Text()),
        *timestamps(),
    )
    op.create_index("ix_model_runs_input_hash", "model_runs", ["input_hash"])
    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(120), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("error", sa.Text()),
        *timestamps(),
    )
    op.create_index("ix_job_runs_job_type", "job_runs", ["job_type"])


def downgrade() -> None:
    op.drop_table("job_runs")
    op.drop_table("model_runs")
    op.drop_table("prompt_versions")
    op.drop_table("collection_runs")
    op.drop_table("sources")
    run_status.drop(op.get_bind(), checkfirst=True)
