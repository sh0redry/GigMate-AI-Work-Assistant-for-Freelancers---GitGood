"""Persist the Role B vendor correlation id with each model call trace."""

import sqlalchemy as sa
from alembic import op

revision = "0017_model_call_request_id"
down_revision = "0016_d03_sending_heads"
branch_labels = None
depends_on = None


def upgrade():
    # No backfill: traces written before this batch never issued a vendor
    # request, so their correlation id is genuinely unknown (NULL), not empty.
    op.add_column("model_call_traces", sa.Column("request_id", sa.String(64)))


def downgrade():
    op.drop_column("model_call_traces", "request_id")
