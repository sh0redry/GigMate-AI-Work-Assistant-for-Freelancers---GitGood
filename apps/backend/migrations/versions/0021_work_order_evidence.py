"""Keep reviewed attachments as work-order evidence.

Additive table only: existing attachments, reviews and work orders are
untouched. The unique constraint makes re-submitting the same reviewed
binding idempotent instead of duplicating evidence.
"""

import sqlalchemy as sa
from alembic import op

revision = "0021_work_order_evidence"
down_revision = "0020_business_model_heads"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_order_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("work_order_id", sa.String(36), sa.ForeignKey("work_orders.id"), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column(
            "attachment_id",
            sa.String(36),
            sa.ForeignKey("waha_attachments.id"),
            nullable=False,
        ),
        sa.Column("attachment_version", sa.Integer, nullable=False),
        sa.Column("context_version", sa.Integer, nullable=False),
        sa.Column("result_job_id", sa.String(36), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("mimetype", sa.String(80), nullable=True),
        sa.Column("review_note", sa.String(2000), nullable=True),
        sa.Column("note", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "work_order_id",
            "attachment_id",
            "attachment_version",
            name="uq_work_order_evidence_binding",
        ),
    )
    op.create_index("ix_work_order_evidence_account_id", "work_order_evidence", ["account_id"])
    op.create_index(
        "ix_work_order_evidence_work_order_id", "work_order_evidence", ["work_order_id"]
    )
    op.create_index(
        "ix_work_order_evidence_attachment_id", "work_order_evidence", ["attachment_id"]
    )


def downgrade():
    op.drop_index("ix_work_order_evidence_attachment_id", table_name="work_order_evidence")
    op.drop_index("ix_work_order_evidence_work_order_id", table_name="work_order_evidence")
    op.drop_index("ix_work_order_evidence_account_id", table_name="work_order_evidence")
    op.drop_table("work_order_evidence")
