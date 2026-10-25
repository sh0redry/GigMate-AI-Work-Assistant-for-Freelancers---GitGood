import hashlib
import json
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from gigmate.contracts import AuditLog, CalendarEvent, Task, WorkOrder
from gigmate.db import (
    Account,
    ActionRow,
    AuditRow,
    CalendarRow,
    ChangeRow,
    CommandResult,
    ConversationOrder,
    ConversationRow,
    MessageRow,
    TaskRow,
    WorkOrderRow,
)
from gigmate.errors import BusinessError
from gigmate.planning import CLOSED, conflicting_orders, conflicts


def validate(model, value):
    return model.model_validate_json(json.dumps(value)).model_dump(mode="json")


def owned(db, model, resource_id, account_id):
    row = db.scalar(select(model).where(model.id == resource_id, model.account_id == account_id))
    if not row:
        raise BusinessError(404, "NOT_FOUND", "Resource not found")
    return row


def command_cache(db, account_id, scope, key, payload):
    if not key or len(key) > 128:
        raise BusinessError(
            422, "VALIDATION_FAILED", "Provide an Idempotency-Key of 1–128 characters"
        )
    if scope == "create_work_order":
        payload = {
            k: v
            for k, v in payload.items()
            if k not in {"from_proposal_id", "expected_context_version"} or v is not None
        }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    record = db.scalar(
        select(CommandResult).where(
            CommandResult.account_id == account_id,
            CommandResult.scope == scope,
            CommandResult.key == key,
        )
    )
    if record and record.digest != digest:
        raise BusinessError(
            409, "IDEMPOTENCY_CONFLICT", "Command key was reused with changed content"
        )
    return digest, record


def save_result(db, account_id, scope, key, digest, result):
    db.add(
        CommandResult(
            id=str(uuid4()), account_id=account_id, scope=scope, key=key, digest=digest, data=result
        )
    )


def confirm(db, account, work_order_id, change_id, command, key, request_id):
    scope = f"confirm:{work_order_id}:{change_id}"
    payload = command.model_dump()
    digest, cached = command_cache(db, account.id, scope, key, payload)
    if cached:
        return cached.data
    order = owned(db, WorkOrderRow, work_order_id, account.id)
    change = owned(db, ChangeRow, change_id, account.id)
    if change.work_order_id != order.id:
        raise BusinessError(404, "NOT_FOUND", "Change not found")
    conversation = owned(db, ConversationRow, change.conversation_id, account.id)
    if not conversation.allowlisted:
        raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
    if order.data["status"] in {"cancelled", "completed"}:
        raise BusinessError(409, "VERSION_CONFLICT", "Work order is closed")
    if (
        order.data["version"] != command.expected_version
        or conversation.context_version != command.expected_context_version
        or change.context_version != conversation.context_version
        or change.data["status"] != "proposed"
        or change.data["base_work_order_version"] != order.data["version"]
    ):
        raise BusinessError(
            409, "VERSION_CONFLICT", "Refresh the work order and review the current proposal"
        )
    for source in change.data["sources"]:
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
    field = change.data["field"]
    if field in DETAIL_FIELDS:
        return confirm_detail(
            db, account, order, change, conversation, request_id, scope, key, digest
        )
    if field not in {"schedule", "address"}:
        raise BusinessError(422, "VALIDATION_FAILED", "This field cannot be confirmed")
    if field == "schedule" and not command.apply_calendar_update:
        raise BusinessError(
            422,
            "VALIDATION_FAILED",
            "Confirming a time requires explicit calendar synchronization",
        )
    new_value = change.data["new_value"]
    timed = field == "schedule" and isinstance(new_value, dict) and new_value.get("kind") == "timed"
    if field == "schedule" and not isinstance(new_value, dict):
        raise BusinessError(422, "VALIDATION_FAILED", "The proposed time is empty")
    if timed:
        if conflicts(db, account.id, order.id, new_value):
            raise BusinessError(
                409, "SCHEDULE_CONFLICT", "The proposed time overlaps a confirmed appointment"
            )
    elif field == "address" and (not isinstance(new_value, str) or not new_value.strip()):
        raise BusinessError(422, "VALIDATION_FAILED", "The proposed address is empty")
    value = json.loads(json.dumps(order.data))
    value["version"] += 1
    value["updated_at"] = now_text()
    # contracts/api-v1.md section 3: a value the customer has not confirmed
    # (for example 下星期六 resolved to 10/17) stays an open item even after the
    # merchant accepts it; the follow-up draft echoes it back for checking.
    customer_confirmed = change.data["customer_confirmation"] == "confirmed"
    value["fields"][field] = {
        "value": new_value.strip() if field == "address" else new_value,
        "status": "confirmed" if customer_confirmed else "proposed",
        "sources": change.data["sources"],
        "interpretation": (
            f"Merchant explicitly approved this {field}"
            if customer_confirmed
            else f"Merchant accepted this {field}; waiting for the customer to confirm it"
        ),
    }
    if customer_confirmed:
        value = settle_deferral(db, value, field)
    was_pending = value["status"] == "pending_confirmation"
    demoted = False
    # An order is confirmed only when both key items — a timed schedule and an
    # address — are confirmed by the merchant and by the customer.
    if was_pending and key_items_confirmed(value):
        value["status"] = "confirmed"
    elif value["status"] == "confirmed" and (
        not customer_confirmed or (field == "schedule" and not timed)
    ):
        # The change itself reopens a key item (awaiting the customer, or a date
        # without a time): back to pending, preparation task withdrawn below and
        # the calendar entry tentative. Judged on this change only, so orders
        # confirmed before the key-items rule (seed data without address) are
        # not demoted by an unrelated confirmation.
        value["status"] = "pending_confirmation"
        demoted = True
    value["pending_change_ids"] = [
        item for item in value["pending_change_ids"] if item != change.id
    ]
    order.data = validate(WorkOrder, value)
    change.data = {**change.data, "status": "confirmed"}
    # Other proposals based on the previous order revision cannot still execute.
    for other in db.scalars(
        select(ChangeRow).where(
            ChangeRow.work_order_id == order.id,
            ChangeRow.account_id == account.id,
            ChangeRow.id != change.id,
        )
    ):
        if other.data["status"] == "proposed":
            other.data = {**other.data, "status": "needs_review"}
    schedule = value["fields"]["schedule"]
    if field == "schedule":
        from gigmate.approvals import cancel_pending

        # The accepted time resolves any open conflict question for this order.
        cancel_pending(db, account.id, work_order_id=order.id, reason="resolved")
        # contracts/api-v1.md section 3: the slot is held only by a timed value
        # the customer has confirmed. A time still awaiting the customer is a
        # tentative entry (shown, not counted in conflict checks) until they do.
        tentative = not (timed and customer_confirmed)
        calendar = db.scalar(
            select(CalendarRow).where(
                CalendarRow.work_order_id == order.id, CalendarRow.account_id == account.id
            )
        )
        if calendar is None:
            db.add(calendar_row(account.id, value, new_value, change.data["sources"], tentative))
        else:
            calendar.data = validate(
                CalendarEvent,
                {
                    **calendar.data,
                    "schedule": new_value,
                    "tentative": tentative,
                    "work_order_version": value["version"],
                    "sources": change.data["sources"],
                },
            )
    # The preparation task follows the confirmed time, and exists only while the
    # order itself is confirmed.
    confirmed_now = value["status"] == "confirmed" and (field == "schedule" or was_pending)
    if confirmed_now or demoted:
        keep = protected_tasks(value)
        for task in db.scalars(
            select(TaskRow).where(
                TaskRow.work_order_id == order.id, TaskRow.account_id == account.id
            )
        ):
            if (
                task.generated
                and task.id not in keep
                and task.data["state"] in {"pending", "blocked"}
            ):
                task.data = {**task.data, "state": "cancelled"}
    if confirmed_now and is_timed(schedule["value"]):
        db.add(
            preparation_task(
                account.id, value, schedule["value"], schedule["sources"], lead(db, account.id)
            )
        )
    from gigmate.approvals import ask_open_items, cancel_pending

    if was_pending and value["status"] == "confirmed":
        # Every key item is settled: no question for this order remains.
        cancel_pending(db, account.id, work_order_id=order.id, reason="resolved")
    else:
        # Ask only for what is still open (missing, or awaiting the customer).
        ask_open_items(db, account.id, order, conversation)
    db.add(audit_row(account.id, order.id, f"confirm_{field}_change", request_id))
    save_result(db, account.id, scope, key, digest, order.data)
    return order.data


def is_timed(schedule_value):
    return isinstance(schedule_value, dict) and schedule_value.get("kind") == "timed"


def key_items_confirmed(order_data):
    schedule, address = order_data["fields"]["schedule"], order_data["fields"]["address"]
    return (
        schedule["status"] == "confirmed"
        and is_timed(schedule["value"])
        and address["status"] == "confirmed"
        and isinstance(address["value"], str)
        and bool(address["value"].strip())
    )


def now_text():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def lead(db, account_id):
    from gigmate.scheduling import settings

    return settings(db, account_id).preparation_minutes


def preparation_task(account_id, order_data, schedule, sources, lead_minutes=60):
    """Memo-style task, e.g. '10/08 15:30 准备 16:30 的陈小姐证件照拍摄'.

    The lead time is the merchant's own preparation setting (方案 §4.4).
    """
    task_id = str(uuid4())
    start = datetime.fromisoformat(schedule["start_at"]).astimezone(ZoneInfo(schedule["timezone"]))
    # Derive display and persisted due from the same absolute instant across DST.
    ready_instant = datetime.fromisoformat(schedule["start_at"]) - timedelta(minutes=lead_minutes)
    ready_by = ready_instant.astimezone(ZoneInfo(schedule["timezone"]))
    due = ready_instant.isoformat().replace("+00:00", "Z")
    task = validate(
        Task,
        {
            "id": task_id,
            "account_id": account_id,
            "work_order_id": order_data["id"],
            "work_order_version": order_data["version"],
            "title": f"{ready_by:%m/%d %H:%M} 准备 {start:%H:%M} 的{order_data['summary']}",
            "owner_id": account_id,
            "due": {"kind": "instant", "at": due, "timezone": schedule["timezone"]},
            "depends_on": [],
            "state": "pending",
            "sources": sources,
        },
    )
    return TaskRow(
        id=task_id, account_id=account_id, work_order_id=order_data["id"], generated=True, data=task
    )


def calendar_row(account_id, order_data, schedule, sources, tentative):
    calendar_id = str(uuid4())
    event = validate(
        CalendarEvent,
        {
            "id": calendar_id,
            "account_id": account_id,
            "work_order_id": order_data["id"],
            "work_order_version": order_data["version"],
            "schedule": schedule,
            "tentative": tentative,
            "buffer_minutes": 0,
            "sources": sources,
        },
    )
    return CalendarRow(
        id=calendar_id, account_id=account_id, work_order_id=order_data["id"], data=event
    )


def audit_row(account_id, entity_id, operation, request_id):
    audit_id = str(uuid4())
    audit = validate(
        AuditLog,
        {
            "id": audit_id,
            "account_id": account_id,
            "actor_id": account_id,
            "entity_type": "work_order",
            "entity_id": entity_id,
            "action_id": None,
            "operation": operation,
            "occurred_at": now_text(),
            "request_id": request_id,
        },
    )
    return AuditRow(id=audit_id, account_id=account_id, data=audit)


def create(db, account, command, key, request_id):
    """Merchant creates an order from a conversation. Missing values stay missing."""
    scope = "create_work_order"
    # Lock before reading the command receipt as well as the suggestion. A
    # concurrent same-key request must see the first committed receipt.
    db.scalar(select(Account).where(Account.id == account.id).with_for_update())
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump(mode="json"))
    if cached:
        return cached.data
    conversation = owned(db, ConversationRow, command.conversation_id, account.id)
    if not conversation.allowlisted:
        raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
    from gigmate.product_commands import bind_suggestion

    suggestion = bind_suggestion(db, account.id, command)
    if (
        command.expected_context_version is not None
        and command.expected_context_version != conversation.context_version
    ):
        raise BusinessError(
            409, "VERSION_CONFLICT", "Conversation changed; review current messages"
        )
    linked = [
        order
        for order in db.scalars(
            select(WorkOrderRow)
            .join(ConversationOrder, ConversationOrder.work_order_id == WorkOrderRow.id)
            .where(
                ConversationOrder.conversation_id == conversation.id,
                WorkOrderRow.account_id == account.id,
            )
        )
        if order.data["status"] not in CLOSED
    ]
    if linked and not command.confirm_additional_order:
        raise BusinessError(
            409,
            "OPEN_ORDER_EXISTS",
            "This conversation already has an open order; confirm this is a new job",
            {"work_order_ids": sorted(order.id for order in linked)},
        )

    # Every value must point at the customer message where it was said.
    def checked(sources, label, given):
        refs = [source.model_dump() for source in sources]
        if given and not refs:
            raise BusinessError(
                422, "VALIDATION_FAILED", f"Say which message the {label} came from"
            )
        if not given and refs:
            raise BusinessError(422, "VALIDATION_FAILED", f"No {label} was given")
        for ref in refs:
            latest = db.scalar(
                select(MessageRow)
                .where(
                    MessageRow.id == ref["message_id"],
                    MessageRow.account_id == account.id,
                    MessageRow.conversation_id == conversation.id,
                )
                .order_by(MessageRow.revision.desc())
            )
            if latest is None:
                raise BusinessError(404, "NOT_FOUND", "Source message not found")
            if latest.revision != ref["message_revision"] or latest.data["revoked"]:
                raise BusinessError(409, "APPROVAL_STALE", "Source message changed")
            # Customer confirmation and merchant actions are separate facts: the
            # merchant's own reply (or our API send echo) cannot stand in for
            # what the customer said.
            if latest.data.get("direction") != "incoming":
                raise BusinessError(
                    422,
                    "VALIDATION_FAILED",
                    f"The {label} must come from a message the customer sent",
                )
        return refs

    if command.address is not None and not command.address.strip():
        raise BusinessError(422, "VALIDATION_FAILED", "The address is empty")

    schedule_sources = checked(command.schedule_sources, "time", command.schedule is not None)
    address_sources = checked(command.address_sources, "address", command.address is not None)
    schedule = command.schedule.model_dump(mode="json") if command.schedule else None
    timed = schedule is not None and schedule["kind"] == "timed"
    if timed:
        if datetime.fromisoformat(schedule["start_at"]) <= datetime.now(UTC):
            raise BusinessError(422, "VALIDATION_FAILED", "The appointment must be in the future")
        clashes = conflicting_orders(db, account.id, None, schedule)
        if clashes:
            raise BusinessError(
                409,
                "SCHEDULE_CONFLICT",
                "The time overlaps a confirmed appointment",
                {"work_order_ids": clashes},
            )
    entered = "Merchant confirmed when creating the order"
    order_id = str(uuid4())
    value = {
        "id": order_id,
        "account_id": account.id,
        "conversation_ids": [conversation.id],
        "summary": command.summary.strip(),
        "status": "pending_confirmation",
        "version": 1,
        "fields": {
            "schedule": (
                {"value": None, "status": "missing", "sources": [], "interpretation": None}
                if schedule is None
                else {
                    "value": schedule,
                    # A date without a time is only a proposal until a time is agreed.
                    "status": "confirmed" if timed else "proposed",
                    "sources": schedule_sources,
                    "interpretation": entered if timed else "Date only; time still needed",
                }
            ),
            "address": (
                {"value": None, "status": "missing", "sources": [], "interpretation": None}
                if command.address is None
                else {
                    "value": command.address.strip(),
                    "status": "confirmed",
                    "sources": address_sources,
                    "interpretation": entered,
                }
            ),
        },
        "pending_change_ids": [],
        "updated_at": now_text(),
    }
    if not value["summary"]:
        raise BusinessError(422, "VALIDATION_FAILED", "Describe the job in the summary")
    # Confirmed only when both key items are: a timed schedule and an address.
    if key_items_confirmed(value):
        value["status"] = "confirmed"
    value = validate(WorkOrder, value)
    db.add(WorkOrderRow(id=order_id, account_id=account.id, data=value))
    db.flush()
    db.add(ConversationOrder(conversation_id=conversation.id, work_order_id=order_id))
    if schedule is not None:
        # A merchant-confirmed time blocks the slot even while the address is missing.
        # Date-only entries are tentative: visible to the merchant, ignored by conflict checks.
        db.add(calendar_row(account.id, value, schedule, schedule_sources, tentative=not timed))
    if value["status"] == "confirmed":
        db.add(
            preparation_task(account.id, value, schedule, schedule_sources, lead(db, account.id))
        )
    from gigmate.product_commands import consume_suggestion

    consume_suggestion(db, account.id, suggestion, order_id)
    db.add(audit_row(account.id, order_id, "create_work_order", request_id))
    from gigmate.approvals import ask_open_items

    # contracts/api-v1.md section 3: a pending order gets one draft (for merchant
    # approval) asking only for its open items.
    ask_open_items(db, account.id, db.get(WorkOrderRow, order_id), conversation)
    save_result(db, account.id, scope, key, digest, value)
    return value


# Merchant status commands. Confirmation itself (pending_confirmation →
# confirmed) only happens through confirm(), when every key item is settled.
TRANSITIONS = {
    "unclassified": {"cancelled"},
    "pending_confirmation": {"cancelled"},
    "confirmed": {"in_progress", "waiting_customer", "completed", "cancelled"},
    "in_progress": {"waiting_customer", "completed", "cancelled"},
    "waiting_customer": {"in_progress", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def set_status(db, account, work_order_id, command, key, request_id):
    """Start, pause for the customer, complete or cancel an order; keeps all history.

    Closing an order (completed or cancelled) frees its calendar slot, cancels
    its unsent drafts and its open generated tasks, and leaves pending
    proposals for review. Nothing is deleted and nothing is sent.
    """
    scope = f"status:{work_order_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    order = db.scalar(
        select(WorkOrderRow)
        .where(WorkOrderRow.id == work_order_id, WorkOrderRow.account_id == account.id)
        .with_for_update()
    )
    if order is None:
        raise BusinessError(404, "NOT_FOUND", "Work order not found")
    if order.data["version"] != command.expected_version:
        raise BusinessError(409, "VERSION_CONFLICT", "Refresh the work order first")
    current, target = order.data["status"], command.status
    if target == "completed" and not command.acknowledge_open_items:
        unfinished = [
            item
            for item in checklist(db, account.id, order)["items"]
            if item["kind"] == "unfinished"
        ]
        if unfinished and target in TRANSITIONS[current]:
            raise BusinessError(
                409,
                "CHECKLIST_OPEN",
                "Some items are unfinished; check them or confirm completing anyway",
                {"unfinished": [item["title"] for item in unfinished]},
            )
    if target not in TRANSITIONS[current]:
        raise BusinessError(
            409,
            "INVALID_TRANSITION",
            f"A {current} order cannot become {target}",
            {"status": current, "allowed": sorted(TRANSITIONS[current])},
        )
    value = json.loads(json.dumps(order.data))
    value["version"] += 1
    value["updated_at"] = now_text()
    value["status"] = target
    if target in CLOSED:
        value["pending_change_ids"] = []
    order.data = validate(WorkOrder, value)
    if target in CLOSED:
        from gigmate.approvals import cancel_pending

        # contracts/api-v1.md section 4: closing an order cancels its unsent drafts.
        cancel_pending(db, account.id, work_order_id=order.id, reason=f"order_{target}")
        for change in db.scalars(
            select(ChangeRow).where(
                ChangeRow.work_order_id == order.id, ChangeRow.account_id == account.id
            )
        ):
            if change.data["status"] == "proposed":
                change.data = {**change.data, "status": "needs_review"}
        for task in db.scalars(
            select(TaskRow).where(
                TaskRow.work_order_id == order.id, TaskRow.account_id == account.id
            )
        ):
            if task.generated and task.data["state"] in {"pending", "blocked"}:
                task.data = {
                    **task.data,
                    "state": "completed" if target == "completed" else "cancelled",
                }
    db.add(audit_row(account.id, order.id, f"set_status_{target}", request_id))
    save_result(db, account.id, scope, key, digest, order.data)
    return order.data


def reject_change(db, account, work_order_id, change_id, command, key, request_id):
    """Merchant turns down a proposal (契约: POST /work-orders/{id}/changes/{id}/reject).

    The proposal stays in history as ``rejected`` with the merchant's reason;
    the order keeps its current values. A conflict question written for this
    proposal is withdrawn, and the open-item question is refreshed against the
    new order version. Nothing is sent.
    """
    scope = f"reject_change:{work_order_id}:{change_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    order = db.scalar(
        select(WorkOrderRow)
        .where(WorkOrderRow.id == work_order_id, WorkOrderRow.account_id == account.id)
        .with_for_update()
    )
    if order is None:
        raise BusinessError(404, "NOT_FOUND", "Work order not found")
    change = owned(db, ChangeRow, change_id, account.id)
    if change.work_order_id != order.id:
        raise BusinessError(404, "NOT_FOUND", "Change not found")
    if order.data["version"] != command.expected_version:
        raise BusinessError(409, "VERSION_CONFLICT", "Refresh the work order first")
    if change.data["status"] not in {"proposed", "needs_review"}:
        raise BusinessError(409, "VERSION_CONFLICT", "This proposal is no longer open")
    reason = command.reason.strip()
    if not reason:
        raise BusinessError(422, "VALIDATION_FAILED", "Say why the proposal is rejected")
    change.data = {**change.data, "status": "rejected", "rejection_reason": reason[:500]}
    value = json.loads(json.dumps(order.data))
    value["version"] += 1
    value["updated_at"] = now_text()
    value["pending_change_ids"] = [
        item for item in value["pending_change_ids"] if item != change.id
    ]
    order.data = validate(WorkOrder, value)
    from gigmate.approvals import NOT_DISPATCHED, ask_open_items, close

    for row in db.scalars(
        select(ActionRow).where(
            ActionRow.account_id == account.id,
            ActionRow.trigger.startswith(f"schedule_conflict:{change.id}"),
        )
    ):
        if row.data["state"] in NOT_DISPATCHED:
            close(row, "cancelled", "proposal_rejected")
    db.flush()
    conversation = db.get(ConversationRow, change.conversation_id)
    if conversation is not None:
        ask_open_items(db, account.id, order, conversation)
    db.add(audit_row(account.id, order.id, "reject_change", request_id))
    save_result(db, account.id, scope, key, digest, order.data)
    return order.data


REVIEWABLE = {"ASSIGNMENT_NEEDS_REVIEW", "EXTRACTION_NEEDS_REVIEW"}


def assign_message(db, account, job_id, command, key, request_id):
    """Merchant files an unassigned message (方案 §4.2: 由商户选择或拆分).

    ``assign`` records the chosen open order and queues the message again so
    it is understood against that one order only; the result is an ordinary
    proposal for the merchant to confirm, never a direct change. ``dismiss``
    marks it as not business. Consuming a new-order suggestion is an
    alternative final decision for that event: it cannot subsequently be
    assigned or dismissed, and a filed/dismissed event cannot create an order
    from its suggestion. Manual creation without a suggestion is a separate
    operation and does not itself file a message.
    Only the conversation's newest message can be filed, because proposals
    are always bound to the current context.
    """
    from gigmate.db import Inbox, Job, JobAssignment, ProposalDecision

    scope = f"assign:{job_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    job = db.scalar(
        select(Job).where(Job.id == job_id, Job.account_id == account.id).with_for_update()
    )
    if job is None:
        raise BusinessError(404, "NOT_FOUND", "Review item not found")
    if db.get(ProposalDecision, job.event_id) is not None:
        raise BusinessError(409, "VERSION_CONFLICT", "This message already created a work order")
    if job.error_code == "MODEL_OUTCOME_UNKNOWN" and command.action == "assign":
        raise BusinessError(
            409, "MODEL_OUTCOME_UNKNOWN", "Check the original model request; do not submit it again"
        )
    if job.state != "completed" or job.error_code not in REVIEWABLE | {"MODEL_OUTCOME_UNKNOWN"}:
        raise BusinessError(409, "VERSION_CONFLICT", "This message no longer needs a decision")
    inbox = db.get(Inbox, job.event_id)
    conversation = owned(db, ConversationRow, inbox.payload.get("conversation_id"), account.id)
    if not conversation.allowlisted:
        raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
    if (
        command.expected_context_version != conversation.context_version
        or inbox.context_version != conversation.context_version
    ):
        raise BusinessError(
            409, "VERSION_CONFLICT", "Newer messages arrived; decide on the newest one"
        )
    if command.action == "dismiss":
        job.error_code = "DISMISSED_BY_MERCHANT"
    else:
        order = owned(db, WorkOrderRow, command.work_order_id, account.id)
        if not db.get(ConversationOrder, (conversation.id, order.id)):
            raise BusinessError(404, "NOT_FOUND", "That order is not part of this conversation")
        if order.data["status"] in CLOSED:
            raise BusinessError(409, "VERSION_CONFLICT", "Work order is closed")
        existing = db.get(JobAssignment, job.id)
        if existing:
            existing.work_order_id, existing.decided_at = order.id, datetime.now(UTC)
        else:
            db.add(
                JobAssignment(
                    job_id=job.id,
                    account_id=account.id,
                    work_order_id=order.id,
                    decided_at=datetime.now(UTC),
                )
            )
        job.state, job.error_code, job.attempts = "pending", None, 0
        job.available_at, job.completed_at = datetime.now(UTC), None
    audit = audit_row(account.id, job.id, f"{command.action}_message", request_id)
    audit.data = {**audit.data, "entity_type": "message_job"}
    db.add(audit)
    result = {
        "job_id": job.id,
        "conversation_id": conversation.id,
        "action": command.action,
        "work_order_id": command.work_order_id,
        "state": job.state,
    }
    save_result(db, account.id, scope, key, digest, result)
    return result


DEFAULT_DEFERRAL = timedelta(days=3)
ITEM_LABEL = {"schedule": "时间", "address": "地址"}


def follow_up_task(account_id, order_data, field, until, timezone, sources):
    """Memo-style follow-up, e.g. '10/12 10:00 跟进 陈小姐证件照拍摄：确认时间'."""
    task_id = str(uuid4())
    local = until.astimezone(ZoneInfo(timezone))
    task = validate(
        Task,
        {
            "id": task_id,
            "account_id": account_id,
            "work_order_id": order_data["id"],
            "work_order_version": order_data["version"],
            "title": f"{local:%m/%d %H:%M} 跟进 {order_data['summary']}：确认{ITEM_LABEL[field]}",
            "owner_id": account_id,
            "due": {
                "kind": "instant",
                "at": until.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "timezone": timezone,
            },
            "depends_on": [],
            "state": "pending",
            "sources": sources,
        },
    )
    return TaskRow(
        id=task_id, account_id=account_id, work_order_id=order_data["id"], generated=True, data=task
    )


def defer_item(db, account, work_order_id, command, key, request_id):
    """The customer said they will confirm a key item later (契约 §3 Customer defers).

    The item stays open and the order stays pending, but the follow-up
    question stops asking it; a follow-up task is created for the date the
    customer gave, or 3 days later at 10:00 (Asia/Hong_Kong). Confirming the
    item later closes the deferral and completes the follow-up task.
    """
    from gigmate.approvals import ask_open_items, open_items

    scope = f"defer:{work_order_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    order = db.scalar(
        select(WorkOrderRow)
        .where(WorkOrderRow.id == work_order_id, WorkOrderRow.account_id == account.id)
        .with_for_update()
    )
    if order is None:
        raise BusinessError(404, "NOT_FOUND", "Work order not found")
    if order.data["version"] != command.expected_version:
        raise BusinessError(409, "VERSION_CONFLICT", "Refresh the work order first")
    if order.data["status"] != "pending_confirmation":
        raise BusinessError(409, "VERSION_CONFLICT", "Only an order still being confirmed")
    items, questions = open_items({**order.data, "deferred": {}})
    from gigmate.clarification import field_for_code, reply_plan

    conversation = authorized_order_conversation(
        db, account, order, order.data["conversation_ids"][0]
    )
    plan = reply_plan(db, account.id, order, conversation, items, questions)
    if plan is not None:
        items = plan[0]
    if not any(field_for_code(item) == command.field for item in items):
        raise BusinessError(409, "VERSION_CONFLICT", f"The {command.field} is not open")
    conversation_id = order.data["conversation_ids"][0]
    conversation = authorized_order_conversation(db, account, order, conversation_id)
    sources = [source.model_dump() for source in command.sources]
    for ref in sources:
        latest = db.scalar(
            select(MessageRow)
            .where(
                MessageRow.id == ref["message_id"],
                MessageRow.account_id == account.id,
                MessageRow.conversation_id == conversation.id,
            )
            .order_by(MessageRow.revision.desc())
        )
        if latest is None:
            raise BusinessError(404, "NOT_FOUND", "Source message not found")
        if latest.revision != ref["message_revision"] or latest.data["revoked"]:
            raise BusinessError(409, "APPROVAL_STALE", "Source message changed")
        if latest.data.get("direction") != "incoming":
            raise BusinessError(
                422, "VALIDATION_FAILED", "The deferral must come from what the customer said"
            )
    timezone = "Asia/Hong_Kong"
    if command.until:
        until = datetime.fromisoformat(command.until.replace("Z", "+00:00"))
    else:
        local = (datetime.now(UTC) + DEFAULT_DEFERRAL).astimezone(ZoneInfo(timezone))
        until = local.replace(hour=10, minute=0, second=0, microsecond=0)
    if until <= datetime.now(UTC):
        raise BusinessError(422, "VALIDATION_FAILED", "The follow-up date must be in the future")
    value = json.loads(json.dumps(order.data))
    previous = (value.get("deferred") or {}).get(command.field)
    if previous:
        old_task = db.get(TaskRow, previous["follow_up_task_id"])
        if old_task and old_task.data["state"] in {"pending", "blocked"}:
            old_task.data = {**old_task.data, "state": "cancelled"}
    value["version"] += 1
    value["updated_at"] = now_text()
    task = follow_up_task(account.id, value, command.field, until, timezone, sources)
    value["deferred"] = {
        **(value.get("deferred") or {}),
        command.field: {
            "until": until.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "follow_up_task_id": task.id,
            "sources": sources,
        },
    }
    order.data = validate(WorkOrder, value)
    db.add(task)
    db.flush()
    ask_open_items(db, account.id, order, conversation)
    db.add(audit_row(account.id, order.id, f"defer_{command.field}", request_id))
    save_result(db, account.id, scope, key, digest, order.data)
    return order.data


def settle_deferral(db, value, field):
    """A deferred item was confirmed: close its follow-up task (契约 §3)."""
    deferred = dict(value.get("deferred") or {})
    item = deferred.pop(field, None)
    if item is None:
        return value
    task = db.get(TaskRow, item["follow_up_task_id"])
    if task and task.data["state"] in {"pending", "blocked"}:
        task.data = {**task.data, "state": "completed"}
    return {**value, "deferred": deferred}


# --- Business detail beyond the key items (方案 §4.3、§4.4、附录 A)

DETAIL_FIELDS = {"summary", "specification", "quantity", "deadline"}


def protected_tasks(value):
    """Generated tasks that belong to commitments, deliveries or follow-ups, not to the time."""
    keep = {task for name, task in (value.get("task_links") or {}).items() if name != "preparation"}
    keep |= {item["task_id"] for item in value.get("requirements") or [] if item.get("task_id")}
    keep |= {item["follow_up_task_id"] for item in (value.get("deferred") or {}).values()}
    return keep


def memo_task(account_id, order_data, title, due, sources):
    task_id = str(uuid4())
    task = validate(
        Task,
        {
            "id": task_id,
            "account_id": account_id,
            "work_order_id": order_data["id"],
            "work_order_version": order_data["version"],
            "title": title[:300],
            "owner_id": account_id,
            "due": due,
            "depends_on": [],
            "state": "pending",
            "sources": sources,
        },
    )
    return TaskRow(
        id=task_id, account_id=account_id, work_order_id=order_data["id"], generated=True, data=task
    )


def due_label(due):
    if not due:
        return ""
    if due["kind"] == "date_only":
        return f"{date_cls.fromisoformat(due['date']):%m/%d} "
    moment = datetime.fromisoformat(due["at"].replace("Z", "+00:00"))
    return f"{moment.astimezone(ZoneInfo(due['timezone'])):%m/%d %H:%M} "


def detail_value(field, value):
    from pydantic import TypeAdapter, ValidationError

    from gigmate.contracts import DeadlineValue

    if field in {"summary", "specification"}:
        if not isinstance(value, str) or not value.strip():
            raise BusinessError(422, "VALIDATION_FAILED", f"The {field} is empty")
        text = value.strip()
        if field == "summary" and len(text) > 120:
            raise BusinessError(422, "VALIDATION_FAILED", "The summary is too long")
        return text
    if field == "quantity":
        if isinstance(value, bool) or not (
            (isinstance(value, int | float) and value > 0)
            or (isinstance(value, str) and value.strip())
        ):
            raise BusinessError(422, "VALIDATION_FAILED", "The quantity is not valid")
        return value.strip() if isinstance(value, str) else value
    try:
        return TypeAdapter(DeadlineValue).validate_python(value).model_dump(mode="json")
    except ValidationError as error:
        raise BusinessError(422, "VALIDATION_FAILED", "The deadline is not valid") from error


def confirm_detail(db, account, order, change, conversation, request_id, scope, key, digest):
    """Confirm a non-key requirement. It never decides order confirmation by itself.

    A confirmed deadline becomes the delivery task (全天交付期限 stays a date,
    not a one-hour meeting); a newer deadline replaces the old task.
    """
    from gigmate.approvals import ask_open_items

    field = change.data["field"]
    new_value = detail_value(field, change.data["new_value"])
    customer_confirmed = change.data["customer_confirmation"] == "confirmed"
    value = json.loads(json.dumps(order.data))
    value["version"] += 1
    value["updated_at"] = now_text()
    if field == "summary":
        value["summary"] = new_value
    else:
        value["fields"][field] = {
            "value": new_value,
            "status": "confirmed" if customer_confirmed else "proposed",
            "sources": change.data["sources"],
            "interpretation": (
                f"Merchant explicitly approved this {field}"
                if customer_confirmed
                else f"Merchant accepted this {field}; waiting for the customer to confirm it"
            ),
        }
    value["pending_change_ids"] = [i for i in value["pending_change_ids"] if i != change.id]
    links = dict(value.get("task_links") or {})
    if field == "deadline":
        previous = db.get(TaskRow, links.get("delivery")) if links.get("delivery") else None
        if previous and previous.data["state"] in {"pending", "blocked"}:
            previous.data = {**previous.data, "state": "cancelled"}
        links.pop("delivery", None)
        if customer_confirmed:
            task = memo_task(
                account.id,
                value,
                f"{due_label(new_value)}交付 {value['summary']}",
                new_value,
                change.data["sources"],
            )
            db.add(task)
            links["delivery"] = task.id
    value["task_links"] = links
    order.data = validate(WorkOrder, value)
    change.data = {**change.data, "status": "confirmed"}
    for other in db.scalars(
        select(ChangeRow).where(
            ChangeRow.work_order_id == order.id,
            ChangeRow.account_id == account.id,
            ChangeRow.id != change.id,
        )
    ):
        if other.data["status"] == "proposed":
            other.data = {**other.data, "status": "needs_review"}
    db.flush()
    ask_open_items(db, account.id, order, conversation)
    db.add(audit_row(account.id, order.id, f"confirm_{field}_change", request_id))
    save_result(db, account.id, scope, key, digest, order.data)
    return order.data


REQUIREMENT_TASKS = {
    # (kind, owner) → memo title; questions are tracked on the order, not as tasks.
    ("material", "customer"): "跟进 {summary}：索取{text}",
    ("material", "merchant"): "准备 {summary}：{text}",
    ("commitment", "merchant"): "{summary}：{text}",
    ("commitment", "customer"): "跟进 {summary}：客人答应{text}",
}


def locked_order(db, account, work_order_id, expected_version):
    order = db.scalar(
        select(WorkOrderRow)
        .where(WorkOrderRow.id == work_order_id, WorkOrderRow.account_id == account.id)
        .with_for_update()
    )
    if order is None:
        raise BusinessError(404, "NOT_FOUND", "Work order not found")
    if order.data["version"] != expected_version:
        raise BusinessError(409, "VERSION_CONFLICT", "Refresh the work order first")
    if order.data["status"] in CLOSED:
        raise BusinessError(409, "VERSION_CONFLICT", "Work order is closed")
    authorized_order_conversation(db, account, order, order.data["conversation_ids"][0])
    return order


def authorized_order_conversation(db, account, order, conversation_id):
    conversation = owned(db, ConversationRow, conversation_id, account.id)
    linked = db.scalar(
        select(ConversationOrder.work_order_id).where(
            ConversationOrder.work_order_id == order.id,
            ConversationOrder.conversation_id == conversation_id,
        )
    )
    if (
        not conversation.allowlisted
        or conversation_id not in order.data["conversation_ids"]
        or linked is None
    ):
        raise BusinessError(403, "CONSENT_REVOKED", "The linked conversation is not authorized")
    return conversation


def current_sources(db, account, conversation_id, sources):
    conversation = owned(db, ConversationRow, conversation_id, account.id)
    if not conversation.allowlisted:
        raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
    for ref in sources:
        latest = db.scalar(
            select(MessageRow)
            .where(
                MessageRow.id == ref["message_id"],
                MessageRow.account_id == account.id,
                MessageRow.conversation_id == conversation_id,
            )
            .order_by(MessageRow.revision.desc())
        )
        if latest is None:
            raise BusinessError(404, "NOT_FOUND", "Source message not found")
        if latest.revision != ref["message_revision"] or latest.data["revoked"]:
            raise BusinessError(409, "APPROVAL_STALE", "Source message changed")


def add_requirement(db, account, work_order_id, command, key, request_id):
    """Record a required material, a promise or an open question with its source message.

    Materials and promises become memo tasks with an owner, due time and
    source (方案 §4.4: 发初稿、索取尺寸、准备材料…); questions stay on the order.
    """
    scope = f"requirement:{work_order_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump(mode="json"))
    if cached:
        return cached.data
    order = locked_order(db, account, work_order_id, command.expected_version)
    sources = [ref.model_dump() for ref in command.sources]
    current_sources(db, account, order.data["conversation_ids"][0], sources)
    text = command.text.strip()
    if not text:
        raise BusinessError(422, "VALIDATION_FAILED", "Describe the item")
    value = json.loads(json.dumps(order.data))
    value["version"] += 1
    value["updated_at"] = now_text()
    due = command.due.model_dump(mode="json") if command.due else None
    item = {
        "id": str(uuid4()),
        "kind": command.kind,
        "text": text,
        "owner": command.owner,
        "status": "open",
        "due": due,
        "task_id": None,
        "sources": sources,
    }
    template = REQUIREMENT_TASKS.get((command.kind, command.owner))
    if template:
        task = memo_task(
            account.id,
            value,
            due_label(due) + template.format(summary=value["summary"], text=text),
            due,
            sources,
        )
        db.add(task)
        item["task_id"] = task.id
    value["requirements"] = [*(value.get("requirements") or []), item]
    order.data = validate(WorkOrder, value)
    db.add(audit_row(account.id, order.id, f"add_{command.kind}", request_id))
    save_result(db, account.id, scope, key, digest, order.data)
    return order.data


def update_requirement(db, account, work_order_id, item_id, command, key, request_id):
    """Mark a requirement done or no longer needed; its task follows."""
    scope = f"requirement:{work_order_id}:{item_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    order = locked_order(db, account, work_order_id, command.expected_version)
    value = json.loads(json.dumps(order.data))
    items = value.get("requirements") or []
    item = next((entry for entry in items if entry["id"] == item_id), None)
    if item is None:
        raise BusinessError(404, "NOT_FOUND", "Requirement not found")
    if item["status"] != "open":
        raise BusinessError(409, "VERSION_CONFLICT", "This item is already closed")
    item["status"] = command.status
    if item.get("task_id"):
        task = db.get(TaskRow, item["task_id"])
        if task and task.data["state"] in {"pending", "blocked"}:
            task.data = {
                **task.data,
                "state": "completed" if command.status == "done" else "cancelled",
            }
    value["version"] += 1
    value["updated_at"] = now_text()
    order.data = validate(WorkOrder, value)
    db.add(audit_row(account.id, order.id, f"requirement_{command.status}", request_id))
    save_result(db, account.id, scope, key, digest, order.data)
    return order.data


FIELD_LABEL = {
    "schedule": "时间",
    "address": "地址",
    "specification": "服务内容",
    "quantity": "数量",
    "deadline": "交付期限",
}


def show(value):
    if isinstance(value, dict):
        if value.get("kind") == "timed":
            start = datetime.fromisoformat(value["start_at"].replace("Z", "+00:00"))
            return f"{start.astimezone(ZoneInfo(value['timezone'])):%m/%d %H:%M}"
        if value.get("kind") == "date_only":
            return value["date"]
        if value.get("kind") == "instant":
            moment = datetime.fromisoformat(value["at"].replace("Z", "+00:00"))
            return f"{moment.astimezone(ZoneInfo(value['timezone'])):%m/%d %H:%M}"
    return str(value)


def checklist(db, account_id, order):
    """Pre-delivery check (方案 §4.6): confirmed requirements, then what is unfinished."""
    from gigmate.approvals import views

    data = order.data
    items = []
    for name, label in FIELD_LABEL.items():
        field = data["fields"].get(name) or {}
        if field.get("status") == "confirmed":
            items.append({"kind": "confirmed", "title": f"{label}：{show(field['value'])}"})
    for entry in data.get("requirements") or []:
        if entry["status"] == "done":
            items.append(
                {
                    "kind": "confirmed",
                    "title": f"已完成：{entry['text']}",
                    "requirement_id": entry["id"],
                }
            )
        elif entry["status"] == "open":
            label = {"material": "资料未齐", "commitment": "承诺未完成", "question": "问题未决"}[
                entry["kind"]
            ]
            items.append(
                {
                    "kind": "unfinished",
                    "title": f"{label}：{entry['text']}",
                    "requirement_id": entry["id"],
                    "task_id": entry.get("task_id"),
                }
            )
    for name in ("schedule", "address"):
        field = data["fields"][name]
        if field["status"] != "confirmed":
            items.append({"kind": "unfinished", "title": f"{FIELD_LABEL[name]}未确认"})
    for change in db.scalars(
        select(ChangeRow).where(
            ChangeRow.work_order_id == order.id, ChangeRow.account_id == account_id
        )
    ):
        if change.data["status"] in {"proposed", "needs_review"}:
            items.append(
                {
                    "kind": "unfinished",
                    "title": f"客人提出的{FIELD_LABEL.get(change.data['field'], change.data['field'])}未处理",
                    "change_id": change.id,
                }
            )
    rows = list(
        db.scalars(
            select(ActionRow).where(
                ActionRow.work_order_id == order.id, ActionRow.account_id == account_id
            )
        )
    )
    for view in views(db, rows) if rows else []:
        if view["state"] in {"pending_approval", "approved", "executing", "result_unknown"}:
            label = {
                "pending_approval": "有回复未批准",
                "approved": "有已批准但未发送的回复",
                "executing": "有回复正在发送",
                "result_unknown": "有回复发送结果未知",
            }[view["state"]]
            items.append({"kind": "unfinished", "title": label, "action_id": view["id"]})
    return {
        "work_order_id": order.id,
        "ready": not any(item["kind"] == "unfinished" for item in items),
        "items": items,
    }


def archive(db, account, work_order_id, command, key, request_id):
    """Archive a completed or cancelled order: hidden from the default list, history kept."""
    scope = f"archive:{work_order_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    order = db.scalar(
        select(WorkOrderRow)
        .where(WorkOrderRow.id == work_order_id, WorkOrderRow.account_id == account.id)
        .with_for_update()
    )
    if order is None:
        raise BusinessError(404, "NOT_FOUND", "Work order not found")
    if order.data["version"] != command.expected_version:
        raise BusinessError(409, "VERSION_CONFLICT", "Refresh the work order first")
    if order.data["status"] not in CLOSED or order.data.get("archived_at"):
        raise BusinessError(
            409, "INVALID_TRANSITION", "Only a closed, unarchived order can be archived"
        )
    value = json.loads(json.dumps(order.data))
    value["version"] += 1
    value["updated_at"] = value["archived_at"] = now_text()
    order.data = validate(WorkOrder, value)
    db.add(audit_row(account.id, order.id, "archive_work_order", request_id))
    save_result(db, account.id, scope, key, digest, order.data)
    return order.data
