"""Merchant-approved send_text drafts (role C, P0).

AI or templates may only *prepare* text. Nothing here talks to WhatsApp: an
approved action is durable work for a later sender, and reject/cancel are
purely local so they work while the connector is disabled.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from gigmate.contracts import ApprovalAction, AuditLog
from gigmate.db import ActionRow, AuditRow, ConversationRow, MessageRow, WorkOrderRow
from gigmate.errors import BusinessError
from gigmate.planning import conflicts
from gigmate.workorders import command_cache, owned, save_result, validate

DRAFT_LIFETIME = timedelta(hours=24)
SNAPSHOT_FIELDS = (
    "id",
    "account_id",
    "work_order_id",
    "conversation_id",
    "kind",
    "revision",
    "recipient",
    "body",
    "bound_work_order_version",
    "bound_context_version",
    "expires_at",
    "sources",
)
# Not yet handed to the sender: can still be replaced, rejected or cancelled.
NOT_DISPATCHED = {"pending_approval", "approved"}
CONFLICT_TEMPLATE = "收到，你想改到 {when}。这个时间我已有其他安排，方便换个时间吗？"


def utc_text(moment):
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def snapshot_hash(data):
    """Hash the send_text projection exactly as contracts/api-v1.md specifies."""
    projection = {name: data[name] for name in SNAPSHOT_FIELDS}
    encoded = json.dumps(projection, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def local_label(schedule):
    start = datetime.fromisoformat(schedule["start_at"]).astimezone(ZoneInfo(schedule["timezone"]))
    return f"{start:%m/%d %H:%M}"


def close(row, state, reason):
    """Move a non-dispatched action to a terminal local state."""
    row.data = validate(ApprovalAction, {**row.data, "state": state})
    row.active_key = None
    row.reason = reason


def expire_if_due(row, now=None):
    now = now or datetime.now(UTC)
    if (
        row.data["state"] == "pending_approval"
        and datetime.fromisoformat(row.data["expires_at"]) <= now
    ):
        close(row, "expired", "expired")
    return row


def cancel_pending(db, account_id, *, reason, conversation_id=None, work_order_id=None):
    """Cancel non-dispatched drafts that no longer match the conversation or order."""
    query = select(ActionRow).where(ActionRow.account_id == account_id)
    if conversation_id:
        query = query.where(ActionRow.conversation_id == conversation_id)
    if work_order_id:
        query = query.where(ActionRow.work_order_id == work_order_id)
    for row in db.scalars(query):
        if row.data["state"] in NOT_DISPATCHED:
            close(row, "cancelled", reason)
    db.flush()


def new_draft(db, account_id, order, conversation, trigger, body, sources):
    """Store one pending send_text draft bound to the current order and context."""
    now = datetime.now(UTC)
    action_id = str(uuid4())
    data = {
        "id": action_id,
        "account_id": account_id,
        "work_order_id": order.id,
        "conversation_id": conversation.id,
        "kind": "send_text",
        "revision": 1,
        "state": "pending_approval",
        "recipient": conversation.id,
        "body": body,
        "bound_work_order_version": order.data["version"],
        "bound_context_version": conversation.context_version,
        "expires_at": utc_text(now + DRAFT_LIFETIME),
        "approved_by": None,
        "approved_at": None,
        "idempotency_key": f"action:{action_id}",
        "provider_message_id": None,
        "delivery_status": "not_submitted",
        "sources": sources,
    }
    data["snapshot_hash"] = snapshot_hash(data)
    data = validate(ApprovalAction, data)
    db.add(
        ActionRow(
            id=action_id,
            account_id=account_id,
            work_order_id=order.id,
            conversation_id=conversation.id,
            trigger=trigger,
            active_key=order.id,
            reason=None,
            created_at=now,
            data=data,
        )
    )
    db.flush()
    return data


def draft_for_change(db, account_id, order, conversation, change, draft_text=None):
    """React to a new schedule proposal for an order.

    - The proposed time collides: create a draft asking for another time
      (replacing any older draft for this order).
    - The proposed time is free: the customer has answered the open question,
      so a pending conflict draft for this order is no longer needed.

    Returns the new draft data, or None. A retried worker step for the same
    change never creates a second draft.
    """
    if change["field"] != "schedule" or change["status"] != "proposed":
        return None
    schedule = change["new_value"]
    if not schedule or schedule.get("kind") != "timed":
        return None
    if not conflicts(db, account_id, order.id, schedule):
        # The customer offered a time that is free: the open question is answered.
        cancel_pending(db, account_id, work_order_id=order.id, reason="answered")
        latest = latest_by_order(db, account_id, conversation.id).get(order.id)
        if latest is not None and latest.reason in {"superseded", "expired"}:
            latest.reason = "answered"
        return None
    trigger = f"schedule_conflict:{change['id']}"
    if db.scalar(select(ActionRow.id).where(ActionRow.trigger.startswith(trigger))):
        return None
    # A newer draft for the same order replaces any older, unapproved one.
    cancel_pending(db, account_id, work_order_id=order.id, reason="superseded")
    body = (draft_text or "").strip() or CONFLICT_TEMPLATE.format(when=local_label(schedule))
    return new_draft(db, account_id, order, conversation, trigger, body, change["sources"])


def latest_by_order(db, account_id, conversation_id):
    latest = {}
    for row in db.scalars(
        select(ActionRow)
        .where(ActionRow.account_id == account_id, ActionRow.conversation_id == conversation_id)
        .order_by(ActionRow.created_at, ActionRow.id)
    ):
        latest[row.work_order_id] = expire_if_due(row)
    return latest


def hold_for_new_message(db, account_id, conversation, changed_message_id):
    """Step 1, when a message is accepted: nothing old stays approvable.

    contracts/api-v1.md sections 3–4: the non-dispatched draft (pending, or
    approved but not yet sent) is closed with reason ``superseded``. What to
    ask next is decided only after the new message is read (step 2,
    ``follow_up``). If the message edits or revokes the draft's own source,
    the question's basis is gone (``source_changed``).
    """
    for row in latest_by_order(db, account_id, conversation.id).values():
        if row.data["state"] not in NOT_DISPATCHED:
            continue
        close(row, "cancelled", "superseded")
        if any(source["message_id"] == changed_message_id for source in row.data["sources"]):
            row.reason = "source_changed"
    db.flush()


def follow_up(db, account_id, conversation):
    """Step 2, after the worker has read the new message.

    Per order, decided by what the new message said:
    - it raised a new conflict → a new question was already drafted;
    - it offered a free time → the question is answered (``answered``);
    - it did not touch the question (e.g. "谢谢") → the open question is still
      open, so the same question is asked again against the current context.
    An expired, never-approved question is also asked again here.
    """
    for order_id, row in latest_by_order(db, account_id, conversation.id).items():
        if (row.data["state"], row.reason) not in {
            ("cancelled", "superseded"),
            ("expired", "expired"),
        }:
            continue
        order = db.get(WorkOrderRow, order_id)
        if order is None or order.data["status"] in {"cancelled", "completed"}:
            continue
        trigger = f"{row.trigger.split('@', 1)[0]}@{conversation.context_version}"
        if db.scalar(select(ActionRow.id).where(ActionRow.trigger == trigger)):
            continue
        new_draft(
            db, account_id, order, conversation, trigger, row.data["body"], row.data["sources"]
        )


def view(row):
    return {
        **row.data,
        "trigger": row.trigger.split(":", 1)[0],
        "closed_reason": row.reason,
        "closed_note": row.note,
    }


def locked(db, account_id, action_id):
    row = db.scalar(
        select(ActionRow)
        .where(ActionRow.id == action_id, ActionRow.account_id == account_id)
        .with_for_update()
    )
    if not row:
        raise BusinessError(404, "NOT_FOUND", "Action not found")
    return row


def audit(db, account_id, row, operation, request_id):
    audit_id = str(uuid4())
    entry = validate(
        AuditLog,
        {
            "id": audit_id,
            "account_id": account_id,
            "actor_id": account_id,
            "entity_type": "approval_action",
            "entity_id": row.id,
            "action_id": row.id,
            "operation": operation,
            "occurred_at": utc_text(datetime.now(UTC)),
            "request_id": request_id,
        },
    )
    db.add(AuditRow(id=audit_id, account_id=account_id, data=entry))


def check_snapshot(row, command):
    if (
        command.expected_action_revision != row.data["revision"]
        or command.snapshot_hash != row.data["snapshot_hash"]
        or snapshot_hash(row.data) != row.data["snapshot_hash"]
    ):
        raise BusinessError(409, "APPROVAL_STALE", "The draft changed; review it again")


def approve(db, account, action_id, command, key, request_id):
    scope = f"approve:{action_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    row = expire_if_due(locked(db, account.id, action_id))
    if row.data["state"] != "pending_approval":
        raise BusinessError(409, "APPROVAL_STALE", "This draft can no longer be approved")
    check_snapshot(row, command)
    order = owned(db, WorkOrderRow, row.work_order_id, account.id)
    conversation = owned(db, ConversationRow, row.conversation_id, account.id)
    if not conversation.allowlisted:
        raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
    if order.data["status"] in {"cancelled", "completed"}:
        raise BusinessError(409, "VERSION_CONFLICT", "Work order is closed")
    if (
        command.expected_version != order.data["version"]
        or command.expected_version != row.data["bound_work_order_version"]
        or command.expected_context_version != conversation.context_version
        or command.expected_context_version != row.data["bound_context_version"]
    ):
        raise BusinessError(409, "VERSION_CONFLICT", "Refresh and review the current draft")
    for source in row.data["sources"]:
        latest = db.scalar(
            select(MessageRow)
            .where(
                MessageRow.id == source["message_id"],
                MessageRow.account_id == account.id,
                MessageRow.conversation_id == conversation.id,
            )
            .order_by(MessageRow.revision.desc())
        )
        if not latest or latest.revision != source["message_revision"] or latest.data["revoked"]:
            raise BusinessError(409, "APPROVAL_STALE", "Source message changed")
    row.data = validate(
        ApprovalAction,
        {
            **row.data,
            "state": "approved",
            "approved_by": account.id,
            "approved_at": utc_text(datetime.now(UTC)),
        },
    )
    audit(db, account.id, row, "approve_action", request_id)
    result = view(row)
    save_result(db, account.id, scope, key, digest, result)
    return result


def reject(db, account, action_id, command, key, request_id, *, operation):
    """Reject (before approval) or cancel (before dispatch); never touches WhatsApp."""
    scope = f"{operation}:{action_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    row = expire_if_due(locked(db, account.id, action_id))
    allowed = {"pending_approval"} if operation == "reject" else {"pending_approval", "approved"}
    if row.data["state"] not in allowed:
        raise BusinessError(409, "APPROVAL_STALE", "This action can no longer be changed")
    check_snapshot(row, command)
    close(row, "cancelled", "rejected" if operation == "reject" else "cancelled")
    row.note = command.reason[:500]
    audit(db, account.id, row, f"{operation}_action", request_id)
    result = view(row)
    save_result(db, account.id, scope, key, digest, result)
    return result
