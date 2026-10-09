"""Join WAHA controls/samples and extraction evidence without rewriting either branch."""

revision = "0007_merge_waha_extraction"
down_revision = ("0006_waha_provider_sample", "0005_extraction_evidence")
branch_labels = None
depends_on = None


def upgrade():
    # Alembic applies both parent branches before recording this merge point.
    pass


def downgrade():
    pass
