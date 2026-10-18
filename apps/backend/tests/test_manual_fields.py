"""Merchant corrections retain sources and never inherit sending authority."""

import copy
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from gigmate.approvals import new_draft
from gigmate.db import (
    ActionRow,
    AuditRow,
    CalendarRow,
    ChangeRow,
    ConversationRow,
    MessageRow,
    WorkOrderRow,
)
from gigmate.seed import uid


def command(**updates):
    return {
        "expected_version": 1,
        "expected_context_version": 1,
        "conversation_id": uid(2),
        "field": "address",
        "value": "合成测试地址：香港大学地铁站 A 出口",
        "sources": [{"message_id": uid(5), "message_revision": 1}],
        "customer_confirmed": True,
        **updates,
    }


def post(client, headers, body, key=None):
    return client.post(
        f"/api/v1/work-orders/{uid(3)}/manual-field",
        json=body,
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def current(factory, **updates):
    with factory() as db:
        return command(
            expected_version=db.get(WorkOrderRow, uid(3)).data["version"],
            expected_context_version=db.get(ConversationRow, uid(2)).context_version,
            **updates,
        )


def test_rejected_reply_does_not_block_manual_correction(signed_in):
    client, factory, _, headers = signed_in
    with factory.begin() as db:
        order, conversation = db.get(WorkOrderRow, uid(3)), db.get(ConversationRow, uid(2))
        draft = new_draft(
            db,
            order.account_id,
            order,
            conversation,
            "open_items:test",
            "合成询问地址",
            command()["sources"],
        )
        row = db.get(ActionRow, draft["id"])
        row.data = {**row.data, "state": "rejected"}
    body = current(factory)
    response = post(client, headers, body)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["fields"]["address"]["value"] == body["value"]
    assert result["fields"]["address"]["sources"] == body["sources"]
    assert result["version"] == body["expected_version"] + 1
    with factory() as db:
        change = db.scalar(select(ChangeRow).where(ChangeRow.work_order_id == uid(3)))
        assert change.data["proposer"] == "merchant"
        assert db.scalar(select(func.count()).select_from(AuditRow)) > 0
        assert not list(
            db.scalars(select(ActionRow).where(ActionRow.data["state"].as_string() == "executing"))
        )


def test_manual_value_is_not_customer_confirmation_by_default(signed_in):
    client, factory, _, headers = signed_in
    response = post(client, headers, current(factory, customer_confirmed=False))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["fields"]["address"]["status"] == "proposed"


def test_retry_has_one_change_and_one_version_bump(signed_in):
    client, factory, _, headers = signed_in
    body, key = current(factory), str(uuid4())
    first = post(client, headers, body, key)
    second = post(client, headers, body, key)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    assert post(client, headers, {**body, "value": "另一地址"}, key).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChangeRow)) == 1


@pytest.mark.parametrize(
    "alter",
    [
        "order_version",
        "context_version",
        "revoked",
        "edited",
        "paused",
        "outgoing",
        "foreign_source",
    ],
)
def test_invalid_or_stale_source_cannot_change_the_order(signed_in, alter):
    client, factory, _, headers = signed_in
    body = current(factory)
    with factory.begin() as db:
        row = db.get(WorkOrderRow, uid(3))
        before = copy.deepcopy(row.data)
        if alter == "order_version":
            body["expected_version"] += 1
        if alter == "context_version":
            body["expected_context_version"] += 1
        if alter == "foreign_source":
            body["sources"][0]["message_id"] = str(uuid4())
        if alter == "paused":
            db.get(ConversationRow, uid(2)).allowlisted = False
        if alter in {"revoked", "outgoing"}:
            message = db.get(MessageRow, (uid(5), 1))
            message.data = {
                **message.data,
                **({"revoked": True} if alter == "revoked" else {"direction": "outgoing"}),
            }
        if alter == "edited":
            body["sources"][0]["message_revision"] += 1
    response = post(client, headers, body)
    assert response.status_code in {403, 404, 409, 422}, response.text
    with factory() as db:
        assert db.get(WorkOrderRow, uid(3)).data == before
        assert db.scalar(select(func.count()).select_from(ChangeRow)) == 0


def test_bad_value_does_not_cancel_existing_draft(signed_in):
    client, factory, _, headers = signed_in
    response = post(
        client,
        headers,
        current(
            factory,
            field="address",
            value={"kind": "date_only", "date": "2026-10-20", "timezone": "Asia/Hong_Kong"},
        ),
    )
    assert response.status_code == 422


def test_manual_time_updates_calendar(signed_in):
    client, factory, _, headers = signed_in
    schedule = {
        "kind": "timed",
        "start_at": "2030-10-20T06:00:00Z",
        "end_at": "2030-10-20T07:00:00Z",
        "timezone": "Asia/Hong_Kong",
    }
    body = current(factory, field="schedule", value=schedule, apply_calendar_update=True)
    response = post(client, headers, body)
    assert response.status_code == 200, response.text
    with factory() as db:
        event = db.scalar(select(CalendarRow).where(CalendarRow.work_order_id == uid(3)))
        assert event.data["schedule"] == schedule
        assert event.data["sources"] == body["sources"]
