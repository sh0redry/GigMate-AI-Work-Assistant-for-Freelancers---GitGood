"""Main C commands integrated with D's readonly delivery/recovery helpers."""

from uuid import uuid4

from sqlalchemy import func, select
from test_create_order import confirm, create, future, propose

from gigmate.db import AuditRow, CalendarRow, CommandResult, WorkOrderRow


def event_id(factory, order_id):
    with factory() as db:
        return db.scalar(select(CalendarRow.id).where(CalendarRow.work_order_id == order_id))


def test_calendar_export_survives_address_and_status_revision_changes(signed_in):
    client, factory, _, headers = signed_in
    order = create(
        client, headers, schedule=future(days=55), address="Synthetic initial venue"
    ).json()["data"]
    path = f"/api/v1/calendar-events/{event_id(factory, order['id'])}.ics"
    change, context, version = propose(factory, order["id"], "address", "Synthetic new venue")
    result = confirm(client, headers, order["id"], change, version, context, calendar=False)
    assert result.status_code == 200, result.text
    order = result.json()["data"]
    assert client.get(path).status_code == 200
    assert "LOCATION:Synthetic new venue" in client.get(path).text
    for target in ("in_progress", "waiting_customer", "completed"):
        key = str(uuid4())
        command = {"status": target, "expected_version": order["version"]}
        result = client.post(
            f"/api/v1/work-orders/{order['id']}/status",
            json=command,
            headers={**headers, "Idempotency-Key": key},
        )
        assert result.status_code == 200, result.text
        order = result.json()["data"]
        receipt = client.post(
            f"/api/v1/work-order-command-results/{key}/inspect",
            json={"kind": "status", "order_id": order["id"], "command": command},
            headers=headers,
        )
        assert receipt.status_code == 200 and receipt.json()["data"] == order
        exported = client.get(path)
        assert exported.status_code == (409 if target == "completed" else 200)
        if target != "completed":
            assert f"SEQUENCE:{order['version']}" in exported.text


def test_receipt_inspection_binds_owner_key_and_original_body_without_writing(signed_in):
    client, factory, _, headers = signed_in
    key = str(uuid4())
    command = {
        "conversation_id": "00000000-0000-4000-8000-000000000002",
        "summary": "Synthetic receipt order",
        "confirm_additional_order": True,
    }
    request = {"kind": "create", "command": command}
    path = f"/api/v1/work-order-command-results/{key}/inspect"

    def counts():
        with factory() as db:
            return tuple(
                db.scalar(select(func.count()).select_from(model))
                for model in (WorkOrderRow, CommandResult, AuditRow)
            )

    before = counts()
    response = client.post(path, json=request, headers=headers)
    assert (
        response.status_code == 409 and response.json()["error"]["code"] == "COMMAND_RESULT_PENDING"
    )
    assert counts() == before
    created = client.post(
        "/api/v1/work-orders", json=command, headers={**headers, "Idempotency-Key": key}
    )
    assert created.status_code == 201, created.text
    before = counts()
    for _ in range(2):
        found = client.post(path, json=request, headers=headers)
        assert found.status_code == 200, found.text
        assert found.json()["data"] == created.json()["data"]
    assert counts() == before
    changed = client.post(
        path, json={**request, "command": {**command, "summary": "Other contents"}}, headers=headers
    )
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert (
        client.post(path, json={**request, "order_id": str(uuid4())}, headers=headers).status_code
        == 422
    )
    assert client.post(path, json=request).status_code == 403
    login = client.post(
        "/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"}
    )
    foreign = client.post(
        path, json=request, headers={"X-CSRF-Token": login.json()["data"]["csrf_token"]}
    )
    assert foreign.status_code == 409 and "Synthetic receipt order" not in foreign.text
    assert counts() == before
    client.cookies.clear()
    assert client.post(path, json=request, headers=headers).status_code == 401


def test_confirmation_receipt_accepts_saved_proposed_result(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=56), address="Synthetic venue").json()[
        "data"
    ]
    change, context, version = propose(
        factory, order["id"], "schedule", future(days=57), customer="pending"
    )
    key = str(uuid4())
    command = {
        "expected_version": version,
        "expected_context_version": context,
        "apply_calendar_update": True,
    }
    response = client.post(
        f"/api/v1/work-orders/{order['id']}/changes/{change}/confirm",
        json=command,
        headers={**headers, "Idempotency-Key": key},
    )
    assert (
        response.status_code == 200
        and response.json()["data"]["fields"]["schedule"]["status"] == "proposed"
    )
    inspected = client.post(
        f"/api/v1/work-order-command-results/{key}/inspect",
        json={"kind": "confirm", "order_id": order["id"], "change_id": change, "command": command},
        headers=headers,
    )
    assert inspected.status_code == 200 and inspected.json()["data"] == response.json()["data"]
