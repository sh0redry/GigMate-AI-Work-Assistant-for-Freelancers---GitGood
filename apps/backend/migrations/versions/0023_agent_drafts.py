"""Bounded, expiring merchant-facing drafts (follow-up / polish).

Additive table only: no existing row is touched. The unique constraint on
``(account_id, proposal_id)`` makes reusing one model proposal idempotent, so a
draft can never be consumed twice or duplicated by a retried request.
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_agent_drafts"
down_revision = "0022_work_order_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("work_order_id", sa.String(36), sa.ForeignKey("work_orders.id"), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("base_work_order_version", sa.Integer(), nullable=True),
        sa.Column("proposal_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("note", sa.String(2000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "proposal_id", name="uq_agent_draft_proposal"),
    )
    op.create_index("ix_agent_drafts_account_id", "agent_drafts", ["account_id"])
    op.create_index("ix_agent_drafts_work_order_id", "agent_drafts", ["work_order_id"])
    op.create_index("ix_agent_drafts_proposal_id", "agent_drafts", ["proposal_id"])
    op.create_index("ix_agent_drafts_expires_at", "agent_drafts", ["expires_at"])


def downgrade():
    op.drop_index("ix_agent_drafts_expires_at", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_proposal_id", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_work_order_id", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_account_id", table_name="agent_drafts")
    op.drop_table("agent_drafts")
