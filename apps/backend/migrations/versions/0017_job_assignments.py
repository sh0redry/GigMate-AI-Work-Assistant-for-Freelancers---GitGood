"""Merchant assignment of an unassigned message to a work order (方案 §4.2, 契约 §1)."""

import sqlalchemy as sa
from alembic import op

revision = "0017_job_assignments"
down_revision = "0016_d03_sending_heads"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_assignments",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("work_order_id", sa.String(36), sa.ForeignKey("work_orders.id"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("job_assignments")
