"""Add business outcomes, calibration profiles, and freshness monitoring."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

outcome_type = postgresql.ENUM(
    "outreach_positive",
    "demo_booked",
    "pricing_accepted",
    "loi_signed",
    "pilot_paid",
    "customer_activated",
    "customer_retained",
    "customer_churned",
    "mrr_observed",
    name="outcomeeventtype",
    create_type=False,
)
calibration_status = postgresql.ENUM(
    "insufficient_data",
    "pending_review",
    "approved",
    "rejected",
    name="calibrationstatus",
    create_type=False,
)
freshness_status = postgresql.ENUM(
    "current",
    "due",
    "refreshing",
    "changed",
    "failed",
    name="freshnessstatus",
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
    outcome_type.create(op.get_bind(), checkfirst=True)
    calibration_status.create(op.get_bind(), checkfirst=True)
    freshness_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "research_campaigns",
        sa.Column("campaign_type", sa.String(40), nullable=False, server_default="baseline"),
    )
    op.add_column(
        "research_campaigns",
        sa.Column(
            "supersedes_campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_campaigns.id"),
        ),
    )
    indexed("research_campaigns", ("campaign_type", "supersedes_campaign_id"))

    op.create_table(
        "business_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
        ),
        sa.Column(
            "decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("opportunity_decisions.id")
        ),
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column("event_type", outcome_type, nullable=False),
        sa.Column("source", sa.String(120), nullable=False, server_default="manual"),
        sa.Column("value_usd", sa.Float()),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("evidence_urls", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("opportunity_id", "event_key", name="uq_opportunity_outcome_event"),
    )
    indexed(
        "business_outcomes",
        ("opportunity_id", "decision_id", "event_key", "event_type", "source", "occurred_at"),
    )

    op.create_table(
        "calibration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("status", calibration_status, nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("baseline_weights", sa.JSON(), nullable=False),
        sa.Column("proposed_weights", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.String(120)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    indexed("calibration_runs", ("version", "status"))

    op.create_table(
        "scoring_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "calibration_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calibration_runs.id"),
        ),
        sa.Column("version", sa.String(40), nullable=False, unique=True),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approved_by", sa.String(120), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
    )
    indexed("scoring_profiles", ("calibration_run_id", "version", "active"))

    op.create_table(
        "freshness_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "active_campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_campaigns.id"),
        ),
        sa.Column("status", freshness_status, nullable=False, server_default="current"),
        sa.Column("freshness_score", sa.Float(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_researched_at", sa.DateTime(timezone=True)),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_topics", sa.JSON(), nullable=False),
        sa.Column("detected_changes", sa.JSON(), nullable=False),
        sa.Column("requires_rescore", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text()),
        *timestamps(),
    )
    indexed(
        "freshness_assessments",
        (
            "opportunity_id",
            "active_campaign_id",
            "status",
            "freshness_score",
            "priority",
            "next_check_at",
            "requires_rescore",
        ),
    )


def downgrade() -> None:
    op.drop_table("freshness_assessments")
    op.drop_table("scoring_profiles")
    op.drop_table("calibration_runs")
    op.drop_table("business_outcomes")
    op.drop_column("research_campaigns", "supersedes_campaign_id")
    op.drop_column("research_campaigns", "campaign_type")
    freshness_status.drop(op.get_bind(), checkfirst=True)
    calibration_status.drop(op.get_bind(), checkfirst=True)
    outcome_type.drop(op.get_bind(), checkfirst=True)
