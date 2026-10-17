"""Persist model submission fences and explicit new-order suggestion decisions."""

import sqlalchemy as sa
from alembic import op

revision = "0021_reviewed_product"
down_revision = "0020_business_model_heads"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("model_request_id", sa.String(64), nullable=True))
    op.create_table(
        "proposal_decisions",
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("inbox.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("proposals.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            sa.String(36),
            sa.ForeignKey("work_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_proposal_decisions_account_id", "proposal_decisions", ["account_id"])


def downgrade():
    op.drop_table("proposal_decisions")
    op.drop_column("jobs", "model_request_id")
