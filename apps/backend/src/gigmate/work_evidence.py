"""Promote a reviewed attachment into work-order evidence.

This is the missing link between a processed attachment and the order it
belongs to. It is deliberately narrow:

* The caller must be the owning account and the attachment must already have
  passed the media review (``waha_media.evidence`` re-validates the exact
  attachment version, context version, reviewed result job and file bytes).
* The work order must be linked to the attachment's conversation; a merchant
  cannot attach a file from an unrelated chat.
* The row copies every binding it was created with. Later source, version or
  result changes do not rewrite history: reads compute ``stale`` instead.
* Nothing here writes a ``RequirementChange`` or marks a field confirmed.
  Evidence supports a merchant's decision; it is not a customer confirmation
  and grants no execution authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from gigmate import waha_media
from gigmate.contracts import WorkOrderEvidenceCommand
from gigmate.db import (
    ConversationOrder,
    ConversationRow,
    WahaAttachment,
    WahaConnection,
    WorkOrderEvidenceRow,
    WorkOrderRow,
)
from gigmate.errors import BusinessError
from gigmate.waha_sync import utc


def _owned_order(db, account, order_id: str) -> WorkOrderRow:
    order = db.get(WorkOrderRow, order_id)
    if not order or order.account_id != account.id:
        raise BusinessError(404, "NOT_FOUND", "Work order not found")
    return order


def _stale_reason(db, row: WorkOrderEvidenceRow) -> str | None:
    """Return why this evidence is no longer current, or ``None``.

    Read-only and cheap: it never reads the blob, so listing evidence for an
    order is not an I/O operation.
    """
    asset = db.get(WahaAttachment, row.attachment_id)
    if not asset or asset.account_id != row.account_id:
        return "MEDIA_SOURCE_EXPIRED"
    if not asset.expires_at or utc(asset.expires_at) <= datetime.now(UTC):
        return "MEDIA_SOURCE_EXPIRED"
    if asset.version != row.attachment_version or asset.sha256 != row.sha256:
        return "MEDIA_SOURCE_CHANGED"
    result = asset.result or {}
    if result.get("job_id") != row.result_job_id:
        return "MEDIA_RESULT_CHANGED"
    review = asset.review or {}
    if (
        not review.get("at")
        or review.get("sha256") != row.sha256
        or review.get("result_job_id") != row.result_job_id
        or review.get("attachment_version") != row.attachment_version
        or review.get("context_version") != row.context_version
    ):
        return "MEDIA_REVIEW_REQUIRED"
    conversation = db.get(ConversationRow, row.conversation_id)
    if not conversation or conversation.context_version != row.context_version:
        return "MEDIA_SOURCE_CHANGED"
    return None


def view(db, row: WorkOrderEvidenceRow) -> dict:
    reason = _stale_reason(db, row)
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return {
        "id": row.id,
        "work_order_id": row.work_order_id,
        "conversation_id": row.conversation_id,
        "attachment_id": row.attachment_id,
        "attachment_version": row.attachment_version,
        "context_version": row.context_version,
        "result_job_id": row.result_job_id,
        "sha256": row.sha256,
        "mimetype": row.mimetype,
        "review_note": row.review_note,
        "note": row.note,
        "created_at": created.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stale": reason is not None,
        "stale_reason": reason,
    }


def attach(db, account, order_id: str, command: WorkOrderEvidenceCommand) -> dict:
    """Persist one reviewed attachment as evidence for ``order_id``.

    Idempotent for the exact same binding: re-submitting the reviewed evidence
    returns the existing row instead of duplicating it (or inheriting a newer
    result).
    """
    _owned_order(db, account, order_id)
    asset = db.get(WahaAttachment, command.attachment_id)
    if not asset or asset.account_id != account.id:
        raise BusinessError(404, "NOT_FOUND", "Attachment not found")
    connection = db.get(WahaConnection, asset.connection_id)
    if not connection or connection.account_id != account.id:
        raise BusinessError(404, "NOT_FOUND", "Attachment not found")
    evidence = waha_media.evidence(
        db,
        connection,
        asset.id,
        command.expected_attachment_version,
        command.expected_context_version,
        str(command.expected_result_job_id),
    )
    linked = db.scalar(
        select(ConversationOrder).where(
            ConversationOrder.conversation_id == evidence["conversation_id"],
            ConversationOrder.work_order_id == order_id,
        )
    )
    if linked is None:
        raise BusinessError(
            409,
            "MEDIA_ORDER_LINK_REQUIRED",
            "The attachment's conversation is not linked to this work order",
        )
    existing = db.scalar(
        select(WorkOrderEvidenceRow).where(
            WorkOrderEvidenceRow.work_order_id == order_id,
            WorkOrderEvidenceRow.attachment_id == asset.id,
            WorkOrderEvidenceRow.attachment_version == evidence["attachment_version"],
        )
    )
    if existing is not None:
        return view(db, existing)
    row = WorkOrderEvidenceRow(
        id=str(uuid4()),
        account_id=account.id,
        work_order_id=order_id,
        conversation_id=evidence["conversation_id"],
        attachment_id=asset.id,
        attachment_version=evidence["attachment_version"],
        context_version=evidence["context_version"],
        result_job_id=evidence["result_job_id"],
        sha256=evidence["sha256"],
        source_fingerprint=evidence["source_fingerprint"],
        mimetype=asset.mimetype,
        review_note=evidence["review_note"],
        note=command.note,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return view(db, row)


def list_for_order(db, account, order_id: str) -> list[WorkOrderEvidenceRow]:
    _owned_order(db, account, order_id)
    return list(
        db.scalars(
            select(WorkOrderEvidenceRow).where(
                WorkOrderEvidenceRow.account_id == account.id,
                WorkOrderEvidenceRow.work_order_id == order_id,
            )
        )
    )


__all__ = ["attach", "list_for_order", "view"]
