"""Persist safe operational evidence and recovery review; preserve prior migrations."""

import sqlalchemy as sa
from alembic import op

revision = "0004_waha_recovery"
down_revision = "0003_waha_stanza_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "service_heartbeats",
        sa.Column("service", sa.String(32), primary_key=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "waha_operations",
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), primary_key=True
        ),
        sa.Column("monitor_at", sa.DateTime(timezone=True)),
        sa.Column("api_at", sa.DateTime(timezone=True)),
        sa.Column("api_ok", sa.Boolean),
        sa.Column("provider_at", sa.DateTime(timezone=True)),
        sa.Column("provider_ok", sa.Boolean),
        sa.Column("rejected", sa.Integer, nullable=False),
        sa.Column("last_rejection_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(64)),
    )
    op.create_table(
        "waha_recovery_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), nullable=False
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("active_key", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolution", sa.String(32)),
        sa.Column("occurrences", sa.Integer, nullable=False),
        sa.UniqueConstraint("connection_id", "active_key", name="uq_waha_active_issue"),
    )
    op.create_index(
        "ix_waha_recovery_issues_connection_id", "waha_recovery_issues", ["connection_id"]
    )
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("processing_ms", sa.Integer))
        batch.add_column(sa.Column("completion_latency_ms", sa.BigInteger))
        batch.add_column(
            sa.Column("lease_recoveries", sa.Integer, nullable=False, server_default="0")
        )


def downgrade():
    with op.batch_alter_table("jobs") as batch:
        for column in (
            "lease_recoveries",
            "completion_latency_ms",
            "processing_ms",
            "completed_at",
        ):
            batch.drop_column(column)
    op.drop_table("waha_recovery_issues")
    op.drop_table("waha_operations")
    op.drop_table("service_heartbeats")
