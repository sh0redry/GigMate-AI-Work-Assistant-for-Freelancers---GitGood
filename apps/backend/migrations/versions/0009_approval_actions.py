"""Approval actions: merchant-reviewed send_text drafts (role C, P0).

Adds ``approval_actions``. Earlier migrations are untouched. If another 0009
lands first, add a merge migration instead of renumbering this one.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_approval_actions"
down_revision = "0008_waha_message_sync"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "approval_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("work_order_id", sa.String(36), sa.ForeignKey("work_orders.id"), nullable=False),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("trigger", sa.String(128), nullable=False, unique=True),
        sa.Column("active_key", sa.String(36), unique=True),
        sa.Column("reason", sa.String(64)),
        sa.Column("note", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_approval_actions_account_id", "approval_actions", ["account_id"])
    op.create_index("ix_approval_actions_work_order_id", "approval_actions", ["work_order_id"])
    op.create_index("ix_approval_actions_conversation_id", "approval_actions", ["conversation_id"])


def downgrade():
    op.drop_table("approval_actions")
