"""Persist AI extraction evidence; preserve prior migrations.

Adds:

- ``proposals`` — full validated ``ChangeProposal`` payload per source event,
  including assignment, change list, unresolved questions and provider versions.
- ``model_call_traces`` — provider call evidence (latency, refusal reason,
  notes) per proposal; required for evaluation and post-hoc review.
- ``evaluation_runs`` and ``evaluation_cases`` — offline benchmark evidence
  for prompt/model/version iterations.

0001..0004 are untouched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_extraction_evidence"
down_revision = "0004_waha_recovery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("inbox.id"), nullable=False),
        sa.Column("work_order_id", sa.String(36), sa.ForeignKey("work_orders.id")),
        sa.Column("assignment", sa.String(24), nullable=False),
        sa.Column("context_version", sa.Integer, nullable=False),
        sa.Column("base_work_order_version", sa.Integer),
        sa.Column("proposal", sa.JSON, nullable=False),
        sa.Column("changes", sa.JSON, nullable=False),
        sa.Column("unresolved_questions", sa.JSON, nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("draft_text", sa.String(2048)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_proposals_account_id", "proposals", ["account_id"])
    op.create_index("ix_proposals_event_id", "proposals", ["event_id"])
    op.create_table(
        "model_call_traces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("provider_name", sa.String(48), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("refused_reason", sa.String(256)),
        sa.Column("notes", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_call_traces_account_id", "model_call_traces", ["account_id"])
    op.create_index("ix_model_call_traces_proposal_id", "model_call_traces", ["proposal_id"])
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_name", sa.String(48), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("case_count", sa.Integer, nullable=False),
        sa.Column("passed", sa.Integer, nullable=False),
        sa.Column("failed", sa.Integer, nullable=False),
        sa.Column("manifest_path", sa.String(512), nullable=False),
    )
    op.create_index("ix_evaluation_runs_account_id", "evaluation_runs", ["account_id"])
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("evaluation_runs.id"), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("scenario", sa.String(128), nullable=False),
        sa.Column("expected_assignment", sa.String(24), nullable=False),
        sa.Column("actual_assignment", sa.String(24), nullable=False),
        sa.Column("actual_confidence", sa.Float, nullable=False),
        sa.Column("expected_min_confidence", sa.Float),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expected_change_fields", sa.JSON, nullable=False),
        sa.Column("actual_change_fields", sa.JSON, nullable=False),
        sa.Column("message", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluation_cases_run_id", "evaluation_cases", ["run_id"])


def downgrade():
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_runs")
    op.drop_table("model_call_traces")
    op.drop_table("proposals")
