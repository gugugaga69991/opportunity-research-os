"""Add autonomous specialist research campaigns and findings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

research_status = postgresql.ENUM(
    "planned",
    "awaiting_configuration",
    "queued",
    "running",
    "collecting",
    "awaiting_analysis",
    "analyzing",
    "completed",
    "failed",
    "blocked",
    name="researchstatus",
    create_type=False,
)
research_lane = postgresql.ENUM(
    "competition",
    "economics",
    "market",
    "distribution",
    "contradiction",
    name="researchlane",
    create_type=False,
)
finding_stance = postgresql.ENUM(
    "supporting", "contradicting", "neutral", name="findingstance", create_type=False
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
    research_status.create(op.get_bind(), checkfirst=True)
    research_lane.create(op.get_bind(), checkfirst=True)
    finding_stance.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "research_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
        ),
        sa.Column("version", sa.String(40), nullable=False, server_default="1.0.0"),
        sa.Column("status", research_status, nullable=False, server_default="planned"),
        sa.Column("required_lane_count", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("completed_lane_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_lane_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        *timestamps(),
        sa.UniqueConstraint("opportunity_id", "version", name="uq_research_campaign_version"),
    )
    indexed(
        "research_campaigns",
        ("opportunity_id", "status", "completed_lane_count", "coverage_score"),
    )

    op.create_table(
        "research_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_campaigns.id"),
            nullable=False,
        ),
        sa.Column("lane", research_lane, nullable=False),
        sa.Column("status", research_status, nullable=False, server_default="planned"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("research_queries", sa.JSON(), nullable=False),
        sa.Column("actor_input", sa.JSON(), nullable=False),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_runs.id"),
        ),
        sa.Column("model_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("model_runs.id")),
        sa.Column("documents_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        *timestamps(),
        sa.UniqueConstraint("campaign_id", "lane", name="uq_research_campaign_lane"),
    )
    indexed(
        "research_tasks",
        (
            "campaign_id",
            "lane",
            "status",
            "required",
            "collection_run_id",
            "model_run_id",
        ),
    )

    op.create_table(
        "research_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_tasks.id"),
            nullable=False,
        ),
        sa.Column("target_key", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(80), nullable=False, server_default="search_query"),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", research_status, nullable=False, server_default="planned"),
        *timestamps(),
        sa.UniqueConstraint("task_id", "target_key", name="uq_research_task_target"),
    )
    indexed("research_targets", ("task_id", "target_key", "target_type", "status"))

    op.create_table(
        "research_findings",
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
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_tasks.id"),
            nullable=False,
        ),
        sa.Column("lane", research_lane, nullable=False),
        sa.Column("finding_key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("stance", finding_stance, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("structured_data", sa.JSON(), nullable=False),
        sa.Column("evidence_urls", sa.JSON(), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("task_id", "finding_key", name="uq_research_task_finding"),
    )
    indexed(
        "research_findings",
        (
            "opportunity_id",
            "campaign_id",
            "task_id",
            "lane",
            "finding_key",
            "stance",
            "confidence",
            "active",
            "last_seen_at",
        ),
    )

    op.create_table(
        "competitor_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity_hypotheses.id"),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_findings.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("normalized_name", sa.String(240), nullable=False),
        sa.Column("website", sa.Text(), nullable=False, server_default=""),
        sa.Column("positioning", sa.Text(), nullable=False, server_default=""),
        sa.Column("icp", sa.Text(), nullable=False, server_default=""),
        sa.Column("pricing", sa.Text(), nullable=False, server_default=""),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("weaknesses", sa.JSON(), nullable=False),
        sa.Column("evidence_urls", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.UniqueConstraint(
            "opportunity_id", "normalized_name", name="uq_opportunity_competitor_name"
        ),
    )
    indexed(
        "competitor_profiles",
        ("opportunity_id", "finding_id", "name", "normalized_name", "active"),
    )


def downgrade() -> None:
    op.drop_table("competitor_profiles")
    op.drop_table("research_findings")
    op.drop_table("research_targets")
    op.drop_table("research_tasks")
    op.drop_table("research_campaigns")
    finding_stance.drop(op.get_bind(), checkfirst=True)
    research_lane.drop(op.get_bind(), checkfirst=True)
    research_status.drop(op.get_bind(), checkfirst=True)
