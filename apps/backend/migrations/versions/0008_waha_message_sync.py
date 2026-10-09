"""Durable bounded read-only synchronization and provenance-preserving snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0008_waha_message_sync"
down_revision = "0007_merge_waha_extraction"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "waha_controls", sa.Column("parameters", sa.JSON(), nullable=False, server_default="{}")
    )
    op.create_table(
        "waha_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("waha_chats.id"), nullable=False),
        sa.Column("provider_message_id", sa.String(256), nullable=False),
        sa.Column("stanza_id", sa.String(256)),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("chat_id", "provider_message_id", name="uq_waha_snapshot"),
    )
    op.create_index("ix_waha_snapshots_chat_id", "waha_snapshots", ["chat_id"])
    op.create_index("ix_waha_snapshot_stanza", "waha_snapshots", ["chat_id", "stanza_id"])
    op.create_table(
        "waha_observation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), nullable=False
        ),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("waha_snapshots.id"), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_waha_observation_receipts_connection_id", "waha_observation_receipts", ["connection_id"]
    )
    op.create_index(
        "ix_waha_observation_receipts_snapshot_id", "waha_observation_receipts", ["snapshot_id"]
    )
    op.create_table(
        "waha_sync_exclusions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), nullable=False
        ),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("waha_chats.id")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_waha_sync_exclusions_connection_id", "waha_sync_exclusions", ["connection_id"]
    )
    op.create_table(
        "waha_source_gaps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("waha_chats.id"), nullable=False),
        sa.Column("provider_reference", sa.String(256), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "chat_id", "provider_reference", "direction", name="uq_waha_source_gap"
        ),
    )
    op.create_index("ix_waha_source_gaps_chat_id", "waha_source_gaps", ["chat_id"])
    op.create_table(
        "waha_sync_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), nullable=False
        ),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("active_key", sa.String(36), unique=True),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("error_code", sa.String(64)),
        sa.UniqueConstraint("connection_id", "request_key", name="uq_waha_sync_key"),
    )
    op.create_index("ix_waha_sync_jobs_connection_id", "waha_sync_jobs", ["connection_id"])


def downgrade():
    for table in (
        "waha_sync_jobs",
        "waha_source_gaps",
        "waha_sync_exclusions",
        "waha_observation_receipts",
        "waha_snapshots",
    ):
        op.drop_table(table)
    op.drop_column("waha_controls", "parameters")
