"""Add the source collection and raw evidence layer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

access_risk = postgresql.ENUM(
    "approved", "review_required", "restricted", name="accessrisk", create_type=False
)
trigger_type = postgresql.ENUM(
    "manual", "schedule", "webhook", name="triggertype", create_type=False
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
    access_risk.create(op.get_bind(), checkfirst=True)
    trigger_type.create(op.get_bind(), checkfirst=True)

    op.add_column("sources", sa.Column("slug", sa.String(160)))
    op.add_column("sources", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "sources",
        sa.Column("adapter_key", sa.String(80), nullable=False, server_default="generic_apify"),
    )
    op.add_column("sources", sa.Column("actor_id", sa.String(200)))
    op.add_column(
        "sources", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column(
        "sources",
        sa.Column("reliability_weight", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column(
        "sources",
        sa.Column("access_risk", access_risk, nullable=False, server_default="review_required"),
    )
    op.add_column(
        "sources",
        sa.Column(
            "collector_config",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.execute("UPDATE sources SET slug = lower(replace(name, ' ', '-')) WHERE slug IS NULL")
    op.alter_column("sources", "slug", nullable=False)
    op.create_index("ix_sources_slug", "sources", ["slug"], unique=True)
    op.create_index("ix_sources_enabled", "sources", ["enabled"])
    op.create_index("ix_sources_access_risk", "sources", ["access_risk"])

    op.add_column("collection_runs", sa.Column("external_dataset_id", sa.String(200)))
    op.add_column(
        "collection_runs",
        sa.Column("trigger_type", trigger_type, nullable=False, server_default="manual"),
    )
    op.add_column(
        "collection_runs",
        sa.Column("actor_input", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.add_column("collection_runs", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("collection_runs", sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.add_column(
        "collection_runs",
        sa.Column("items_received", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "collection_runs",
        sa.Column("items_ingested", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "collection_runs",
        sa.Column("items_skipped", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("collection_runs", sa.Column("cost_usd", sa.Float()))

    op.create_table(
        "raw_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False
        ),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_runs.id"),
            nullable=False,
        ),
        sa.Column("source_external_id", sa.String(240)),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("author", sa.String(240)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("language", sa.String(16)),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_raw_document_source_hash"),
    )
    for column in (
        "source_id",
        "collection_run_id",
        "source_external_id",
        "document_type",
        "published_at",
        "collected_at",
        "content_hash",
    ):
        op.create_index(f"ix_raw_documents_{column}", "raw_documents", [column])

    op.create_table(
        "collection_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("cron_expression", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="UTC"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("input_overrides", sa.JSON(), nullable=False),
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_collection_schedules_source_id", "collection_schedules", ["source_id"])
    op.create_index("ix_collection_schedules_enabled", "collection_schedules", ["enabled"])
    op.create_index("ix_collection_schedules_next_run_at", "collection_schedules", ["next_run_at"])

    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("event_key", sa.String(240), nullable=False, unique=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        *timestamps(),
    )
    op.create_index("ix_webhook_events_provider", "webhook_events", ["provider"])
    op.create_index("ix_webhook_events_event_type", "webhook_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("collection_schedules")
    op.drop_table("raw_documents")
    for column in (
        "cost_usd",
        "items_skipped",
        "items_ingested",
        "items_received",
        "finished_at",
        "started_at",
        "actor_input",
        "trigger_type",
        "external_dataset_id",
    ):
        op.drop_column("collection_runs", column)
    for column in (
        "collector_config",
        "access_risk",
        "reliability_weight",
        "enabled",
        "actor_id",
        "adapter_key",
        "description",
        "slug",
    ):
        op.drop_column("sources", column)
    trigger_type.drop(op.get_bind(), checkfirst=True)
    access_risk.drop(op.get_bind(), checkfirst=True)
