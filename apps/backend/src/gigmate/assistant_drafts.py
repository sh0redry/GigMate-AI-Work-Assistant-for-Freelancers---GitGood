"""Assistant reply/polish drafts (ADR 0011, batch 3).

A draft is text the merchant may take into the chat composer. It never sends,
approves or confirms anything. Its validity is computed on read from the bindings
it was created with, mirroring ``agent_drafts``: any accepted new, edited or
revoked message advances the conversation context version and so invalidates an
unconsumed draft without a write.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, update

from gigmate.contracts import AssistantDraftView
from gigmate.db import (
    AssistantDraft,
    ConversationOrder,
    ConversationRow,
    MessageRow,
    Session,
    WorkOrderRow,
)
from gigmate.errors import BusinessError
from gigmate.message_context import source_allowed
from gigmate.planning import CLOSED

DEFAULT_TTL = timedelta(hours=24)
RETENTION = timedelta(days=30)


def ttl() -> timedelta:
    raw = os.environ.get("GIGMATE_ASSISTANT_DRAFT_TTL_MINUTES", "").strip()
    try:
        minutes = int(raw)
    except ValueError:
        return DEFAULT_TTL
    return timedelta(minutes=min(minutes, 7 * 24 * 60)) if minutes > 0 else DEFAULT_TTL


def _utc(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=UTC)


def _stamp(value):
    value = _utc(value)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def create(db, *, scope, turn, composition, now) -> AssistantDraft:
    order = scope.order
    row = AssistantDraft(
        id=str(uuid4()),
        account_id=turn.account_id,
        turn_id=turn.id,
        conversation_id=scope.conversation.id,
        work_order_id=order.id if order else None,
        base_work_order_version=order.data.get("version") if order else None,
        context_version=scope.conversation.context_version,
        kind=composition.kind,
        text=composition.text,
        sources=[s.model_dump() for s in composition.sources],
        unverified_claims=list(composition.unverified_claims),
        status="proposed",
        expires_at=now + ttl(),
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def invalid_reason(db, row: AssistantDraft) -> str | None:
    """Why an unconsumed draft can no longer be used, or None when its bindings hold."""
    conversation = db.get(ConversationRow, row.conversation_id)
    if conversation is None or conversation.account_id != row.account_id:
        return "consent_revoked"
    if not conversation.allowlisted:
        return "consent_revoked"
    if conversation.context_version != row.context_version:
        return "context_changed"
    if row.work_order_id:
        order = db.get(WorkOrderRow, row.work_order_id)
        if (
            order is None
            or order.account_id != row.account_id
            or order.data.get("status") in CLOSED
            or order.data.get("version") != row.base_work_order_version
            or db.get(ConversationOrder, (row.conversation_id, row.work_order_id)) is None
        ):
            return "order_changed"
    for source in row.sources:
        newest = db.scalar(
            select(func.max(MessageRow.revision)).where(
                MessageRow.id == source["message_id"],
                MessageRow.account_id == row.account_id,
                MessageRow.conversation_id == row.conversation_id,
            )
        )
        message = db.get(MessageRow, (source["message_id"], source["message_revision"]))
        if (
            message is None
            or newest != source["message_revision"]
            or not source_allowed(db, conversation, message)
        ):
            return "source_changed"
    return None


def _effective(db, row: AssistantDraft, now) -> tuple[str, str | None]:
    if row.status == "consumed":
        return "consumed", None
    if row.status == "revoked":
        return "revoked", "merchant"
    if _utc(row.expires_at) <= now:
        return "expired", None
    reason = invalid_reason(db, row)
    return ("revoked", reason) if reason else ("proposed", None)


def view(db, row: AssistantDraft, now=None) -> dict:
    now = now or datetime.now(UTC)
    status, reason = _effective(db, row, now)
    return AssistantDraftView(
        id=row.id,
        turn_id=row.turn_id,
        conversation_id=row.conversation_id,
        work_order_id=row.work_order_id,
        base_work_order_version=row.base_work_order_version,
        context_version=row.context_version,
        kind=row.kind,
        text=row.text,
        sources=row.sources,
        unverified_claims=row.unverified_claims,
        status=status,
        revoke_reason=reason,
        expires_at=_stamp(row.expires_at),
        created_at=_stamp(row.created_at),
        consumed_at=_stamp(row.consumed_at),
        revoked_at=_stamp(row.revoked_at),
        scrubbed_at=_stamp(row.scrubbed_at),
    ).model_dump(mode="json")


def _owned(db, account, draft_id: str, *, lock=False) -> AssistantDraft:
    query = select(AssistantDraft).where(
        AssistantDraft.id == draft_id, AssistantDraft.account_id == account.id
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise BusinessError(404, "NOT_FOUND", "Draft not found")
    return row


def get(db, account, draft_id: str) -> dict:
    return view(db, _owned(db, account, draft_id))


def consume(db, account, draft_id: str) -> dict:
    """Hand the text to the merchant's composer exactly once; nothing is sent."""
    now = datetime.now(UTC)
    row = _owned(db, account, draft_id, lock=True)
    status, reason = _effective(db, row, now)
    if status != "proposed":
        raise BusinessError(
            409,
            "ASSISTANT_DRAFT_NOT_USABLE",
            f"Draft is {status}" + (f" ({reason})" if reason else ""),
        )
    row.status, row.consumed_at = "consumed", now
    db.flush()
    return view(db, row, now)


def revoke(db, account, draft_id: str) -> dict:
    row = _owned(db, account, draft_id, lock=True)
    if row.status == "consumed":
        raise BusinessError(
            409, "ASSISTANT_DRAFT_ALREADY_CONSUMED", "A consumed draft cannot be revoked"
        )
    if row.status != "revoked":
        row.status, row.revoked_at = "revoked", datetime.now(UTC)
        db.flush()
    return view(db, row)


def scrub(factory=Session, now=None) -> int:
    """Clear draft text after the retention window; identifiers and status remain."""
    now = now or datetime.now(UTC)
    with factory.begin() as db:
        result = db.execute(
            update(AssistantDraft)
            .where(
                AssistantDraft.created_at < now - RETENTION,
                AssistantDraft.scrubbed_at.is_(None),
            )
            .values(text=None, scrubbed_at=now)
        )
        return result.rowcount or 0
