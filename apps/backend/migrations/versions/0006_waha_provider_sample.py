"""Persist detailed pairing samples for the unified UI; preserve prior migrations."""

import sqlalchemy as sa
from alembic import op

revision = "0006_waha_provider_sample"
down_revision = "0005_waha_controls"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("waha_connections", sa.Column("provider_state", sa.String(32)))
    op.add_column("waha_connections", sa.Column("provider_observed_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("waha_connections", "provider_observed_at")
    op.drop_column("waha_connections", "provider_state")
