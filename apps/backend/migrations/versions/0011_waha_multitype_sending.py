"""Separate send consent, private uploads, exact policies and transactional outbox."""

import sqlalchemy as sa
from alembic import op

revision = "0011_waha_multitype_sending"
down_revision = "0010_waha_media_evidence"
branch_labels = None
depends_on = None


def fk(name, table, **kwargs):
    return sa.Column(name, sa.String(36), sa.ForeignKey(table + ".id"), **kwargs)


def upgrade():
    op.create_table(
        "waha_send_request_fences",
        fk("connection_id", "waha_connections", primary_key=True),
        sa.Column("request_key", sa.String(128), primary_key=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "waha_send_permissions",
        fk("connection_id", "waha_connections", primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("chat_ids", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "waha_send_uploads",
        sa.Column("id", sa.String(36), primary_key=True),
        fk("connection_id", "waha_connections", nullable=False),
        sa.Column("filename", sa.String(128), nullable=False),
        sa.Column("mimetype", sa.String(100), nullable=False),
        sa.Column("blob_key", sa.String(40)),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_waha_send_uploads_connection_id", "waha_send_uploads", ["connection_id"])
    op.create_index("ix_waha_send_uploads_expires_at", "waha_send_uploads", ["expires_at"])
    op.create_table(
        "waha_send_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        fk("connection_id", "waha_connections", nullable=False),
        fk("chat_id", "waha_chats", nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("bindings", sa.JSON(), nullable=False),
        sa.Column("permission_version", sa.Integer(), nullable=False),
        sa.Column("control_version", sa.Integer(), nullable=False),
        fk("approved_by", "accounts", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("maximum_uses", sa.Integer(), nullable=False),
        sa.Column("uses", sa.Integer(), nullable=False),
    )
    op.create_index("ix_waha_send_policies_connection_id", "waha_send_policies", ["connection_id"])
    op.create_table(
        "waha_send_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        fk("connection_id", "waha_connections", nullable=False),
        fk("chat_id", "waha_chats", nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("bindings", sa.JSON(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        fk("approved_by", "accounts"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("dispatch_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("dispatch_key", sa.String(36), unique=True),
        sa.Column("provider_message_id", sa.String(256)),
        sa.Column("delivery_rank", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("unknown_review", sa.JSON()),
        sa.UniqueConstraint("connection_id", "request_key", name="uq_waha_send_request"),
        sa.UniqueConstraint("connection_id", "provider_message_id", name="uq_waha_send_message"),
    )
    for column in ("connection_id", "chat_id", "dispatched_at"):
        op.create_index("ix_waha_send_actions_" + column, "waha_send_actions", [column])


def downgrade():
    for table in (
        "waha_send_actions",
        "waha_send_policies",
        "waha_send_uploads",
        "waha_send_permissions",
        "waha_send_request_fences",
    ):
        op.drop_table(table)
