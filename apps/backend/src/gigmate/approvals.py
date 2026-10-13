"""Merchant-approved send_text drafts (role C, P0).

AI or templates may only *prepare* text. Nothing here talks to WhatsApp: an
approved action is durable work for a later sender, and reject/cancel are
purely local so they work while the connector is disabled.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from gigmate.contracts import ApprovalAction, AuditLog
from gigmate.db import ActionRow, AuditRow, ChangeRow, ConversationRow, MessageRow, WorkOrderRow
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
OPEN_ITEMS_TEMPLATE = "你好，想跟你确认一下：{questions}"


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


def is_due(row, now=None):
    return row.data["state"] == "pending_approval" and datetime.fromisoformat(
        row.data["expires_at"]
    ) <= (now or datetime.now(UTC))


def expire_if_due(row, now=None):
    """Persist expiry. Only call on rows the caller has locked (commands, ingestion)."""
    if is_due(row, now):
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


def open_items(order_data):
    """contracts/api-v1.md section 3: the key items still open on an order.

    An item is open while its field is missing (or needs review), or proposed
    without the customer's confirmation. Returns (reason codes, questions), in
    the order the questions are asked. Resolved values the customer has not
    confirmed are echoed back so the customer can check them.
    """
    items, questions = [], []
    schedule, address = order_data["fields"]["schedule"], order_data["fields"]["address"]
    value = schedule["value"]
    if value is None or schedule["status"] in {"missing", "needs_review"}:
        items.append("missing_schedule")
        questions.append("哪天几点方便？")
    elif value["kind"] == "date_only":
        day = f"{date.fromisoformat(value['date']):%m/%d}"
        if schedule["status"] == "proposed":
            items.append("verify_schedule")
            questions.append(f"你说的是 {day} 吗？几点方便？")
        else:
            questions.append(f"{day} 几点方便？")
        items.append("missing_time")
    elif schedule["status"] == "proposed":
        items.append("verify_schedule")
        questions.append(f"时间是 {local_label(value)} 对吗？")
    if not address["value"] or address["status"] in {"missing", "needs_review"}:
        items.append("missing_address")
        questions.append("见面地址是？")
    elif address["status"] == "proposed":
        items.append("verify_address")
        questions.append(f"地址是「{address['value']}」对吗？")
    return items, questions


def latest_message_source(db, account_id, conversation_id):
    """The newest current message of the conversation, as a draft source."""
    newest = {}
    for row in db.scalars(
        select(MessageRow).where(
            MessageRow.account_id == account_id, MessageRow.conversation_id == conversation_id
        )
    ):
        if row.id not in newest or row.revision > newest[row.id].revision:
            newest[row.id] = row
    current = [row for row in newest.values() if not row.data["revoked"]]
    if not current:
        return []
    row = max(current, key=lambda item: (item.data["occurred_at"], item.id))
    return [{"message_id": row.id, "message_revision": row.revision}]


def open_items_trigger(order, conversation, items, round_of=None):
    """Unique per order version, or per reissue round (the action being replaced).

    Kept under the 128-character trigger column: at most about 100 characters.
    """
    owner, tag = (
        (round_of, f"r{conversation.context_version}")
        if round_of
        else (
            order.id,
            f"v{order.data['version']}",
        )
    )
    return f"open_items:{owner}:{tag}:{'+'.join(items)}"


def ask_open_items(db, account_id, order, conversation, round_of=None):
    """Keep one clarification draft per pending order that asks only for open items.

    Called after the merchant creates or confirms something on the order (and
    on reissue). Never sends anything: the draft waits for merchant approval.
    Returns the draft data, or None when nothing is open or the order is not
    pending.
    """
    if order.data["status"] != "pending_confirmation" or not conversation.allowlisted:
        return None
    items, questions = open_items(order.data)
    if not items:
        return None
    trigger = open_items_trigger(order, conversation, items, round_of)
    if db.scalar(select(ActionRow.id).where(ActionRow.trigger == trigger)):
        return None
    sources = []
    for field in order.data["fields"].values():
        for source in field["sources"]:
            if source not in sources:
                sources.append(source)
    sources = sources or latest_message_source(db, account_id, conversation.id)
    if not sources:
        return None
    cancel_pending(db, account_id, work_order_id=order.id, reason="superseded")
    body = OPEN_ITEMS_TEMPLATE.format(questions="".join(questions))
    return new_draft(db, account_id, order, conversation, trigger, body, sources)


def latest_by_order(db, account_id, conversation_id):
    """Newest action per order in a conversation, locked for the caller's transaction."""
    latest = {}
    for row in db.scalars(
        select(ActionRow)
        .where(ActionRow.account_id == account_id, ActionRow.conversation_id == conversation_id)
        .order_by(ActionRow.created_at, ActionRow.id)
        .with_for_update()
    ):
        latest[row.work_order_id] = row
    return latest


def source_changed(row, changed_message_id):
    return any(source["message_id"] == changed_message_id for source in row.data["sources"])


def hold_for_new_message(db, account_id, conversation, changed_message_id):
    """A new message (customer, merchant's own app reply or our own API echo) arrived.

    contracts/api-v1.md sections 3–4: nothing written for the previous context
    stays approvable, so the non-dispatched draft (pending, or approved but
    not yet sent) is closed with reason ``superseded``. The question is not
    lost: the worker reacts when the message clearly answers or changes it,
    and otherwise the merchant decides whether to ask again (``reissue``),
    because "the extractor did not understand" is not proof the question is
    still open. If the message edits or revokes the draft's own source, the
    question's basis is gone (``source_changed``), even for an expired draft.
    """
    for row in latest_by_order(db, account_id, conversation.id).values():
        expire_if_due(row)
        state = row.data["state"]
        if state in NOT_DISPATCHED:
            close(row, "cancelled", "superseded")
        if state in NOT_DISPATCHED or state == "expired":
            if source_changed(row, changed_message_id):
                row.reason = "source_changed"
    db.flush()


def conflict_basis(db, account_id, row):
    """The conflicting proposal a schedule_conflict draft was written for, if still valid."""
    kind, _, rest = row.trigger.partition(":")
    if kind != "schedule_conflict":
        return True
    change = db.get(ChangeRow, rest.split("@", 1)[0])
    if change is None or change.account_id != account_id:
        return False
    return bool(conflicts(db, account_id, row.work_order_id, change.data["new_value"]))


REISSUABLE = {("cancelled", "superseded"), ("expired", "expired")}


def view(row, reissuable=False):
    """Read-only projection: an overdue draft is shown as expired without a write."""
    data, reason = row.data, row.reason
    if is_due(row):
        data = {**data, "state": "expired"}
        reason = "expired"
    kind, *parts = row.trigger.split(":")
    return {
        **data,
        "trigger": kind,
        "open_items": parts[2].split("+") if kind == "open_items" else [],
        "closed_reason": reason,
        "closed_note": row.note,
        "reissuable": reissuable and (data["state"], reason) in REISSUABLE,
    }


def views(db, rows):
    """Mark which closed questions the merchant may ask again (the newest per order)."""
    newest = {}
    for row in db.scalars(
        select(ActionRow)
        .where(ActionRow.work_order_id.in_({row.work_order_id for row in rows}))
        .order_by(ActionRow.created_at, ActionRow.id)
    ):
        newest[row.work_order_id] = row.id
    return [view(row, newest.get(row.work_order_id) == row.id) for row in rows]


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


def require_current_sources(db, account_id, conversation_id, sources):
    for source in sources:
        latest = db.scalar(
            select(MessageRow)
            .where(
                MessageRow.id == source["message_id"],
                MessageRow.account_id == account_id,
                MessageRow.conversation_id == conversation_id,
            )
            .order_by(MessageRow.revision.desc())
        )
        if not latest or latest.revision != source["message_revision"] or latest.data["revoked"]:
            raise BusinessError(409, "APPROVAL_STALE", "Source message changed")


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
    require_current_sources(db, account.id, conversation.id, row.data["sources"])
    if not conflict_basis(db, account.id, row):
        raise BusinessError(
            409, "APPROVAL_STALE", "The time no longer conflicts; this question is outdated"
        )
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


def reissue(db, account, action_id, command, key, request_id):
    """The merchant asks the same question again against the current context.

    Allowed only for the newest action of its order when it was superseded by
    a new message or expired unapproved — never for answered, rejected,
    resolved or source-changed questions. Sources and the conflict itself are
    re-checked, so an outdated question cannot come back.
    """
    scope = f"reissue:{action_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    row = expire_if_due(locked(db, account.id, action_id))
    conversation = owned(db, ConversationRow, row.conversation_id, account.id)
    newest = latest_by_order(db, account.id, conversation.id).get(row.work_order_id)
    if newest is None or newest.id != row.id or (row.data["state"], row.reason) not in REISSUABLE:
        raise BusinessError(409, "APPROVAL_STALE", "This question cannot be asked again")
    if not conversation.allowlisted:
        raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
    if command.expected_context_version != conversation.context_version:
        raise BusinessError(409, "VERSION_CONFLICT", "Read the newest messages first")
    order = owned(db, WorkOrderRow, row.work_order_id, account.id)
    if order.data["status"] in {"cancelled", "completed"}:
        raise BusinessError(409, "VERSION_CONFLICT", "Work order is closed")
    require_current_sources(db, account.id, conversation.id, row.data["sources"])
    if not conflict_basis(db, account.id, row):
        raise BusinessError(
            409, "APPROVAL_STALE", "The time no longer conflicts; this question is outdated"
        )
    if row.trigger.startswith("open_items:"):
        # Ask only what is still open now; an answered item is never asked again.
        data = ask_open_items(db, account.id, order, conversation, round_of=row.id)
        if data is None:
            raise BusinessError(409, "APPROVAL_STALE", "Nothing is left to ask")
    else:
        # Each round gets its own durable identity: the action it replaces. A row
        # is reissued at most once (afterwards it is no longer the newest), so
        # repeated rounds in the same context never collide on the unique trigger.
        trigger = f"{row.trigger.split('@', 1)[0]}@{conversation.context_version}~{row.id}"
        data = new_draft(
            db, account.id, order, conversation, trigger, row.data["body"], row.data["sources"]
        )
    fresh = db.get(ActionRow, data["id"])
    audit(db, account.id, fresh, "reissue_action", request_id)
    result = view(fresh, True)
    save_result(db, account.id, scope, key, digest, result)
    return result
