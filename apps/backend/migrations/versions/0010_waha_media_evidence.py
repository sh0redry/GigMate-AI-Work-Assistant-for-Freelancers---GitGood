"""Keep original message time separate and freeze media processing context."""

import sqlalchemy as sa
from alembic import op

revision = "0010_waha_media_evidence"
down_revision = "0009_waha_media_ingestion"
branch_labels = None
depends_on = None


def upgrade():
    # No backfill: prior event/observation times are not original sending evidence.
    op.add_column("waha_snapshots", sa.Column("message_sent_at", sa.DateTime(timezone=True)))
    op.add_column("waha_media_jobs", sa.Column("input_context", sa.JSON()))


def downgrade():
    op.drop_column("waha_media_jobs", "input_context")
    op.drop_column("waha_snapshots", "message_sent_at")
