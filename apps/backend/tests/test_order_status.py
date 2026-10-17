"""Role C: merchant status commands — start, wait for the customer, complete, cancel."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from gigmate.db import ActionRow, AuditRow, ChangeRow, TaskRow
from gigmate.seed import uid
from gigmate.worker import run_once

CONVERSATION = uid(2)
SEED_ORDER = uid(3)
SAID = [{"message_id": uid(5), "message_revision": 1}]


def future(days):
    start = (datetime.now(UTC) + timedelta(days=days)).replace(
        hour=7, minute=0, second=0, microsecond=0
    )
    return {
        "kind": "timed",
        "start_at": start.isoformat().replace("+00:00", "Z"),
        "end_at": (start + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "timezone": "Asia/Hong_Kong",
    }


def create(client, headers, **fields):
    body = {
        "conversation_id": CONVERSATION,
        "summary": "陈小姐证件照拍摄",
        "confirm_additional_order": True,
        **fields,
    }
    if "schedule" in fields:
        body["schedule_sources"] = SAID
    if "address" in fields:
        body["address_sources"] = SAID
    response = client.post(
        "/api/v1/work-orders", json=body, headers={**headers, "Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def status(client, headers, order, target, version=None, key=None):
    return client.post(
        f"/api/v1/work-orders/{order['id']}/status",
        json={"status": target, "expected_version": version or order["version"]},
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def tasks(factory, order_id):
    with factory() as db:
        return list(db.scalars(select(TaskRow).where(TaskRow.work_order_id == order_id)))


def test_confirmed_order_moves_through_its_life_cycle(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(3), address="旺角")
    assert order["status"] == "confirmed"
    for target in ["in_progress", "waiting_customer", "in_progress", "completed"]:
        response = status(client, headers, order, target)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == target
        assert response.json()["data"]["version"] == order["version"] + 1
        order = response.json()["data"]
    # The preparation task is closed as done, not deleted.
    [task] = tasks(factory, order["id"])
    assert task.data["state"] == "completed"
    with factory() as db:
        operations = [row.data["operation"] for row in db.scalars(select(AuditRow))]
    assert operations.count("set_status_in_progress") == 2
    assert "set_status_completed" in operations


def test_closed_orders_are_final_and_pending_orders_cannot_be_completed(signed_in):
    client, _, _, headers = signed_in
    pending = create(client, headers)
    refused = status(client, headers, pending, "completed")
    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["code"] == "INVALID_TRANSITION"
    assert error["details"] == {"status": "pending_confirmation", "allowed": ["cancelled"]}
    cancelled = status(client, headers, pending, "cancelled").json()["data"]
    again = status(client, headers, cancelled, "in_progress")
    assert again.status_code == 409
    assert again.json()["error"]["details"]["allowed"] == []


def test_cancelling_closes_drafts_tasks_proposals_and_frees_the_slot(signed_in):
    client, factory, _, headers = signed_in
    slot = future(5)
    pending = create(client, headers, schedule=slot)
    with factory() as db:
        [draft] = db.scalars(select(ActionRow).where(ActionRow.work_order_id == pending["id"]))
        assert draft.data["state"] == "pending_approval"
    cancelled = status(client, headers, pending, "cancelled")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "cancelled"
    with factory() as db:
        draft = db.get(ActionRow, draft.id)
        assert (draft.data["state"], draft.reason) == ("cancelled", "order_cancelled")
    # The same time can be booked again; the cancelled order stays as history.
    create(client, headers, schedule=slot)
    assert client.get(f"/api/v1/work-orders/{pending['id']}").json()["data"]["status"] == (
        "cancelled"
    )


def test_cancelled_order_no_longer_takes_new_messages(signed_in):
    client, factory, _, headers = signed_in
    seed = client.get(f"/api/v1/work-orders/{SEED_ORDER}").json()["data"]
    assert status(client, headers, seed, "cancelled").status_code == 200
    fresh = create(client, headers)
    response = client.post(
        "/api/v1/replay",
        json={"scenario": "available"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202
    assert run_once(factory)
    with factory() as db:
        changes = list(db.scalars(select(ChangeRow)))
    # The customer's new time now attaches to the open order, not the cancelled one.
    assert [change.work_order_id for change in changes] == [fresh["id"]]


def test_status_command_checks_version_and_is_idempotent(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(6), address="旺角")
    stale = status(client, headers, order, "in_progress", version=order["version"] + 1)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    key = str(uuid4())
    first = status(client, headers, order, "in_progress", key=key)
    second = status(client, headers, order, "in_progress", key=key)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    reused = status(client, headers, order, "completed", key=key)
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    other = client.post(
        f"/api/v1/work-orders/{uuid4()}/status",
        json={"status": "cancelled", "expected_version": 1},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert other.status_code == 404
