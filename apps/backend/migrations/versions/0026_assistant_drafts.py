"""Assistant reply/polish drafts (ADR 0011, batch 3).

Additive table only. One draft per turn (unique ``turn_id``); validity is
computed on read from its bindings, so no existing row is touched.
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_assistant_drafts"
down_revision = "0025_assistant"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistant_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "turn_id",
            sa.String(36),
            sa.ForeignKey("assistant_turns.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("work_order_id", sa.String(36), sa.ForeignKey("work_orders.id"), nullable=True),
        sa.Column("base_work_order_version", sa.Integer(), nullable=True),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("unverified_claims", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scrubbed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assistant_drafts_account_id", "assistant_drafts", ["account_id"])
    op.create_index("ix_assistant_drafts_conversation_id", "assistant_drafts", ["conversation_id"])
    op.create_index("ix_assistant_drafts_created_at", "assistant_drafts", ["created_at"])


def downgrade():
    op.drop_index("ix_assistant_drafts_created_at", table_name="assistant_drafts")
    op.drop_index("ix_assistant_drafts_conversation_id", table_name="assistant_drafts")
    op.drop_index("ix_assistant_drafts_account_id", table_name="assistant_drafts")
    op.drop_table("assistant_drafts")
