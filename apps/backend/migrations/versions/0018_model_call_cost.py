"""Persist per-call cost accounting on the model-call trace.

The role B pre-activation batch 2 needs a hard, auditable ceiling on what a
single LLM call may cost. The seam (LLMProvider._SKELETON_SEAM) is still
closed in this batch, so no live call is issued and every row is null by
construction, but the column is added now so the next authorized batch can
write real numbers without a second migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_model_call_cost"
down_revision = "0017_model_call_request_id"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "model_call_traces",
        sa.Column("input_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "model_call_traces",
        sa.Column("output_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "model_call_traces",
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
    )


def downgrade():
    op.drop_column("model_call_traces", "cost_usd")
    op.drop_column("model_call_traces", "output_tokens")
    op.drop_column("model_call_traces", "input_tokens")
