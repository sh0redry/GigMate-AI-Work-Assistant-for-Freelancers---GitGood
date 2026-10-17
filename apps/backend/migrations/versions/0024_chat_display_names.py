"""Keep owned chat names after short-lived discovery candidates expire."""

import sqlalchemy as sa
from alembic import op

revision = "0024_chat_display_names"
down_revision = "0023_agent_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("waha_chats", sa.Column("display_name", sa.String(200), nullable=True))
    db = op.get_bind()
    rows = db.execute(
        sa.text(
            "SELECT c.id, d.label FROM waha_chats c JOIN conversations v ON v.id=c.conversation_id JOIN waha_candidates d ON d.connection_id=c.connection_id AND d.provider_chat_id=c.provider_chat_id WHERE v.allowlisted = true ORDER BY d.expires_at"
        )
    )
    for row in rows:
        db.execute(
            sa.text("UPDATE waha_chats SET display_name=:label WHERE id=:id"),
            {"id": row.id, "label": row.label},
        )


def downgrade():
    op.drop_column("waha_chats", "display_name")
