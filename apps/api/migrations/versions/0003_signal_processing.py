"""Add the signal normalization, deduplication, and extraction layer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

processing_status = postgresql.ENUM(
    "queued",
    "running",
    "awaiting_model",
    "succeeded",
    "failed",
    name="processingstatus",
    create_type=False,
)
duplicate_kind = postgresql.ENUM(
    "exact", "near", "semantic", name="duplicatekind", create_type=False
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
    processing_status.create(op.get_bind(), checkfirst=True)
    duplicate_kind.create(op.get_bind(), checkfirst=True)

    op.add_column("model_runs", sa.Column("actual_model", sa.String(160)))
    op.add_column("model_runs", sa.Column("cost_usd", sa.Float()))
    op.add_column("model_runs", sa.Column("duration_ms", sa.Integer()))

    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "raw_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_documents.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "canonical_signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.id"),
        ),
        sa.Column("status", processing_status, nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False, server_default=""),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="und"),
        sa.Column("exact_hash", sa.String(64), nullable=False),
        sa.Column("simhash", sa.String(16), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duplicate_kind", duplicate_kind),
        sa.Column("duplicate_score", sa.Float()),
        sa.Column("embedding", Vector(1536)),
        sa.Column("embedding_model", sa.String(160)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        *timestamps(),
    )
    for column in (
        "raw_document_id",
        "canonical_signal_id",
        "status",
        "language",
        "exact_hash",
        "simhash",
        "is_duplicate",
        "processed_at",
    ):
        op.create_index(f"ix_signals_{column}", "signals", [column])
    op.create_index(
        "ix_signals_embedding_hnsw",
        "signals",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "signal_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "model_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_runs.id"),
            nullable=False,
        ),
        sa.Column("is_pain", sa.Boolean(), nullable=False),
        sa.Column("pain_probability", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("industry", sa.String(160), nullable=False, server_default=""),
        sa.Column("user_role", sa.String(160), nullable=False, server_default=""),
        sa.Column("buyer_role", sa.String(160), nullable=False, server_default=""),
        sa.Column("recurrence", sa.String(80), nullable=False, server_default=""),
        sa.Column("urgency", sa.String(80), nullable=False, server_default=""),
        sa.Column("ontology", sa.JSON(), nullable=False),
        sa.Column("evidence_spans", sa.JSON(), nullable=False),
        *timestamps(),
    )
    for column in (
        "signal_id",
        "model_run_id",
        "is_pain",
        "pain_probability",
        "confidence",
        "industry",
        "user_role",
        "recurrence",
        "urgency",
    ):
        op.create_index(f"ix_signal_extractions_{column}", "signal_extractions", [column])


def downgrade() -> None:
    op.drop_table("signal_extractions")
    op.drop_index("ix_signals_embedding_hnsw", table_name="signals")
    op.drop_table("signals")
    op.drop_column("model_runs", "duration_ms")
    op.drop_column("model_runs", "cost_usd")
    op.drop_column("model_runs", "actual_model")
    duplicate_kind.drop(op.get_bind(), checkfirst=True)
    processing_status.drop(op.get_bind(), checkfirst=True)
