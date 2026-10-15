"""Join the landed C merge and the published D-03 merge without rewriting either."""

revision = "0015_d03_approval_heads"
down_revision = ("0013_merge_approval_media", "0014_media_approvals")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
