"""Add evidence entities, graph edges, and corroborated clusters."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

entity_type = postgresql.ENUM(
    "industry",
    "subindustry",
    "company_type",
    "company_size",
    "company",
    "role",
    "trigger",
    "task",
    "pain_type",
    "tool",
    "software",
    "input",
    "output",
    "workflow_step",
    "workaround",
    "recurrence",
    "desired_outcome",
    name="entitytype",
    create_type=False,
)
cluster_type = postgresql.ENUM("pain", "workflow", "change", name="clustertype", create_type=False)
cluster_status = postgresql.ENUM(
    "active", "merged", "archived", name="clusterstatus", create_type=False
)
membership_method = postgresql.ENUM(
    "fingerprint", "semantic", "hybrid", name="membershipmethod", create_type=False
)
processing_status = postgresql.ENUM(
    "queued",
    "running",
    "awaiting_model",
    "succeeded",
    "failed",
    name="processingstatus",
    create_type=False,
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


def indexed(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    entity_type.create(op.get_bind(), checkfirst=True)
    cluster_type.create(op.get_bind(), checkfirst=True)
    cluster_status.create(op.get_bind(), checkfirst=True)
    membership_method.create(op.get_bind(), checkfirst=True)

    op.add_column("signals", sa.Column("intelligence_status", processing_status))
    op.add_column("signals", sa.Column("intelligence_processed_at", sa.DateTime(timezone=True)))
    op.add_column("signals", sa.Column("intelligence_error", sa.Text()))
    op.create_index("ix_signals_intelligence_status", "signals", ["intelligence_status"])
    op.create_index(
        "ix_signals_intelligence_processed_at", "signals", ["intelligence_processed_at"]
    )

    op.create_table(
        "knowledge_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", entity_type, nullable=False),
        sa.Column("display_value", sa.String(300), nullable=False),
        sa.Column("normalized_value", sa.String(240), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("entity_type", "normalized_value", name="uq_entity_type_value"),
    )
    indexed("knowledge_entities", ("entity_type", "normalized_value"))

    op.create_table(
        "signal_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=False
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_entities.id"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(80), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("evidence", sa.JSON(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("signal_id", "entity_id", "relation", name="uq_signal_entity_relation"),
    )
    indexed("signal_entities", ("signal_id", "entity_id", "relation"))

    op.create_table(
        "entity_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_entities.id"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_entities.id"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(80), nullable=False, server_default="co_occurs"),
        sa.Column("support_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("supporting_signal_ids", sa.JSON(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "source_entity_id", "target_entity_id", "relation", name="uq_entity_edge"
        ),
    )
    indexed(
        "entity_edges",
        ("source_entity_id", "target_entity_id", "relation", "support_count"),
    )

    op.create_table(
        "evidence_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cluster_type", cluster_type, nullable=False),
        sa.Column("cluster_key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", cluster_status, nullable=False, server_default="active"),
        sa.Column("centroid", Vector(1536)),
        sa.Column("centroid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_type_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("corroboration_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("recurrence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("velocity_30d", sa.Float(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("metrics", sa.JSON(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("cluster_type", "cluster_key", name="uq_cluster_type_key"),
    )
    indexed(
        "evidence_clusters",
        (
            "cluster_type",
            "cluster_key",
            "status",
            "signal_count",
            "source_count",
            "corroboration_score",
            "velocity_30d",
            "first_seen_at",
            "last_seen_at",
        ),
    )
    op.create_index(
        "ix_evidence_clusters_centroid_hnsw",
        "evidence_clusters",
        ["centroid"],
        postgresql_using="hnsw",
        postgresql_ops={"centroid": "vector_cosine_ops"},
    )

    op.create_table(
        "cluster_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_clusters.id"),
            nullable=False,
        ),
        sa.Column(
            "signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=False
        ),
        sa.Column("similarity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("method", membership_method, nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        *timestamps(),
        sa.UniqueConstraint("cluster_id", "signal_id", name="uq_cluster_signal"),
    )
    indexed("cluster_memberships", ("cluster_id", "signal_id", "method", "is_primary"))

    op.create_table(
        "cluster_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_clusters.id"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_entities.id"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(80), nullable=False, server_default="contains"),
        sa.Column("support_count", sa.Integer(), nullable=False, server_default="1"),
        *timestamps(),
        sa.UniqueConstraint("cluster_id", "entity_id", "relation", name="uq_cluster_entity"),
    )
    indexed("cluster_entities", ("cluster_id", "entity_id", "relation"))


def downgrade() -> None:
    op.drop_table("cluster_entities")
    op.drop_table("cluster_memberships")
    op.drop_index("ix_evidence_clusters_centroid_hnsw", table_name="evidence_clusters")
    op.drop_table("evidence_clusters")
    op.drop_table("entity_edges")
    op.drop_table("signal_entities")
    op.drop_table("knowledge_entities")
    op.drop_index("ix_signals_intelligence_processed_at", table_name="signals")
    op.drop_index("ix_signals_intelligence_status", table_name="signals")
    op.drop_column("signals", "intelligence_error")
    op.drop_column("signals", "intelligence_processed_at")
    op.drop_column("signals", "intelligence_status")
    membership_method.drop(op.get_bind(), checkfirst=True)
    cluster_status.drop(op.get_bind(), checkfirst=True)
    cluster_type.drop(op.get_bind(), checkfirst=True)
    entity_type.drop(op.get_bind(), checkfirst=True)
