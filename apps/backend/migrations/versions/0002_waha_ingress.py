"""Persist trusted connector mappings and scoped reception/state."""

import sqlalchemy as sa
from alembic import op

revision = "0002_waha_ingress"
down_revision = "0001_replay_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "waha_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("instance_id", sa.String(128), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("state_timestamp", sa.BigInteger),
        sa.Column("state_received_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("accepted", sa.Integer, nullable=False),
        sa.Column("duplicates", sa.Integer, nullable=False),
        sa.Column("stale_events", sa.Integer, nullable=False),
        sa.UniqueConstraint("instance_id", "session_id", name="uq_waha_session"),
    )
    op.create_index("ix_waha_connections_account_id", "waha_connections", ["account_id"])
    op.create_table(
        "waha_chats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), nullable=False
        ),
        sa.Column("provider_chat_id", sa.String(256), nullable=False),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.UniqueConstraint("connection_id", "provider_chat_id", name="uq_waha_chat"),
        sa.UniqueConstraint("conversation_id"),
    )
    op.create_index("ix_waha_chats_connection_id", "waha_chats", ["connection_id"])
    op.create_table(
        "waha_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("waha_chats.id"), nullable=False),
        sa.Column("provider_message_id", sa.String(256), nullable=False),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("occurred_timestamp", sa.BigInteger, nullable=False),
        sa.Column("delivery_rank", sa.Integer, nullable=False),
        sa.UniqueConstraint("chat_id", "provider_message_id", name="uq_waha_message"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index("ix_waha_messages_chat_id", "waha_messages", ["chat_id"])
    with op.batch_alter_table("inbox") as batch:
        batch.add_column(sa.Column("connection_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_inbox_waha_connection", "waha_connections", ["connection_id"], ["id"]
        )
        batch.create_index("ix_inbox_connection_id", ["connection_id"])


def downgrade():
    with op.batch_alter_table("inbox") as batch:
        batch.drop_index("ix_inbox_connection_id")
        batch.drop_constraint("fk_inbox_waha_connection", type_="foreignkey")
        batch.drop_column("connection_id")
    op.drop_table("waha_messages")
    op.drop_table("waha_chats")
    op.drop_table("waha_connections")
