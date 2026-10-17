"""Role C: the customer will confirm later (契约 §3 Customer defers)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from test_create_order import SAID, confirm, create, drafts, future, propose_address

from gigmate.db import TaskRow


def defer(client, headers, order, field="address", until=None, sources=None, version=None):
    body = {
        "field": field,
        "sources": sources or SAID,
        "expected_version": version or order["version"],
    }
    if until:
        body["until"] = until
    return client.post(
        f"/api/v1/work-orders/{order['id']}/defer",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )


def tasks(factory, order_id):
    with factory() as db:
        return list(db.scalars(select(TaskRow).where(TaskRow.work_order_id == order_id)))


def test_deferred_item_stays_open_but_is_not_asked_and_gets_a_follow_up(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=8)).json()["data"]
    [question] = drafts(client, order["id"])
    assert question["open_items"] == ["missing_address"]
    response = defer(client, headers, order)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "pending_confirmation"
    assert set(data["deferred"]) == {"address"}
    # Nothing is left to ask now, so the old question is withdrawn.
    assert drafts(client, order["id"]) == []
    [task] = tasks(factory, order["id"])
    due = datetime.fromisoformat(data["deferred"]["address"]["until"].replace("Z", "+00:00"))
    local = due.astimezone(ZoneInfo("Asia/Hong_Kong"))
    assert (local.hour, local.minute) == (10, 0)
    assert (
        local.date()
        == (datetime.now(UTC) + timedelta(days=3)).astimezone(ZoneInfo("Asia/Hong_Kong")).date()
    )
    assert task.data["title"] == f"{local:%m/%d} 10:00 跟进 陈小姐证件照拍摄：确认地址"
    assert task.data["state"] == "pending"


def test_customer_date_is_used_and_confirmation_closes_the_follow_up(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=8)).json()["data"]
    until = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0)
    data = defer(client, headers, order, until=until.isoformat().replace("+00:00", "Z")).json()[
        "data"
    ]
    [task] = tasks(factory, order["id"])
    assert task.data["due"]["at"] == until.isoformat().replace("+00:00", "Z")
    change_id, context, version = propose_address(factory, order["id"], "旺角")
    done = confirm(client, headers, order["id"], change_id, version, context, calendar=False)
    assert done.status_code == 200, done.text
    result = done.json()["data"]
    assert result["status"] == "confirmed"
    assert result["deferred"] == {}
    states = {row.id: row.data["state"] for row in tasks(factory, order["id"])}
    assert states[task.id] == "completed"
    assert data["version"] < result["version"]


def test_only_open_items_of_pending_orders_from_the_customer_can_be_deferred(signed_in):
    client, factory, _, headers = signed_in
    confirmed = create(client, headers, schedule=future(days=9), address="旺角").json()["data"]
    assert defer(client, headers, confirmed).status_code == 409
    order = create(client, headers, address="旺角").json()["data"]
    # The address is settled; only the time is open.
    assert defer(client, headers, order, field="address").status_code == 409
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    assert defer(client, headers, order, field="schedule", until=past).status_code == 422
    stale = defer(client, headers, order, field="schedule", version=order["version"] + 1)
    assert stale.status_code == 409
    missing = defer(
        client,
        headers,
        order,
        field="schedule",
        sources=[{"message_id": str(uuid4()), "message_revision": 1}],
    )
    assert missing.status_code == 404
    ok = defer(client, headers, order, field="schedule")
    assert ok.status_code == 200, ok.text
    [task] = tasks(factory, order["id"])
    assert task.data["title"].endswith("跟进 陈小姐证件照拍摄：确认时间")
