"""Make job runs a PostgreSQL-backed durable queue."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_runs",
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column("job_runs", sa.Column("locked_at", sa.DateTime(timezone=True)))
    op.add_column("job_runs", sa.Column("locked_by", sa.String(160)))
    op.add_column(
        "job_runs", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "job_runs", sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False)
    )
    op.add_column("job_runs", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_job_runs_available_at", "job_runs", ["available_at"])
    op.create_index(
        "ix_job_runs_status_available_at",
        "job_runs",
        ["status", "available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_runs_status_available_at", table_name="job_runs")
    op.drop_index("ix_job_runs_available_at", table_name="job_runs")
    op.drop_column("job_runs", "completed_at")
    op.drop_column("job_runs", "max_attempts")
    op.drop_column("job_runs", "attempts")
    op.drop_column("job_runs", "locked_by")
    op.drop_column("job_runs", "locked_at")
    op.drop_column("job_runs", "available_at")
