"""Owned local control queue and expiring opaque chat choices."""

import sqlalchemy as sa
from alembic import op

revision = "0005_waha_controls"
down_revision = "0004_waha_recovery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "waha_connections",
        sa.Column("control_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "waha_controls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), nullable=False
        ),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("active_key", sa.String(36), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.UniqueConstraint("connection_id", "request_key", name="uq_waha_control_key"),
    )
    op.create_index("ix_waha_controls_connection_id", "waha_controls", ["connection_id"])
    op.create_table(
        "waha_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "connection_id", sa.String(36), sa.ForeignKey("waha_connections.id"), nullable=False
        ),
        sa.Column("provider_chat_id", sa.String(256), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_waha_candidates_connection_id", "waha_candidates", ["connection_id"])


def downgrade():
    op.drop_table("waha_candidates")
    op.drop_table("waha_controls")
    op.drop_column("waha_connections", "control_version")
