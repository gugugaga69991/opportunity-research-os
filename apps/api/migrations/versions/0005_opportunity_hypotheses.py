"""Add evidence-gated opportunity hypotheses and lifecycle history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

hypothesis_track = postgresql.ENUM(
    "pain_led", "change_led", name="hypothesistrack", create_type=False
)
opportunity_status = postgresql.ENUM(
    "raw",
    "clustered",
    "screened",
    "researching",
    "thesis_ready",
    "validating",
    "pilot",
    "prototype",
    "build",
    "killed",
    "watchlist",
    name="opportunitystatus",
    create_type=False,
)
hypothesis_readiness = postgresql.ENUM(
    "preliminary",
    "corroborating",
    "research_ready",
    name="hypothesisreadiness",
    create_type=False,
)
evidence_stance = postgresql.ENUM(
    "supporting", "contradicting", "context", name="evidencestance", create_type=False
)
cluster_link_role = postgresql.ENUM(
    "origin",
    "supporting",
    "context",
    "contradicting",
    name="clusterlinkrole",
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
    hypothesis_track.create(op.get_bind(), checkfirst=True)
    opportunity_status.create(op.get_bind(), checkfirst=True)
    hypothesis_readiness.create(op.get_bind(), checkfirst=True)
    evidence_stance.create(op.get_bind(), checkfirst=True)
    cluster_link_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "opportunity_hypotheses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("hypothesis_key", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "origin_cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_clusters.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("track", hypothesis_track, nullable=False),
        sa.Column("status", opportunity_status, nullable=False, server_default="clustered"),
        sa.Column("readiness", hypothesis_readiness, nullable=False, server_default="preliminary"),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("industry", sa.String(160), nullable=False, server_default=""),
        sa.Column("icp", sa.Text(), nullable=False, server_default=""),
        sa.Column("user_role", sa.String(160), nullable=False, server_default=""),
        sa.Column("buyer_role", sa.String(160), nullable=False, server_default=""),
        sa.Column("core_workflow", sa.Text(), nullable=False, server_default=""),
        sa.Column("problem", sa.Text(), nullable=False, server_default=""),
        sa.Column("frequency", sa.String(160), nullable=False, server_default=""),
        sa.Column("current_workaround", sa.Text(), nullable=False, server_default=""),
        sa.Column("economic_cost", sa.Text(), nullable=False, server_default=""),
        sa.Column("existing_spend", sa.Text(), nullable=False, server_default=""),
        sa.Column("why_now", sa.Text(), nullable=False, server_default=""),
        sa.Column("desired_outcome", sa.Text(), nullable=False, server_default=""),
        sa.Column("solution_concept", sa.Text(), nullable=False, server_default=""),
        sa.Column("value_proposition", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confirming_signal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirming_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_type_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contradiction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buyer_identified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recurring_problem", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_gate_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("thesis", sa.JSON(), nullable=False),
        sa.Column("genealogy", sa.JSON(), nullable=False),
        sa.Column("generation_version", sa.String(40), nullable=False, server_default="1.0.0"),
        sa.Column("last_cluster_update_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    indexed(
        "opportunity_hypotheses",
        (
            "hypothesis_key",
            "origin_cluster_id",
            "track",
            "status",
            "readiness",
            "name",
            "industry",
            "user_role",
            "buyer_role",
            "confidence",
            "buyer_identified",
            "recurring_problem",
            "evidence_gate_passed",
            "last_cluster_update_at",
        ),
    )

    op.create_table(
        "opportunity_cluster_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
        ),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_clusters.id"),
            nullable=False,
        ),
        sa.Column("role", cluster_link_role, nullable=False),
        sa.Column("shared_entity_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("opportunity_id", "cluster_id", "role", name="uq_opportunity_cluster"),
    )
    indexed(
        "opportunity_cluster_links",
        ("opportunity_id", "cluster_id", "role", "active", "last_seen_at"),
    )

    op.create_table(
        "opportunity_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
        ),
        sa.Column(
            "signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=False
        ),
        sa.Column(
            "cluster_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_clusters.id")
        ),
        sa.Column("stance", evidence_stance, nullable=False),
        sa.Column("evidence_type", sa.String(120), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "opportunity_id", "signal_id", "stance", name="uq_opportunity_signal_stance"
        ),
    )
    indexed(
        "opportunity_evidence",
        (
            "opportunity_id",
            "signal_id",
            "cluster_id",
            "stance",
            "evidence_type",
            "active",
            "last_seen_at",
        ),
    )

    op.create_table(
        "opportunity_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
        ),
        sa.Column("from_status", opportunity_status),
        sa.Column("to_status", opportunity_status, nullable=False),
        sa.Column("actor", sa.String(80), nullable=False, server_default="system"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        *timestamps(),
    )
    indexed("opportunity_transitions", ("opportunity_id", "to_status"))


def downgrade() -> None:
    op.drop_table("opportunity_transitions")
    op.drop_table("opportunity_evidence")
    op.drop_table("opportunity_cluster_links")
    op.drop_table("opportunity_hypotheses")
    cluster_link_role.drop(op.get_bind(), checkfirst=True)
    evidence_stance.drop(op.get_bind(), checkfirst=True)
    hypothesis_readiness.drop(op.get_bind(), checkfirst=True)
    opportunity_status.drop(op.get_bind(), checkfirst=True)
    hypothesis_track.drop(op.get_bind(), checkfirst=True)
