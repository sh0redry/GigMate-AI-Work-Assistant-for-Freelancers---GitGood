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

from sqlalchemy import func, select

from gigmate.contracts import ApprovalAction, AuditLog, WorkOrder
from gigmate.db import (
    ActionRow,
    AuditRow,
    ChangeRow,
    ConversationOrder,
    ConversationRow,
    MessageRow,
    WorkOrderRow,
)
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
# 附录 A: offer a time only when it comes from checked free time, never a guess.
CONFLICT_WITH_SLOT = "收到，你想改到 {when}。这个时间我已有其他安排，{slot} 可以吗？"
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
    if not isinstance(schedule, dict) or schedule.get("kind") != "timed":
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
    body = (draft_text or "").strip() or conflict_body(db, account_id, order, schedule)
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
    deferred = order_data.get("deferred") or {}
    if "schedule" in deferred:
        # The customer will answer later: keep the item open, but do not ask now.
        items = [item for item in items if not item.endswith(("_schedule", "_time"))]
        questions = []
    if "address" in deferred:
        return items, questions
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


def open_items_from_trigger(trigger):
    """Reason codes of an ``open_items:<owner>:<tag>:<codes>`` trigger.

    Read from the right so a change to the owner/tag segments cannot shift
    the codes; any other trigger kind (or a malformed one) has none.
    """
    kind, _, rest = trigger.partition(":")
    if kind != "open_items" or ":" not in rest:
        return []
    codes = rest.rpartition(":")[2]
    return [code for code in codes.split("+") if code]


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
        # Nothing to ask now (e.g. every open item is deferred): no stale question stays.
        cancel_pending(db, account_id, work_order_id=order.id, reason="deferred")
        return None
    trigger = open_items_trigger(order, conversation, items, round_of)
    if db.scalar(select(ActionRow.id).where(ActionRow.trigger == trigger)):
        return None
    sources = list(order.data.get("source_messages") or [])
    for field in order.data["fields"].values():
        for source in field["sources"]:
            if source not in sources:
                sources.append(source)
    if not sources:
        # Legacy single-order records may use the chat's newest source. Once
        # multiple orders share a chat, never borrow another job's message.
        linked = db.scalar(
            select(func.count())
            .select_from(ConversationOrder)
            .where(ConversationOrder.conversation_id == conversation.id)
        )
        sources = latest_message_source(db, account_id, conversation.id) if linked == 1 else []
    if not sources:
        return None
    cancel_pending(db, account_id, work_order_id=order.id, reason="superseded")
    body = OPEN_ITEMS_TEMPLATE.format(questions="".join(questions))
    return new_draft(db, account_id, order, conversation, trigger, body, sources)


def conflict_body(db, account_id, order, schedule):
    """The conflict question, offering the first free slot of the same length."""
    from gigmate.scheduling import free_slots, parse

    start, end = parse(schedule["start_at"]), parse(schedule["end_at"])
    slots = free_slots(db, account_id, end - start, start, exclude_order_id=order.id, count=1)
    when = local_label(schedule)
    if not slots:
        return CONFLICT_TEMPLATE.format(when=when)
    offered = datetime.fromisoformat(slots[0]["start_at"].replace("Z", "+00:00"))
    local = offered.astimezone(ZoneInfo(schedule["timezone"]))
    return CONFLICT_WITH_SLOT.format(when=when, slot=f"{local:%m/%d %H:%M}")


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
    kind = row.trigger.partition(":")[0]
    return {
        **data,
        "trigger": kind,
        "open_items": open_items_from_trigger(row.trigger),
        "closed_reason": reason,
        "closed_note": row.note,
        "reissuable": reissuable and (data["state"], reason) in REISSUABLE,
    }


def views(db, rows):
    """Mark which closed questions the merchant may ask again (the newest per order)."""
    ranked = (
        select(
            ActionRow.work_order_id.label("order_id"),
            ActionRow.id.label("action_id"),
            func.row_number()
            .over(
                partition_by=ActionRow.work_order_id,
                order_by=(ActionRow.created_at.desc(), ActionRow.id.desc()),
            )
            .label("position"),
        )
        .where(
            ActionRow.work_order_id.in_({row.work_order_id for row in rows}),
            ActionRow.account_id.in_({row.account_id for row in rows}),
        )
        .subquery()
    )
    newest = dict(
        db.execute(
            select(ranked.c.order_id, ranked.c.action_id).where(ranked.c.position == 1)
        ).all()
    )
    return [send_view(db, row, view(row, newest.get(row.work_order_id) == row.id)) for row in rows]


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
        return safe_cached_action(db, account, cached)
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
    result = send_view(db, row, view(row))
    save_result(db, account.id, scope, key, digest, result)
    return result


def reject(db, account, action_id, command, key, request_id, *, operation):
    """Reject (before approval) or cancel (before dispatch); never touches WhatsApp."""
    scope = f"{operation}:{action_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return safe_cached_action(db, account, cached)
    row = expire_if_due(locked(db, account.id, action_id))
    if operation == "cancel" and row.data["state"] == "executing":
        return cancel_handed_off(db, account, row, command, scope, key, digest, request_id)
    allowed = {"pending_approval"} if operation == "reject" else {"pending_approval", "approved"}
    if row.data["state"] not in allowed:
        raise BusinessError(409, "APPROVAL_STALE", "This action can no longer be changed")
    check_snapshot(row, command)
    close(row, "cancelled", "rejected" if operation == "reject" else "cancelled")
    row.note = command.reason[:500]
    audit(db, account.id, row, f"{operation}_action", request_id)
    result = send_view(db, row, view(row))
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
        return safe_cached_action(db, account, cached)
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
    result = send_view(db, fresh, view(fresh, True))
    save_result(db, account.id, scope, key, digest, result)
    return result


# --- Business approval → WhatsApp sending gateway (方案 §4.5、§6.2、§7; Issue #29 §1)
#
# C's approval only records the merchant's decision on the exact reply. Sending
# is a second, explicit merchant command that hands that exact text to A's
# gateway under A's own send permission. One business action maps to at most
# one gateway action through a deterministic request key, so a retried or
# repeated command can never create a second send.

SEND_KEY = "c-action:{}"
# Gateway state → business action state.
SEND_STATES = {
    "draft": "executing",
    "queued": "executing",
    "preparing": "executing",
    "dispatching": "executing",
    "accepted": "succeeded",
    "result_unknown": "result_unknown",
    "failed": "failed",
    "cancelled": "cancelled",
}


def linked_send(db, row):
    """Read only the explicit owned immutable link, never a global request key."""
    from gigmate.db import WahaChat, WahaConnection, WahaSendAction

    if not row.send_action_id:
        return None
    gateway = db.scalar(
        select(WahaSendAction)
        .join(WahaConnection, WahaConnection.id == WahaSendAction.connection_id)
        .join(WahaChat, WahaChat.id == WahaSendAction.chat_id)
        .where(
            WahaSendAction.id == row.send_action_id,
            WahaConnection.account_id == row.account_id,
            WahaChat.connection_id == WahaSendAction.connection_id,
            WahaChat.conversation_id == row.conversation_id,
        )
    )
    if gateway is None:
        return None
    command = gateway.command
    if (
        command.get("work_order_id") != row.work_order_id
        or command.get("expected_work_order_version") != row.data["bound_work_order_version"]
        or command.get("expected_context_version") != row.data["bound_context_version"]
        or {k: v for k, v in (command.get("payload") or {}).items() if v is not None}
        != {"kind": "text", "text": row.data["body"]}
    ):
        return None
    return gateway


def safe_cached_action(db, account, cached):
    # Old buggy caches may contain an unowned request-key-derived send ID.
    # Reproject links without dispatching or guessing a backfill.
    if cached.data.get("send_action_id") is not None:
        row = owned(db, ActionRow, cached.data["id"], account.id)
        return send_view(db, row, view(row))
    return cached.data


def send_view(db, row, data):
    """Add the linked gateway outcome to a business action view (read-only)."""
    send = linked_send(db, row) if row.data["state"] == "executing" else None
    if send is None:
        if row.data["state"] == "executing":
            return {
                **data,
                "state": "result_unknown",
                "delivery_status": "unknown",
                "send_action_id": None,
                "send_state": None,
                "send_error": "SEND_LINK_UNVERIFIED",
            }
        return {**data, "send_action_id": None, "send_state": None, "send_error": None}
    from gigmate import waha_send as sends

    gateway = sends.action_view(send)
    state = SEND_STATES.get(send.state, "executing")
    return {
        **data,
        "state": state,
        "delivery_status": "unknown" if state == "result_unknown" else gateway["delivery_status"],
        "provider_message_id": send.provider_message_id,
        "send_action_id": send.id,
        "send_state": send.state,
        "send_error": send.error_code,
    }


def send(db, account, action_id, command, key, request_id):
    """Hand an approved business reply to the sending gateway and queue it.

    Re-checks everything the approval was bound to (order and context
    versions, sources, the conflict basis, chat consent, an open order), then
    resolves the conversation's WhatsApp chat on the chosen connection on the
    server and creates the gateway action with the exact approved text, bound
    to the same work-order and context versions. A's own checks (send
    permission, control version, expiry, context) run before queuing and
    again before dispatch. Nothing is sent by this call itself: the gateway
    worker dispatches once; an unknown outcome is never retried.
    """
    from gigmate import waha_controls as controls
    from gigmate import waha_send as sends
    from gigmate.contracts import WahaSendDraftCommand
    from gigmate.db import WahaChat

    scope = f"send:{action_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return safe_cached_action(db, account, cached)
    row = expire_if_due(locked(db, account.id, action_id))
    existing = linked_send(db, row)
    if row.data["state"] == "executing" and existing is not None:
        result = send_view(db, row, view(row))
        save_result(db, account.id, scope, key, digest, result)
        return result
    if row.data["state"] != "approved":
        raise BusinessError(409, "APPROVAL_STALE", "Only an approved reply can be sent")
    if (
        command.expected_action_revision != row.data["revision"]
        or command.snapshot_hash != row.data["snapshot_hash"]
        or snapshot_hash(row.data) != row.data["snapshot_hash"]
    ):
        raise BusinessError(409, "APPROVAL_STALE", "The reply changed; review it again")
    order = owned(db, WorkOrderRow, row.work_order_id, account.id)
    conversation = owned(db, ConversationRow, row.conversation_id, account.id)
    if not conversation.allowlisted:
        raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
    if order.data["status"] in {"cancelled", "completed"}:
        raise BusinessError(409, "VERSION_CONFLICT", "Work order is closed")
    if (
        order.data["version"] != row.data["bound_work_order_version"]
        or conversation.context_version != row.data["bound_context_version"]
    ):
        raise BusinessError(409, "VERSION_CONFLICT", "The order or chat changed after approval")
    require_current_sources(db, account.id, conversation.id, row.data["sources"])
    if not conflict_basis(db, account.id, row):
        raise BusinessError(
            409, "APPROVAL_STALE", "The time no longer conflicts; this question is outdated"
        )
    connection = controls.owned(db, account, command.connection_id)
    connection = sends.locks(db, connection.id)
    chat = db.scalar(
        select(WahaChat).where(
            WahaChat.connection_id == connection.id,
            WahaChat.conversation_id == conversation.id,
        )
    )
    if chat is None:
        raise BusinessError(
            404, "SEND_CHAT_NOT_LINKED", "This conversation has no WhatsApp chat on that connection"
        )
    draft = WahaSendDraftCommand(
        expected_control_version=command.expected_control_version,
        expected_permission_version=command.expected_permission_version,
        chat_id=chat.id,
        expected_context_version=row.data["bound_context_version"],
        work_order_id=order.id,
        expected_work_order_version=row.data["bound_work_order_version"],
        mode="manual",
        payload={"kind": "text", "text": row.data["body"]},
    )
    from gigmate.db import WahaSendAction

    if db.scalar(
        select(WahaSendAction.id).where(
            WahaSendAction.connection_id == connection.id,
            WahaSendAction.request_key == SEND_KEY.format(row.id),
        )
    ):
        raise BusinessError(409, "SEND_REQUEST_KEY_TAKEN", "The gateway key is already occupied")
    gateway = sends.create_draft(db, connection, account, draft, SEND_KEY.format(row.id))
    row.send_action_id = gateway["id"]
    sends.approve(db, connection, account, gateway["id"], gateway["revision"])
    row.data = validate(ApprovalAction, {**row.data, "state": "executing"})
    row.active_key = None
    db.flush()
    audit(db, account.id, row, "send_action", request_id)
    result = send_view(db, row, view(row))
    save_result(db, account.id, scope, key, digest, result)
    return result


def cancel_handed_off(db, account, row, command, scope, key, digest, request_id):
    """Withdraw a reply already handed to the gateway, only while it is unsent.

    Once the gateway has started dispatching, the request cannot be pulled
    back: that is reported, never pretended away (方案 §7).
    """
    from gigmate import waha_send as sends

    check_snapshot(row, command)
    gateway = linked_send(db, row)
    if gateway is None or gateway.state not in {"draft", "queued", "preparing"}:
        raise BusinessError(409, "SEND_ALREADY_DISPATCHED", "This reply may already be sent")
    connection = sends.locks(db, gateway.connection_id)
    sends.cancel(db, connection, gateway.id, gateway.revision)
    row.note = command.reason[:500]
    audit(db, account.id, row, "cancel_action", request_id)
    result = send_view(db, row, view(row))
    save_result(db, account.id, scope, key, digest, result)
    return result


def edit(db, account, action_id, command, key, request_id):
    """Edit a pending draft (方案 §4.5 编辑后发送). The edited text needs its own approval.

    The revision increases and the snapshot hash is recomputed, so an approval
    of the old text can never apply to the new one.
    """
    scope = f"edit:{action_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return safe_cached_action(db, account, cached)
    row = expire_if_due(locked(db, account.id, action_id))
    if row.data["state"] != "pending_approval":
        raise BusinessError(
            409, "APPROVAL_STALE", "Only a draft waiting for approval can be edited"
        )
    if (
        command.expected_action_revision != row.data["revision"]
        or command.snapshot_hash != row.data["snapshot_hash"]
    ):
        raise BusinessError(409, "APPROVAL_STALE", "The draft changed; review it again")
    order = owned(db, WorkOrderRow, row.work_order_id, account.id)
    from gigmate.workorders import authorized_order_conversation

    conversation = authorized_order_conversation(db, account, order, row.conversation_id)
    if (
        order.data["status"] in {"completed", "cancelled"}
        or order.data["version"] != row.data["bound_work_order_version"]
        or conversation.context_version != row.data["bound_context_version"]
    ):
        raise BusinessError(409, "APPROVAL_STALE", "The order or conversation changed")
    require_current_sources(db, account.id, conversation.id, row.data["sources"])
    body = command.body.strip()
    if not body:
        raise BusinessError(422, "VALIDATION_FAILED", "The message is empty")
    data = {
        **row.data,
        "body": body,
        "revision": row.data["revision"] + 1,
        "expires_at": utc_text(datetime.now(UTC) + DRAFT_LIFETIME),
    }
    data["snapshot_hash"] = snapshot_hash(data)
    row.data = validate(ApprovalAction, data)
    audit(db, account.id, row, "edit_action", request_id)
    result = send_view(db, row, view(row))
    save_result(db, account.id, scope, key, digest, result)
    return result


# --- No reply (契约 §3 "No reply"): at most two follow-ups, then flag the order.

NO_REPLY_AFTER = timedelta(hours=24)
NO_REPLY_ROUNDS = 2


def follow_up_unanswered(db, now=None):
    """Hourly check: a sent open-item question unanswered for 24 hours.

    Creates a follow-up task and a new draft (still needing approval) for the
    items that remain, at most twice; after that the order is flagged
    ``customer_not_replying`` for the merchant to decide. Nothing is sent.
    Returns the number of questions handled.
    """
    from gigmate.workorders import memo_task, now_text

    now = now or datetime.now(UTC)
    handled = 0
    for row in db.scalars(
        select(ActionRow)
        .where(ActionRow.trigger.startswith("open_items:"), ActionRow.reason.is_(None))
        .with_for_update()
    ):
        if row.data["state"] != "executing":
            continue
        gateway = linked_send(db, row)
        if gateway is None or gateway.state != "accepted" or gateway.dispatched_at is None:
            continue
        sent_at = gateway.dispatched_at.replace(tzinfo=gateway.dispatched_at.tzinfo or UTC)
        if now - sent_at < NO_REPLY_AFTER:
            continue
        order = db.scalar(
            select(WorkOrderRow).where(WorkOrderRow.id == row.work_order_id).with_for_update()
        )
        conversation = db.get(ConversationRow, row.conversation_id)
        replied = any(
            message.data.get("direction") == "incoming"
            and datetime.fromisoformat(message.data["occurred_at"].replace("Z", "+00:00")) > sent_at
            for message in db.scalars(
                select(MessageRow).where(MessageRow.conversation_id == row.conversation_id)
            )
        )
        if replied or order.data["status"] != "pending_confirmation":
            row.reason = "answered"
            continue
        value = json.loads(json.dumps(order.data))
        links = dict(value.get("task_links") or {})
        rounds = sum(1 for name in links if name.startswith("no_reply_"))
        value["version"] += 1
        value["updated_at"] = now_text()
        row.reason = "no_reply"
        handled += 1
        if rounds >= NO_REPLY_ROUNDS:
            value["attention"] = sorted({*value.get("attention", []), "customer_not_replying"})
            order.data = validate(WorkOrder, value)
            continue
        local = now.astimezone(ZoneInfo("Asia/Hong_Kong"))
        task = memo_task(
            row.account_id,
            value,
            f"{local:%m/%d %H:%M} 跟进 {value['summary']}：客人未回复",
            {"kind": "instant", "at": utc_text(now), "timezone": "Asia/Hong_Kong"},
            row.data["sources"],
        )
        db.add(task)
        links[f"no_reply_{rounds + 1}"] = task.id
        value["task_links"] = links
        order.data = validate(WorkOrder, value)
        db.flush()
        ask_open_items(db, row.account_id, order, conversation, round_of=row.id)
    db.flush()
    return handled
