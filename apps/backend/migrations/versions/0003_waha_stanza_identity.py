"""Index documented short edit/revoke targets; backfill exact scoped serialized IDs."""

import re

import sqlalchemy as sa
from alembic import op

revision = "0003_waha_stanza_identity"
down_revision = "0002_waha_ingress"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("waha_messages", sa.Column("stanza_id", sa.String(256)))
    op.create_index("ix_waha_message_stanza", "waha_messages", ["chat_id", "stanza_id"])
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT w.id,w.provider_message_id,c.provider_chat_id,m.data FROM waha_messages w "
            "JOIN waha_chats c ON c.id=w.chat_id "
            "JOIN message_revisions m ON m.id=w.message_id AND m.revision=w.revision"
        )
    ).mappings()
    import json

    for row in rows:
        data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        direction = data.get("direction")
        if direction not in {"incoming", "outgoing"}:
            continue
        prefix = f"{'true' if direction == 'outgoing' else 'false'}_{row['provider_chat_id']}_"
        reference = row["provider_message_id"]
        if not reference.startswith(prefix):
            continue
        tail = reference[len(prefix) :]
        if re.fullmatch(r"[A-Za-z0-9]+(?:_[^_]+)?", tail):
            connection.execute(
                sa.text("UPDATE waha_messages SET stanza_id=:stanza WHERE id=:id"),
                {"stanza": tail.split("_", 1)[0], "id": row["id"]},
            )


def downgrade():
    op.drop_index("ix_waha_message_stanza", table_name="waha_messages")
    with op.batch_alter_table("waha_messages") as batch:
        batch.drop_column("stanza_id")
