"""Add auditable opportunity scoring and red-team decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

decision_status = postgresql.ENUM(
    "awaiting_analysis",
    "analyzing",
    "completed",
    "failed",
    name="decisionstatus",
    create_type=False,
)
decision_disposition = postgresql.ENUM(
    "advance",
    "watchlist",
    "kill",
    name="decisiondisposition",
    create_type=False,
)
risk_severity = postgresql.ENUM(
    "low",
    "medium",
    "high",
    "fatal",
    name="riskseverity",
    create_type=False,
)
score_dimension = postgresql.ENUM(
    "pain_severity",
    "recurring_frequency",
    "existing_spend",
    "willingness_to_pay",
    "competition_weakness",
    "distribution_quality",
    "retention",
    "buildability",
    "time_to_value",
    "ai_advantage",
    "defensibility",
    "market_timing",
    "reachable_tam",
    "expansion",
    name="scoredimension",
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
    decision_status.create(op.get_bind(), checkfirst=True)
    decision_disposition.create(op.get_bind(), checkfirst=True)
    risk_severity.create(op.get_bind(), checkfirst=True)
    score_dimension.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "opportunity_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_campaigns.id"),
            nullable=False,
        ),
        sa.Column("model_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("model_runs.id")),
        sa.Column("version", sa.String(40), nullable=False, server_default="1.0.0"),
        sa.Column("status", decision_status, nullable=False, server_default="awaiting_analysis"),
        sa.Column("disposition", decision_disposition),
        sa.Column("raw_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("adjusted_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("research_coverage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("hard_kill_triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("penalties", sa.JSON(), nullable=False),
        sa.Column("hard_kills", sa.JSON(), nullable=False),
        sa.Column("thesis", sa.JSON(), nullable=False),
        sa.Column("red_team", sa.JSON(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        *timestamps(),
        sa.UniqueConstraint("campaign_id", "version", name="uq_campaign_decision_version"),
    )
    indexed(
        "opportunity_decisions",
        (
            "opportunity_id",
            "campaign_id",
            "model_run_id",
            "status",
            "disposition",
            "raw_score",
            "confidence_score",
            "adjusted_score",
            "hard_kill_triggered",
        ),
    )

    op.create_table(
        "opportunity_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "decision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_decisions.id"),
            nullable=False,
        ),
        sa.Column("dimension", score_dimension, nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("weighted_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_urls", sa.JSON(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("decision_id", "dimension", name="uq_decision_score_dimension"),
    )
    indexed("opportunity_scores", ("decision_id", "dimension"))

    op.create_table(
        "opportunity_risks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "decision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_decisions.id"),
            nullable=False,
        ),
        sa.Column("risk_key", sa.String(64), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("severity", risk_severity, nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("implication", sa.Text(), nullable=False, server_default=""),
        sa.Column("mitigation", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_urls", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("decision_id", "risk_key", name="uq_decision_risk"),
    )
    indexed(
        "opportunity_risks",
        ("decision_id", "risk_key", "category", "severity", "active"),
    )


def downgrade() -> None:
    op.drop_table("opportunity_risks")
    op.drop_table("opportunity_scores")
    op.drop_table("opportunity_decisions")
    score_dimension.drop(op.get_bind(), checkfirst=True)
    risk_severity.drop(op.get_bind(), checkfirst=True)
    decision_disposition.drop(op.get_bind(), checkfirst=True)
    decision_status.drop(op.get_bind(), checkfirst=True)
