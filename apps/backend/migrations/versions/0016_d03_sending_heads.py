"""Join the published D-03 and accepted sending heads without rewriting either."""

revision = "0016_d03_sending_heads"
down_revision = ("0015_d03_approval_heads", "0014_merge_approval_send")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
