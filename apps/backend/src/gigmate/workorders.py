import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from gigmate.contracts import AuditLog, CalendarEvent, Task, WorkOrder
from gigmate.db import (
    AuditRow,
    CalendarRow,
    ChangeRow,
    CommandResult,
    ConversationRow,
    MessageRow,
    TaskRow,
    WorkOrderRow,
)
from gigmate.errors import BusinessError
from gigmate.planning import conflicts


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
    if change.data["field"] != "schedule" or not command.apply_calendar_update:
        raise BusinessError(
            422,
            "VALIDATION_FAILED",
            "Skeleton confirmations require explicit calendar synchronization",
        )
    schedule = change.data["new_value"]
    if conflicts(db, account.id, order.id, schedule):
        raise BusinessError(
            409, "SCHEDULE_CONFLICT", "The proposed time overlaps a confirmed appointment"
        )
    value = json.loads(json.dumps(order.data))
    value["version"] += 1
    value["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    value["fields"]["schedule"] = {
        "value": schedule,
        "status": "confirmed",
        "sources": change.data["sources"],
        "interpretation": "Merchant explicitly approved this schedule",
    }
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
    calendar = db.scalar(
        select(CalendarRow).where(
            CalendarRow.work_order_id == order.id, CalendarRow.account_id == account.id
        )
    )
    calendar.data = validate(
        CalendarEvent,
        {
            **calendar.data,
            "schedule": schedule,
            "work_order_version": value["version"],
            "sources": change.data["sources"],
        },
    )
    for task in db.scalars(
        select(TaskRow).where(TaskRow.work_order_id == order.id, TaskRow.account_id == account.id)
    ):
        if task.generated and task.data["state"] in {"pending", "blocked"}:
            task.data = {**task.data, "state": "cancelled"}
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
            "account_id": account.id,
            "work_order_id": order.id,
            "work_order_version": value["version"],
            "title": f"{ready_by:%m/%d %H:%M} 准备 {start:%H:%M} 的{value['summary']}",
            "owner_id": account.id,
            "due": {"kind": "instant", "at": due, "timezone": schedule["timezone"]},
            "depends_on": [],
            "state": "pending",
            "sources": change.data["sources"],
        },
    )
    db.add(
        TaskRow(
            id=task_id, account_id=account.id, work_order_id=order.id, generated=True, data=task
        )
    )
    audit_id = str(uuid4())
    audit = validate(
        AuditLog,
        {
            "id": audit_id,
            "account_id": account.id,
            "actor_id": account.id,
            "entity_type": "work_order",
            "entity_id": order.id,
            "action_id": None,
            "operation": "confirm_schedule_change",
            "occurred_at": value["updated_at"],
            "request_id": request_id,
        },
    )
    db.add(AuditRow(id=audit_id, account_id=account.id, data=audit))
    save_result(db, account.id, scope, key, digest, order.data)
    return order.data
