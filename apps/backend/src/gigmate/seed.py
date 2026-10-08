"""Idempotent development seed; never resets existing work or accounts."""

import copy
from uuid import uuid4

from sqlalchemy import select

from gigmate.config import DEMO_PASSWORD
from gigmate.contracts import CalendarEvent, Task, WorkOrder
from gigmate.db import (
    Account,
    CalendarRow,
    ConversationOrder,
    ConversationRow,
    MessageRow,
    Session,
    TaskRow,
    WorkOrderRow,
)
from gigmate.identity import password_hash
from gigmate.messaging import fixture
from gigmate.workorders import validate


def uid(n):
    return f"00000000-0000-4000-8000-{n:012}"


def seed(factory=Session):
    with factory.begin() as db:
        for index, username in [(1, "merchant"), (99, "other")]:
            # Serialize repeated seed executions through the unique account identity.
            if db.scalar(select(Account).where(Account.username == username)):
                continue
            account_id, conversation_id, order_id = (
                uid(index),
                uid(2 if index == 1 else 22),
                uid(3 if index == 1 else 23),
            )
            db.add(
                Account(
                    id=account_id,
                    username=username,
                    password_hash=password_hash(DEMO_PASSWORD),
                    active=True,
                )
            )
            db.flush()
            db.add(
                ConversationRow(
                    id=conversation_id, account_id=account_id, context_version=4, allowlisted=True
                )
            )
            order = copy.deepcopy(fixture("work-order"))
            message_id = uid(5 if index == 1 else 25)
            order.update(id=order_id, account_id=account_id, conversation_ids=[conversation_id])
            order["fields"]["schedule"]["sources"] = [
                {"message_id": message_id, "message_revision": 1}
            ]
            db.add(
                WorkOrderRow(id=order_id, account_id=account_id, data=validate(WorkOrder, order))
            )
            db.flush()
            db.add(ConversationOrder(conversation_id=conversation_id, work_order_id=order_id))
            original = fixture("message-original")
            db.add(
                MessageRow(
                    id=message_id,
                    revision=1,
                    account_id=account_id,
                    conversation_id=conversation_id,
                    provider_message_id=f"synthetic:original-{index}",
                    data={
                        "id": message_id,
                        "account_id": account_id,
                        "conversation_id": conversation_id,
                        "provider_message_id": f"synthetic:original-{index}",
                        "revision": 1,
                        "direction": "incoming",
                        "source": "replay",
                        "occurred_at": original["occurred_at"],
                        "text": original["payload"]["text"],
                        "revoked": False,
                    },
                )
            )
            calendar_id = str(uuid4())
            db.add(
                CalendarRow(
                    id=calendar_id,
                    account_id=account_id,
                    work_order_id=order_id,
                    data=validate(
                        CalendarEvent,
                        {
                            "id": calendar_id,
                            "account_id": account_id,
                            "work_order_id": order_id,
                            "work_order_version": 3,
                            "schedule": order["fields"]["schedule"]["value"],
                            "tentative": False,
                            "buffer_minutes": 0,
                            "sources": order["fields"]["schedule"]["sources"],
                        },
                    ),
                )
            )
            task_id = str(uuid4())
            db.add(
                TaskRow(
                    id=task_id,
                    account_id=account_id,
                    work_order_id=order_id,
                    generated=True,
                    data=validate(
                        Task,
                        {
                            "id": task_id,
                            "account_id": account_id,
                            "work_order_id": order_id,
                            "work_order_version": 3,
                            "title": "10/07 14:00 准备 15:00 的虚构业务预约",
                            "owner_id": account_id,
                            "due": {
                                "kind": "instant",
                                "at": "2026-10-07T06:00:00Z",
                                "timezone": "Asia/Hong_Kong",
                            },
                            "depends_on": [],
                            "state": "pending",
                            "sources": order["fields"]["schedule"]["sources"],
                        },
                    ),
                )
            )
            if index == 1:
                conflict = copy.deepcopy(order)
                conflict.update(id=uid(13), summary="另一项已确认预约", conversation_ids=[uid(14)])
                conflict["fields"]["schedule"]["value"] = fixture("proposal-reschedule")["changes"][
                    0
                ]["new_value"]
                conflict["fields"]["schedule"]["sources"] = [
                    {"message_id": uid(15), "message_revision": 1}
                ]
                db.add(
                    ConversationRow(
                        id=uid(14), account_id=account_id, context_version=1, allowlisted=True
                    )
                )
                db.add(
                    WorkOrderRow(
                        id=uid(13), account_id=account_id, data=validate(WorkOrder, conflict)
                    )
                )
                db.flush()
                db.add(ConversationOrder(conversation_id=uid(14), work_order_id=uid(13)))
                db.add(
                    MessageRow(
                        id=uid(15),
                        revision=1,
                        account_id=account_id,
                        conversation_id=uid(14),
                        provider_message_id="synthetic:conflict",
                        data={
                            "id": uid(15),
                            "account_id": account_id,
                            "conversation_id": uid(14),
                            "provider_message_id": "synthetic:conflict",
                            "revision": 1,
                            "direction": "incoming",
                            "source": "replay",
                            "occurred_at": "2026-10-01T00:00:00Z",
                            "text": "确认十月八日下午三点到四点",
                            "revoked": False,
                        },
                    )
                )
                calendar_id = str(uuid4())
                db.add(
                    CalendarRow(
                        id=calendar_id,
                        account_id=account_id,
                        work_order_id=uid(13),
                        data=validate(
                            CalendarEvent,
                            {
                                "id": calendar_id,
                                "account_id": account_id,
                                "work_order_id": uid(13),
                                "work_order_version": 3,
                                "schedule": conflict["fields"]["schedule"]["value"],
                                "tentative": False,
                                "buffer_minutes": 0,
                                "sources": conflict["fields"]["schedule"]["sources"],
                            },
                        ),
                    )
                )


if __name__ == "__main__":
    seed()
    print("Synthetic accounts and appointments seeded; existing data preserved.")
