"""Independent synthetic HTTP probes; never run a provider or dispatch worker."""

import copy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from test_business_send import approved_question, ingress, send  # noqa: F401
from test_business_send import setup as gateway_setup_fixture
from test_create_order import create, future, propose
from test_deferral import defer
from test_requirements import requirement

from gigmate.db import (
    ActionRow,
    ConversationRow,
    WahaChat,
    WahaConnection,
    WahaSendAction,
    WahaSendPermission,
)
from gigmate.seed import uid


@pytest.fixture
def setup(ingress, monkeypatch, tmp_path):  # noqa: F811
    return gateway_setup_fixture.__wrapped__(ingress, monkeypatch, tmp_path)


@pytest.mark.parametrize("operation", ["lookup", "cancel"])
def test_business_send_cannot_link_or_cancel_another_account(setup, operation):
    s = setup
    client, factory, _, binding, _ = s
    _, action = approved_question(s)
    foreign_connection, foreign_chat, foreign_conversation = [str(uuid4()) for _ in range(3)]
    with factory.begin() as db:
        old = db.get(WahaConnection, binding.connection_id)
        data = {
            col.key: copy.deepcopy(getattr(old, col.key))
            for col in WahaConnection.__table__.columns
        }
        data.update(
            id=foreign_connection,
            account_id=uid(99),
            instance_id="synthetic:other-instance",
            session_id="synthetic:other-session",
        )
        db.add(WahaConnection(**data))
        db.flush()
        db.add(
            ConversationRow(
                id=foreign_conversation, account_id=uid(99), context_version=1, allowlisted=True
            )
        )
        db.flush()
        db.add(
            WahaChat(
                id=foreign_chat,
                connection_id=foreign_connection,
                provider_chat_id="synthetic:other@lid",
                conversation_id=foreign_conversation,
            )
        )
        db.flush()
        old_permission = db.get(WahaSendPermission, binding.connection_id)
        db.add(
            WahaSendPermission(
                connection_id=foreign_connection,
                version=old_permission.version,
                enabled=True,
                chat_ids=[foreign_chat],
                expires_at=old_permission.expires_at,
            )
        )
        permission_version = old_permission.version
        control_version = data["control_version"]

    def login(name):
        r = client.post(
            "/api/v1/auth/login", json={"username": name, "password": "demo-only-change-me"}
        )
        assert r.status_code == 200
        return {"X-CSRF-Token": r.json()["data"]["csrf_token"]}

    other_headers = login("other")
    base = f"/api/v1/connectors/{foreign_connection}/sending"
    created = client.post(
        base + "/drafts",
        json={
            "expected_control_version": control_version,
            "expected_permission_version": permission_version,
            "chat_id": foreign_chat,
            "expected_context_version": 1,
            "mode": "manual",
            "payload": {"kind": "text", "text": "Synthetic private reply of the other account"},
        },
        headers={**other_headers, "Idempotency-Key": f"c-action:{action['id']}"},
    )
    assert created.status_code == 201, created.text
    foreign = created.json()["data"]
    approved = client.post(
        base + f"/actions/{foreign['id']}/approve",
        json={"expected_revision": foreign["revision"]},
        headers=other_headers,
    )
    assert approved.status_code == 200, approved.text
    own_headers = login("merchant")
    s = (client, factory, own_headers, binding, s[4])
    response = send(s, action)
    assert response.status_code == 202, response.text
    if operation == "lookup":
        assert response.json()["data"]["send_action_id"] != foreign["id"], response.text
    else:
        cancelled = client.post(
            f"/api/v1/actions/{action['id']}/cancel",
            json={
                "expected_version": action["bound_work_order_version"],
                "expected_context_version": action["bound_context_version"],
                "expected_action_revision": action["revision"],
                "snapshot_hash": action["snapshot_hash"],
                "reason": "Synthetic merchant cancellation",
            },
            headers={**own_headers, "Idempotency-Key": str(uuid4())},
        )
        assert cancelled.status_code == 200, cancelled.text
        with factory() as db:
            rows = list(db.scalars(select(WahaSendAction)))
            own = next(r for r in rows if r.connection_id == binding.connection_id)
            assert (db.get(WahaSendAction, foreign["id"]).state, own.state) == (
                "queued",
                "cancelled",
            )


@pytest.mark.parametrize("operation", ["defer", "requirement"])
def test_paused_conversation_cannot_store_new_sourced_content(signed_in, operation):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=8)).json()["data"]
    with factory.begin() as db:
        db.get(ConversationRow, uid(2)).allowlisted = False
    result = (
        defer(client, headers, order)
        if operation == "defer"
        else requirement(
            client,
            headers,
            order,
            kind="material",
            text="Synthetic newly stored private requirement",
            owner="customer",
        )
    )
    assert result.status_code == 403, result.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("address", "Synthetic venue"),
        ("schedule", {"kind": "date_only", "date": "2027-01-20", "timezone": "Asia/Hong_Kong"}),
        ("schedule", future(days=130)),
        ("quantity", 2),
        ("specification", "Synthetic detail"),
        ("deadline", {"kind": "date_only", "date": "2027-01-20", "timezone": "Asia/Hong_Kong"}),
    ],
)
def test_valid_non_timed_changes_are_readable(signed_in, field, value):
    client, factory, _, headers = signed_in
    order = create(client, headers).json()["data"]
    propose(factory, order["id"], field, value)
    with type(client)(client.app, raise_server_exceptions=False) as http:
        http.cookies.update(client.cookies)
        response = http.get(f"/api/v1/work-orders/{order['id']}/changes")
    assert response.status_code == 200, response.text


def test_invalid_calendar_date_has_validation_error(signed_in):
    client, _, _, _ = signed_in
    with type(client)(client.app, raise_server_exceptions=False) as http:
        http.cookies.update(client.cookies)
        response = http.get("/api/v1/daily-summary?date=2026-02-31")
    assert response.status_code == 422, response.text


def test_one_action_page_does_not_materialize_the_orders_entire_history(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers).json()["data"]
    with factory.begin() as db:
        original = db.scalar(select(ActionRow).where(ActionRow.work_order_id == order["id"]))
        for i in range(200):
            aid = str(uuid4())
            data = {**copy.deepcopy(original.data), "id": aid, "state": "cancelled"}
            db.add(
                ActionRow(
                    id=aid,
                    account_id=original.account_id,
                    work_order_id=order["id"],
                    conversation_id=original.conversation_id,
                    trigger=f"open_items:synthetic:{i}:missing_address",
                    active_key=None,
                    reason="superseded",
                    created_at=datetime.now(UTC),
                    data=data,
                )
            )
    loaded = []

    def observed(target, _):
        loaded.append(target.id)

    event.listen(ActionRow, "load", observed)
    try:
        r = client.get("/api/v1/actions", params={"work_order_id": order["id"], "limit": 1})
        assert r.status_code == 200, r.text
    finally:
        event.remove(ActionRow, "load", observed)
    assert len(loaded) <= 2, f"A single-item page materialized {len(loaded)} actions from 201 total"


def test_existing_gateway_key_is_not_taken_over_on_same_connection(setup):
    s = setup
    client, factory, headers, binding, _ = s
    _, action = approved_question(s)
    with factory() as db:
        connection = db.get(WahaConnection, binding.connection_id)
        chat = db.scalar(select(WahaChat).where(WahaChat.connection_id == connection.id))
        permission = db.get(WahaSendPermission, connection.id)
        context = db.get(ConversationRow, chat.conversation_id).context_version
        body = {
            "chat_id": chat.id,
            "expected_context_version": context,
            "mode": "manual",
            "payload": {"kind": "text", "text": "Synthetic independent draft"},
            "expected_control_version": connection.control_version,
            "expected_permission_version": permission.version,
        }
    reserved = client.post(
        f"/api/v1/connectors/{binding.connection_id}/sending/drafts",
        json=body,
        headers={**headers, "Idempotency-Key": f"c-action:{action['id']}"},
    )
    assert reserved.status_code == 201, reserved.text
    response = send(s, action)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SEND_REQUEST_KEY_TAKEN"
    with factory() as db:
        assert db.get(ActionRow, action["id"]).send_action_id is None
        assert db.get(WahaSendAction, reserved.json()["data"]["id"]).state == "draft"


@pytest.mark.parametrize("operation", ["edit", "requirement_done"])
def test_paused_edits_have_no_order_task_audit_or_receipt_side_effects(setup, operation):
    from sqlalchemy import func

    from gigmate.db import AuditRow, CommandResult, TaskRow, WorkOrderRow

    s = setup
    client, factory, headers, _, _ = s
    order, action = approved_question(s)
    if operation == "requirement_done":
        # use a replay conversation with a known incoming source for this branch
        order = create(client, headers).json()["data"]
        order = requirement(
            client, headers, order, kind="material", text="Synthetic", owner="customer"
        ).json()["data"]
    with factory.begin() as db:
        db.get(ConversationRow, order["conversation_ids"][0]).allowlisted = False
        before = [
            db.scalar(select(func.count()).select_from(model))
            for model in (TaskRow, AuditRow, CommandResult)
        ]
    if operation == "edit":
        # restore a pending draft without changing its immutable bound version
        with factory.begin() as db:
            row = db.get(ActionRow, action["id"])
            row.data = {
                **row.data,
                "state": "pending_approval",
                "approved_by": None,
                "approved_at": None,
            }
        response = client.post(
            f"/api/v1/actions/{action['id']}/edit",
            json={
                "body": "New synthetic private text",
                "expected_action_revision": action["revision"],
                "snapshot_hash": action["snapshot_hash"],
            },
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
    else:
        item = order["requirements"][0]
        response = client.post(
            f"/api/v1/work-orders/{order['id']}/requirements/{item['id']}",
            json={"status": "done", "expected_version": order["version"]},
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
    assert response.status_code == 403, response.text
    with factory() as db:
        assert db.get(WorkOrderRow, order["id"]).data["version"] == order["version"]
        assert [
            db.scalar(select(func.count()).select_from(model))
            for model in (TaskRow, AuditRow, CommandResult)
        ] == before


@pytest.mark.parametrize("day", ["2026-13-01", "2027-02-29", "2026-00-10", "2026-02-31"])
def test_daily_summary_rejects_nonexistent_dates(signed_in, day):
    response = signed_in[0].get("/api/v1/daily-summary", params={"date": day})
    assert response.status_code == 422


def test_daily_summary_accepts_leap_day(signed_in):
    assert signed_in[0].get("/api/v1/daily-summary?date=2028-02-29").status_code == 200


def test_legacy_cached_send_id_is_never_returned_as_a_trusted_link(setup):
    from gigmate.db import CommandResult

    s = setup
    _, factory, _, _, _ = s
    _, action = approved_question(s)
    key = str(uuid4())
    first = send(s, action, key=key)
    assert first.status_code == 202
    with factory.begin() as db:
        db.get(ActionRow, action["id"]).send_action_id = None
        cache = db.scalar(
            select(CommandResult).where(
                CommandResult.scope == f"send:{action['id']}", CommandResult.key == key
            )
        )
        cache.data = {**cache.data, "send_action_id": str(uuid4())}
    again = send(s, action, key=key)
    assert again.status_code == 202, again.text
    assert again.json()["data"]["state"] == "result_unknown"
    assert again.json()["data"]["send_action_id"] is None
    with factory() as db:
        assert len(list(db.scalars(select(WahaSendAction)))) == 1


def test_link_revalidates_the_immutable_body_before_disclosing_a_receipt(setup):
    s = setup
    client, factory, _, _, _ = s
    _, action = approved_question(s)
    sent = send(s, action).json()["data"]
    with factory.begin() as db:
        gateway = db.get(WahaSendAction, sent["send_action_id"])
        gateway.command = {
            **gateway.command,
            "payload": {"kind": "text", "text": "Synthetic different message"},
        }
    shown = client.get(f"/api/v1/actions/{action['id']}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["data"]["state"] == "result_unknown"
    assert shown.json()["data"]["send_action_id"] is None
