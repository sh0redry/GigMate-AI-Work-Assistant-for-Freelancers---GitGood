"""Preserve content-stop decisions independently of reconciliation state."""

import sqlalchemy as sa
from alembic import op

revision = "0012_waha_media_stop"
down_revision = "0010_waha_media_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("waha_media_jobs", sa.Column("content_stop_reason", sa.String(64)))
    # Recover still-visible historical stop evidence. Previously erased decisions
    # cannot be inferred safely from a generic unknown-result error.
    op.execute(
        sa.text(
            "UPDATE waha_media_jobs SET content_stop_reason = error_code "
            "WHERE state = 'cancelled' OR error_code IN "
            "('MEDIA_CANCELLED', 'CONSENT_REVOKED', 'MEDIA_SOURCE_EXPIRED', "
            "'MEDIA_SOURCE_CHANGED')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE waha_media_jobs SET content_stop_reason = 'MEDIA_CANCELLED' "
            "WHERE state = 'cancelled' AND content_stop_reason IS NULL"
        )
    )
    # Older reconciliation could erase the only stop marker. Conservatively
    # suppress pre-upgrade unknown/look-up results rather than republish them.
    # A definite lookup can still release their gate, without resubmission.
    op.execute(
        sa.text(
            "UPDATE waha_media_jobs SET content_stop_reason = 'MEDIA_LEGACY_REVIEW_REQUIRED' "
            "WHERE content_stop_reason IS NULL AND "
            "(state = 'result_unknown' OR stage = 'reconciling')"
        )
    )


def downgrade():
    op.drop_column("waha_media_jobs", "content_stop_reason")
