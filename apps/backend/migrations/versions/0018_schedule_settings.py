"""Merchant working hours, breaks, durations and buffers (方案 §4.4)."""

import sqlalchemy as sa
from alembic import op

revision = "0018_schedule_settings"
down_revision = "0017_job_assignments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "schedule_settings",
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("schedule_settings")
