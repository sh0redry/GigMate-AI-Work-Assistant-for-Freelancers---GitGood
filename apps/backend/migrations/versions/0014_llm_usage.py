"""Persist vendor token accounting per model call.

Additive, nullable columns only. Historical traces keep ``NULL``: their usage
was never recorded, and guessing ``0`` would make a pre-upgrade call look like
it was free (or like it was accounted for) when the truth is unknown.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_llm_usage"
down_revision = "0013_merge_approval_media"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("model_call_traces", sa.Column("prompt_tokens", sa.Integer, nullable=True))
    op.add_column("model_call_traces", sa.Column("completion_tokens", sa.Integer, nullable=True))
    op.add_column("model_call_traces", sa.Column("total_tokens", sa.Integer, nullable=True))


def downgrade():
    op.drop_column("model_call_traces", "total_tokens")
    op.drop_column("model_call_traces", "completion_tokens")
    op.drop_column("model_call_traces", "prompt_tokens")
