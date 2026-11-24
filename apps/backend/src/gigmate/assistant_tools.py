"""Read-only tools the bounded assistant may run (ADR 0011).

Every tool works on a ``Scope`` the server resolved from the merchant's explicit
selection; no tool accepts an ID from the model. Tools never write, confirm,
approve or send. Each returns plain data for the server-side renderer plus the
citations that justify it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from gigmate import scheduling
from gigmate.assistant_plan import (
    FindFreeSlots,
    GetWorkOrder,
    ListWorkOrders,
    ReadConversation,
)
from gigmate.db import ConversationOrder, ConversationRow, WorkOrderRow
from gigmate.message_context import bounded_incoming

OPEN = {"pending_confirmation", "confirmed", "in_progress", "waiting_customer"}
MAX_ORDERS = 20
MAX_SLOTS = 10


class ToolUnavailable(Exception):
    """The plan asked for something the merchant did not select."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Scope:
    account_id: str
    conversation: ConversationRow | None = None
    order: WorkOrderRow | None = None
    selected_sources: list[dict] = field(default_factory=list)


def find_free_slots(db, scope: Scope, call: FindFreeSlots) -> dict:
    config = scheduling.settings(db, scope.account_id)
    tz = ZoneInfo(config.timezone)
    start = datetime.combine(call.from_date, time.min, tz)
    end = datetime.combine(call.to_date + timedelta(days=1), time.min, tz)
    slots = scheduling.free_slots(
        db,
        scope.account_id,
        timedelta(minutes=call.duration_minutes),
        start,
        count=MAX_SLOTS,
        days=(end - start).days,
    )
    inside = [s for s in slots if scheduling.parse(s["end_at"]) <= end]
    return {
        "timezone": config.timezone,
        "duration_minutes": call.duration_minutes,
        "slots": inside,
        "citations": [{"kind": "free_slots"}],
    }


def _summary(order: WorkOrderRow) -> dict:
    data = order.data
    return {
        "id": order.id,
        "version": data.get("version"),
        "summary": data.get("summary"),
        "status": data.get("status"),
    }


def list_work_orders(db, scope: Scope, call: ListWorkOrders) -> dict:
    query = select(WorkOrderRow).where(WorkOrderRow.account_id == scope.account_id)
    if call.scope == "selected_conversation":
        if scope.conversation is None:
            raise ToolUnavailable("ASSISTANT_SELECTION_REQUIRED")
        query = query.join(
            ConversationOrder, ConversationOrder.work_order_id == WorkOrderRow.id
        ).where(ConversationOrder.conversation_id == scope.conversation.id)
    wanted = OPEN if call.status == "open" else {call.status}
    orders = [
        _summary(row)
        for row in db.scalars(query.order_by(WorkOrderRow.id))
        if row.data.get("status") in wanted and not row.data.get("archived_at")
    ][:MAX_ORDERS]
    return {
        "orders": orders,
        "citations": [
            {"kind": "work_order", "work_order_id": o["id"], "work_order_version": o["version"]}
            for o in orders
        ],
    }


def get_work_order(db, scope: Scope, call: GetWorkOrder) -> dict:
    if scope.order is None:
        raise ToolUnavailable("ASSISTANT_SELECTION_REQUIRED")
    data = scope.order.data
    fields = {
        name: value.get("status")
        for name, value in (data.get("fields") or {}).items()
        if isinstance(value, dict)
    }
    order = {**_summary(scope.order), "field_status": fields}
    return {
        "order": order,
        "citations": [
            {
                "kind": "work_order",
                "work_order_id": order["id"],
                "work_order_version": order["version"],
            }
        ],
    }


def read_conversation(db, scope: Scope, call: ReadConversation) -> dict:
    if scope.conversation is None:
        raise ToolUnavailable("ASSISTANT_SELECTION_REQUIRED")
    messages = bounded_incoming(db, scope.conversation)
    return {
        "messages": list(messages),
        "citations": [
            {
                "kind": "message",
                "message": {
                    "message_id": m["message_id"],
                    "message_revision": m["message_revision"],
                },
            }
            for m in messages
        ],
    }


TOOLS = {
    "find_free_slots": find_free_slots,
    "list_work_orders": list_work_orders,
    "get_work_order": get_work_order,
    "read_conversation": read_conversation,
}


def run(db, scope: Scope, call) -> dict:
    return TOOLS[call.tool](db, scope, call)
