"""Bounded merchant assistant threads and durable turns (ADR 0011, batch 1).

Additive tables only: no existing row is touched. ``(account_id, request_key)``
makes a retried browser request return the original turn instead of asking twice.
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_assistant"
down_revision = "0024_context_clarification"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistant_threads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assistant_threads_account_id", "assistant_threads", ["account_id"])
    op.create_table(
        "assistant_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "thread_id", sa.String(36), sa.ForeignKey("assistant_threads.id"), nullable=False
        ),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("intent", sa.String(16), nullable=True),
        sa.Column("engine", sa.String(8), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=True),
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scrubbed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("account_id", "request_key", name="uq_assistant_turn_key"),
    )
    op.create_index("ix_assistant_turns_account_id", "assistant_turns", ["account_id"])
    op.create_index("ix_assistant_turns_thread_id", "assistant_turns", ["thread_id"])
    op.create_index("ix_assistant_turns_state", "assistant_turns", ["state"])
    op.create_index("ix_assistant_turns_created_at", "assistant_turns", ["created_at"])


def downgrade():
    op.drop_index("ix_assistant_turns_created_at", table_name="assistant_turns")
    op.drop_index("ix_assistant_turns_state", table_name="assistant_turns")
    op.drop_index("ix_assistant_turns_thread_id", table_name="assistant_turns")
    op.drop_index("ix_assistant_turns_account_id", table_name="assistant_turns")
    op.drop_table("assistant_turns")
    op.drop_index("ix_assistant_threads_account_id", table_name="assistant_threads")
    op.drop_table("assistant_threads")
