"""Business detail beyond time and address (方案 §4.3、§4.4、附录 A)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from test_create_order import SAID, confirm, create, future, propose, propose_address

from gigmate.db import TaskRow


def tasks(factory, order_id):
    with factory() as db:
        return {
            row.id: row.data
            for row in db.scalars(select(TaskRow).where(TaskRow.work_order_id == order_id))
        }


def accept(client, factory, headers, order, field, value, customer="confirmed"):
    change_id, context, version = propose(factory, order["id"], field, value, customer)
    response = confirm(client, headers, order["id"], change_id, version, context, calendar=False)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_detail_fields_are_confirmed_without_changing_the_key_item_rule(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=6)).json()["data"]
    data = accept(client, factory, headers, order, "specification", "护照相 2 张，白底")
    assert data["fields"]["specification"]["status"] == "confirmed"
    assert data["status"] == "pending_confirmation"
    data = accept(client, factory, headers, data, "quantity", 2)
    assert data["fields"]["quantity"]["value"] == 2
    data = accept(client, factory, headers, data, "summary", "陈小姐护照相拍摄")
    assert data["summary"] == "陈小姐护照相拍摄"
    unverified = accept(client, factory, headers, data, "specification", "蓝底", customer="pending")
    assert unverified["fields"]["specification"]["status"] == "proposed"
    change_id, context, version = propose(factory, order["id"], "quantity", -1)
    bad = confirm(client, headers, order["id"], change_id, version, context, calendar=False)
    assert bad.status_code == 422


def test_deadline_becomes_one_delivery_task_and_a_newer_one_replaces_it(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=6), address="旺角").json()["data"]
    first_day = (datetime.now(UTC) + timedelta(days=9)).date()
    data = accept(
        client,
        factory,
        headers,
        order,
        "deadline",
        {"kind": "date_only", "date": first_day.isoformat(), "timezone": "Asia/Hong_Kong"},
    )
    first = data["task_links"]["delivery"]
    assert tasks(factory, order["id"])[first]["title"] == f"{first_day:%m/%d} 交付 陈小姐证件照拍摄"
    second_day = first_day + timedelta(days=2)
    data = accept(
        client,
        factory,
        headers,
        data,
        "deadline",
        {"kind": "date_only", "date": second_day.isoformat(), "timezone": "Asia/Hong_Kong"},
    )
    shown = tasks(factory, order["id"])
    assert shown[first]["state"] == "cancelled"
    assert shown[data["task_links"]["delivery"]]["state"] == "pending"


def requirement(client, headers, order, **body):
    return client.post(
        f"/api/v1/work-orders/{order['id']}/requirements",
        json={"sources": SAID, "expected_version": order["version"], **body},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )


def test_materials_and_promises_become_tasks_and_questions_stay_on_the_order(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=6)).json()["data"]
    data = requirement(
        client, headers, order, kind="material", text="证件尺寸", owner="customer"
    ).json()["data"]
    [item] = data["requirements"]
    assert (
        tasks(factory, order["id"])[item["task_id"]]["title"]
        == "跟进 陈小姐证件照拍摄：索取证件尺寸"
    )
    due = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    data = requirement(
        client,
        headers,
        data,
        kind="commitment",
        text="发初稿",
        owner="merchant",
        due={
            "kind": "instant",
            "at": due.isoformat().replace("+00:00", "Z"),
            "timezone": "Asia/Hong_Kong",
        },
    ).json()["data"]
    promise = data["requirements"][1]
    assert tasks(factory, order["id"])[promise["task_id"]]["title"].endswith(
        "陈小姐证件照拍摄：发初稿"
    )
    data = requirement(
        client, headers, data, kind="question", text="要不要化妆？", owner="customer"
    ).json()["data"]
    assert data["requirements"][2]["task_id"] is None
    # Confirming the address later must not cancel these tasks.
    change_id, context, version = propose_address(factory, order["id"], "旺角")
    done = confirm(client, headers, order["id"], change_id, version, context, calendar=False)
    assert done.status_code == 200, done.text
    data = done.json()["data"]
    assert data["status"] == "confirmed"
    shown = tasks(factory, order["id"])
    assert shown[item["task_id"]]["state"] == "pending"
    assert shown[promise["task_id"]]["state"] == "pending"
    closed = client.post(
        f"/api/v1/work-orders/{order['id']}/requirements/{item['id']}",
        json={"status": "done", "expected_version": data["version"]},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert closed.status_code == 200, closed.text
    assert tasks(factory, order["id"])[item["task_id"]]["state"] == "completed"
    again = client.post(
        f"/api/v1/work-orders/{order['id']}/requirements/{item['id']}",
        json={"status": "cancelled", "expected_version": closed.json()["data"]["version"]},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert again.status_code == 409


def test_requirements_need_current_version_sources_and_an_open_order(signed_in):
    client, _, _, headers = signed_in
    order = create(client, headers).json()["data"]
    stale = requirement(
        client,
        headers,
        {**order, "version": order["version"] + 1},
        kind="question",
        text="x",
        owner="customer",
    )
    assert stale.status_code == 409
    foreign = client.post(
        f"/api/v1/work-orders/{order['id']}/requirements",
        json={
            "kind": "question",
            "text": "x",
            "owner": "customer",
            "sources": [{"message_id": str(uuid4()), "message_revision": 1}],
            "expected_version": order["version"],
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert foreign.status_code == 404
    cancelled = client.post(
        f"/api/v1/work-orders/{order['id']}/status",
        json={"status": "cancelled", "expected_version": order["version"]},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    ).json()["data"]
    closed = requirement(client, headers, cancelled, kind="question", text="x", owner="customer")
    assert closed.status_code == 409
