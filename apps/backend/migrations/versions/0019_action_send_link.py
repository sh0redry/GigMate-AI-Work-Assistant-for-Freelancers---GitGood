"""Persist the exact business approval to owned gateway action link."""

import sqlalchemy as sa
from alembic import op

revision = "0019_action_send_link"
down_revision = "0018_schedule_settings"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("approval_actions") as batch:
        batch.add_column(sa.Column("send_action_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_approval_send_action",
            "waha_send_actions",
            ["send_action_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint("uq_approval_actions_send_action_id", ["send_action_id"])


def downgrade():
    with op.batch_alter_table("approval_actions") as batch:
        batch.drop_constraint("uq_approval_actions_send_action_id", type_="unique")
        batch.drop_constraint("fk_approval_send_action", type_="foreignkey")
        batch.drop_column("send_action_id")
