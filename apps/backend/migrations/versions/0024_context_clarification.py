"""Mainline source-bound clarification and model-context consent boundary."""

import sqlalchemy as sa
from alembic import op

revision = "0024_context_clarification"
down_revision = "0023_agent_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("proposals", sa.Column("clarification", sa.JSON(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("consent_context_version", sa.Integer(), nullable=False, server_default="0"),
    )
    # Old consent history has no trustworthy timestamp. Preserve business data,
    # but require new accepted input before old text can enter the new context feature.
    op.execute("UPDATE conversations SET consent_context_version=context_version")


def downgrade():
    op.drop_column("conversations", "consent_context_version")
    op.drop_column("proposals", "clarification")
