"""Frozen initial schema; future changes require new migration revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0001_replay_foundation"
down_revision = None
branch_labels = None
depends_on = None


def identifier(name="id", primary=False, foreign=None):
    args = [sa.ForeignKey(foreign)] if foreign else []
    return sa.Column(name, sa.String(36), *args, primary_key=primary, nullable=False)


def account():
    return identifier("account_id", foreign="accounts.id")


def data():
    return sa.Column("data", sa.JSON, nullable=False)


def upgrade():
    op.create_table(
        "accounts",
        identifier(primary=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
    )
    op.create_table(
        "login_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        account(),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "conversations",
        identifier(primary=True),
        account(),
        sa.Column("context_version", sa.Integer, nullable=False),
        sa.Column("allowlisted", sa.Boolean, nullable=False),
    )
    op.create_table("work_orders", identifier(primary=True), account(), data())
    op.create_table(
        "conversation_orders",
        identifier("conversation_id", primary=True, foreign="conversations.id"),
        identifier("work_order_id", primary=True, foreign="work_orders.id"),
    )
    op.create_table(
        "inbox",
        identifier(primary=True),
        account(),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("context_version", sa.Integer, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "message_revisions",
        identifier(primary=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        account(),
        identifier("conversation_id", foreign="conversations.id"),
        sa.Column("provider_message_id", sa.String(256), nullable=False),
        data(),
        sa.UniqueConstraint(
            "account_id",
            "conversation_id",
            "provider_message_id",
            "revision",
            name="uq_message_identity",
        ),
    )
    op.create_table(
        "jobs",
        identifier(primary=True),
        identifier("event_id", foreign="inbox.id"),
        account(),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.String(36)),
        sa.Column("error_code", sa.String(64)),
        sa.UniqueConstraint("event_id"),
    )
    op.create_table(
        "requirement_changes",
        identifier(primary=True),
        account(),
        identifier("work_order_id", foreign="work_orders.id"),
        identifier("conversation_id", foreign="conversations.id"),
        sa.Column("context_version", sa.Integer, nullable=False),
        data(),
    )
    op.create_table(
        "calendar_events",
        identifier(primary=True),
        account(),
        identifier("work_order_id", foreign="work_orders.id"),
        data(),
        sa.UniqueConstraint("work_order_id"),
    )
    op.create_table(
        "tasks",
        identifier(primary=True),
        account(),
        identifier("work_order_id", foreign="work_orders.id"),
        sa.Column("generated", sa.Boolean, nullable=False),
        data(),
    )
    op.create_table("audit_logs", identifier(primary=True), account(), data())
    op.create_table(
        "command_results",
        identifier(primary=True),
        account(),
        sa.Column("scope", sa.String(256), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        data(),
        sa.UniqueConstraint("account_id", "scope", "key", name="uq_command_key"),
    )
    for table in [
        "conversations",
        "work_orders",
        "inbox",
        "message_revisions",
        "requirement_changes",
        "calendar_events",
        "tasks",
        "audit_logs",
    ]:
        op.create_index(f"ix_{table}_account_id", table, ["account_id"])


def downgrade():
    for table in [
        "command_results",
        "audit_logs",
        "tasks",
        "calendar_events",
        "requirement_changes",
        "jobs",
        "message_revisions",
        "inbox",
        "conversation_orders",
        "work_orders",
        "conversations",
        "login_sessions",
        "accounts",
    ]:
        op.drop_table(table)
