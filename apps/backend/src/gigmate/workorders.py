import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from gigmate.contracts import AuditLog, CalendarEvent, Task, WorkOrder
from gigmate.db import (
    Account,
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
    if field not in {"schedule", "address"}:
        raise BusinessError(422, "VALIDATION_FAILED", "Only time and address can be confirmed")
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
    was_pending = value["status"] == "pending_confirmation"
    demoted = False
    # An order is confirmed only when both key items — a timed schedule and an
    # address — are confirmed by the merchant and by the customer.
    if was_pending and key_items_confirmed(value):
        value["status"] = "confirmed"
    elif value["status"] == "confirmed" and not key_items_confirmed(value):
        # A confirmed order whose key item is open again (awaiting the customer,
        # or a date without a time) goes back to pending; its preparation task
        # is withdrawn below and the calendar entry becomes tentative.
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
        calendar = db.scalar(
            select(CalendarRow).where(
                CalendarRow.work_order_id == order.id, CalendarRow.account_id == account.id
            )
        )
        if calendar is None:
            db.add(calendar_row(account.id, value, new_value, change.data["sources"], not timed))
        else:
            calendar.data = validate(
                CalendarEvent,
                {
                    **calendar.data,
                    "schedule": new_value,
                    "tentative": not timed,
                    "work_order_version": value["version"],
                    "sources": change.data["sources"],
                },
            )
    # The preparation task follows the confirmed time, and exists only while the
    # order itself is confirmed.
    confirmed_now = value["status"] == "confirmed" and (field == "schedule" or was_pending)
    if confirmed_now or demoted:
        for task in db.scalars(
            select(TaskRow).where(
                TaskRow.work_order_id == order.id, TaskRow.account_id == account.id
            )
        ):
            if task.generated and task.data["state"] in {"pending", "blocked"}:
                task.data = {**task.data, "state": "cancelled"}
    if confirmed_now and is_timed(schedule["value"]):
        db.add(preparation_task(account.id, value, schedule["value"], schedule["sources"]))
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


def preparation_task(account_id, order_data, schedule, sources):
    """Memo-style task, e.g. '10/08 15:30 准备 16:30 的陈小姐证件照拍摄'."""
    task_id = str(uuid4())
    start = datetime.fromisoformat(schedule["start_at"]).astimezone(ZoneInfo(schedule["timezone"]))
    # Derive display and persisted due from the same absolute instant across DST.
    ready_instant = datetime.fromisoformat(schedule["start_at"]) - timedelta(hours=1)
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
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump(mode="json"))
    if cached:
        return cached.data
    # Serialize creation per account so two clicks cannot both pass the checks below.
    db.scalar(select(Account).where(Account.id == account.id).with_for_update())
    conversation = owned(db, ConversationRow, command.conversation_id, account.id)
    if not conversation.allowlisted:
        raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
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
        db.add(preparation_task(account.id, value, schedule, schedule_sources))
    db.add(audit_row(account.id, order_id, "create_work_order", request_id))
    from gigmate.approvals import ask_open_items

    # contracts/api-v1.md section 3: a pending order gets one draft (for merchant
    # approval) asking only for its open items.
    ask_open_items(db, account.id, db.get(WorkOrderRow, order_id), conversation)
    save_result(db, account.id, scope, key, digest, value)
    return value
