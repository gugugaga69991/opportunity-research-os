"""Add portfolio monitoring, interview memory, alerts, and build handoffs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    portfolio_state = postgresql.ENUM(
        "improving",
        "stable",
        "deteriorating",
        "saturating",
        "invalidated",
        name="portfoliostate",
        create_type=False,
    )
    alert_status = postgresql.ENUM(
        "unread", "read", "archived", name="alertstatus", create_type=False
    )
    build_status = postgresql.ENUM(
        "draft", "approved", name="buildspecstatus", create_type=False
    )
    portfolio_state.create(op.get_bind(), checkfirst=True)
    alert_status.create(op.get_bind(), checkfirst=True)
    build_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("current_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("previous_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("score_velocity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("competition_velocity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pain_velocity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("market_timing_velocity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rank", sa.Integer()),
        sa.Column("previous_rank", sa.Integer()),
        sa.Column("state", portfolio_state, nullable=False, server_default="stable"),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
    )
    indexed(
        "portfolio_snapshots",
        ("opportunity_id", "current_score", "score_velocity", "rank", "state", "assessed_at"),
    )

    op.create_table(
        "operational_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
        ),
        sa.Column("alert_key", sa.String(200), nullable=False, unique=True),
        sa.Column("alert_type", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(40), nullable=False),
        sa.Column("status", alert_status, nullable=False, server_default="unread"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("telegram_delivered_at", sa.DateTime(timezone=True)),
        sa.Column("delivery_error", sa.Text()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    indexed(
        "operational_alerts", ("opportunity_id", "alert_key", "alert_type", "severity", "status")
    )

    op.create_table(
        "customer_interviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
        ),
        sa.Column("interview_key", sa.String(160), nullable=False),
        sa.Column("company", sa.String(240), nullable=False, server_default=""),
        sa.Column("industry", sa.String(160), nullable=False, server_default=""),
        sa.Column("company_size", sa.String(120), nullable=False, server_default=""),
        sa.Column("participant_role", sa.String(160), nullable=False, server_default=""),
        sa.Column("buyer_or_user", sa.String(40), nullable=False, server_default="user"),
        sa.Column("interviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("current_workflow", sa.Text(), nullable=False, server_default=""),
        sa.Column("tools_used", sa.JSON(), nullable=False),
        sa.Column("pain_frequency", sa.String(120), nullable=False, server_default=""),
        sa.Column("time_cost_hours", sa.Float()),
        sa.Column("financial_cost_usd", sa.Float()),
        sa.Column("current_spend_usd", sa.Float()),
        sa.Column("complaints", sa.JSON(), nullable=False),
        sa.Column("desired_outcome", sa.Text(), nullable=False, server_default=""),
        sa.Column("urgency", sa.String(80), nullable=False, server_default=""),
        sa.Column("budget_signal", sa.String(120), nullable=False, server_default=""),
        sa.Column("price_reaction", sa.String(120), nullable=False, server_default=""),
        sa.Column("objections", sa.JSON(), nullable=False),
        sa.Column("quotes", sa.JSON(), nullable=False),
        sa.Column("follow_up", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_strength", sa.Float(), nullable=False, server_default="0"),
        *timestamps(),
        sa.UniqueConstraint("opportunity_id", "interview_key", name="uq_opportunity_interview"),
    )
    indexed(
        "customer_interviews",
        (
            "opportunity_id",
            "interview_key",
            "industry",
            "participant_role",
            "interviewed_at",
            "evidence_strength",
        ),
    )

    op.create_table(
        "build_specifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
        ),
        sa.Column(
            "decision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_decisions.id"),
            nullable=False,
        ),
        sa.Column(
            "validation_campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("validation_campaigns.id"),
            nullable=False,
        ),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("status", build_status, nullable=False, server_default="draft"),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("source_manifest", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.String(120)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("opportunity_id", "version", name="uq_opportunity_build_spec"),
    )
    indexed(
        "build_specifications",
        ("opportunity_id", "decision_id", "validation_campaign_id", "status"),
    )


def downgrade() -> None:
    op.drop_table("build_specifications")
    op.drop_table("customer_interviews")
    op.drop_table("operational_alerts")
    op.drop_table("portfolio_snapshots")
    postgresql.ENUM(name="buildspecstatus").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="alertstatus").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="portfoliostate").drop(op.get_bind(), checkfirst=True)
