"""Join shared media-stop and sending migrations without rewriting either."""

revision = "0013_merge_media_send"
down_revision = ("0011_waha_multitype_sending", "0012_waha_media_stop")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
