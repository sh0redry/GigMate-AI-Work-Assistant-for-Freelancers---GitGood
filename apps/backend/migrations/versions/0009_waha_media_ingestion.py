"""Owned media storage, bounded processing leases and separate review evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0009_waha_media_ingestion"
down_revision = "0008_waha_message_sync"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "waha_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(36),
            sa.ForeignKey("waha_snapshots.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), nullable=False
        ),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("blob_key", sa.String(40)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("mimetype", sa.String(80)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("result", sa.JSON()),
        sa.Column("review", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_waha_attachments_connection_id", "waha_attachments", ["connection_id"])
    op.create_index("ix_waha_attachments_expires_at", "waha_attachments", ["expires_at"])
    op.create_table(
        "waha_media_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "attachment_id", sa.String(36), sa.ForeignKey("waha_attachments.id"), nullable=False
        ),
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), nullable=False
        ),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("active_key", sa.String(36), unique=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("retry_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "request_key", name="uq_waha_media_key"),
    )
    op.create_index("ix_waha_media_jobs_connection_id", "waha_media_jobs", ["connection_id"])
    op.create_index("ix_waha_media_jobs_attachment_id", "waha_media_jobs", ["attachment_id"])


def downgrade():
    op.drop_table("waha_media_jobs")
    op.drop_table("waha_attachments")
