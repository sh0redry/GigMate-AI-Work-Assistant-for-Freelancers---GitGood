"""Join role C approval actions and WAHA media ingestion without rewriting either branch."""

revision = "0013_merge_approval_media"
down_revision = ("0009_approval_actions", "0012_waha_media_stop")
branch_labels = None
depends_on = None


def upgrade():
    # Alembic applies both parent branches before recording this merge point.
    pass


def downgrade():
    pass
