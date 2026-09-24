"""Add validation campaigns, experiments, outcomes, and failure memory."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

validation_status = postgresql.ENUM(
    "planned", "running", "completed", "failed", name="validationstatus", create_type=False
)
validation_verdict = postgresql.ENUM(
    "pending",
    "strong",
    "mixed",
    "weak",
    "invalidated",
    name="validationverdict",
    create_type=False,
)
experiment_type = postgresql.ENUM(
    "pain_interview",
    "cold_email",
    "pricing",
    "paid_commitment",
    name="experimenttype",
    create_type=False,
)
experiment_status = postgresql.ENUM(
    "planned",
    "ready",
    "running",
    "completed",
    "cancelled",
    name="experimentstatus",
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
    validation_status.create(op.get_bind(), checkfirst=True)
    validation_verdict.create(op.get_bind(), checkfirst=True)
    experiment_type.create(op.get_bind(), checkfirst=True)
    experiment_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "validation_campaigns",
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
        sa.Column("version", sa.String(40), nullable=False, server_default="1.0.0"),
        sa.Column("status", validation_status, nullable=False, server_default="planned"),
        sa.Column("verdict", validation_verdict, nullable=False, server_default="pending"),
        sa.Column("validation_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("experiment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_experiment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("decision_id", "version", name="uq_decision_validation_version"),
    )
    indexed(
        "validation_campaigns",
        ("opportunity_id", "decision_id", "status", "verdict", "validation_score"),
    )

    op.create_table(
        "validation_experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("validation_campaigns.id"),
            nullable=False,
        ),
        sa.Column("experiment_type", experiment_type, nullable=False),
        sa.Column("status", experiment_status, nullable=False, server_default="planned"),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False, server_default=""),
        sa.Column("channel", sa.String(120), nullable=False, server_default="manual"),
        sa.Column("positioning_angle", sa.String(240), nullable=False, server_default=""),
        sa.Column("price_point_usd", sa.Float()),
        sa.Column("sample_target", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_criteria", sa.JSON(), nullable=False),
        sa.Column("execution_brief", sa.JSON(), nullable=False),
        sa.Column("aggregate", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("campaign_id", "experiment_type", name="uq_validation_experiment_type"),
    )
    indexed("validation_experiments", ("campaign_id", "experiment_type", "status", "channel"))

    op.create_table(
        "validation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "experiment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("validation_experiments.id"),
            nullable=False,
        ),
        sa.Column("result_key", sa.String(160), nullable=False),
        sa.Column("source", sa.String(120), nullable=False, server_default="manual"),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("qualitative_feedback", sa.JSON(), nullable=False),
        sa.Column("evidence_urls", sa.JSON(), nullable=False),
        sa.Column("interpretation", sa.Text(), nullable=False, server_default=""),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("experiment_id", "result_key", name="uq_experiment_result_key"),
    )
    indexed("validation_results", ("experiment_id", "result_key", "source", "observed_at"))

    op.create_table(
        "failure_memories",
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
            sa.ForeignKey("validation_campaigns.id"),
            nullable=False,
        ),
        sa.Column("reason_key", sa.String(64), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("predicted", sa.JSON(), nullable=False),
        sa.Column("actual", sa.JSON(), nullable=False),
        sa.Column("reusable_lesson", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint("campaign_id", "reason_key", name="uq_validation_failure_reason"),
    )
    indexed(
        "failure_memories", ("opportunity_id", "campaign_id", "reason_key", "category", "active")
    )


def downgrade() -> None:
    op.drop_table("failure_memories")
    op.drop_table("validation_results")
    op.drop_table("validation_experiments")
    op.drop_table("validation_campaigns")
    experiment_status.drop(op.get_bind(), checkfirst=True)
    experiment_type.drop(op.get_bind(), checkfirst=True)
    validation_verdict.drop(op.get_bind(), checkfirst=True)
    validation_status.drop(op.get_bind(), checkfirst=True)
