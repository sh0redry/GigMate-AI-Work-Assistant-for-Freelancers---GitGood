"""Business approval → WhatsApp sending gateway (方案 §4.5、§6.2、§7; Issue #29 §1).

Synthetic chat and provider only; nothing reaches a real WhatsApp account.
"""

from uuid import uuid4

from sqlalchemy import func, select
from test_waha_ingress import post, raw
from test_waha_send import Provider, execute, ingress, setup  # noqa: F401

from gigmate.db import (
    ActionRow,
    ConversationRow,
    MessageRow,
    WahaChat,
    WahaConnection,
    WahaSendAction,
    WahaSendPermission,
)


def conversation_message(s):
    """An incoming customer message in the linked WhatsApp chat."""
    assert post(s_ingress(s), raw()).status_code in {200, 202}
    with s[1]() as db:
        chat = db.scalar(select(WahaChat))
        message = db.scalar(
            select(MessageRow).where(MessageRow.conversation_id == chat.conversation_id)
        )
        return chat.conversation_id, {
            "message_id": message.id,
            "message_revision": message.revision,
        }


def s_ingress(s):
    client, factory, headers, binding, _ = s
    return client, factory, None, headers, binding, None


def approved_question(s):
    """A merchant-created order missing its time → one open-item draft, approved."""
    client, factory, headers, _, _ = s
    conversation_id, source = conversation_message(s)
    created = client.post(
        "/api/v1/work-orders",
        json={
            "conversation_id": conversation_id,
            "summary": "陈小姐证件照拍摄",
            "address": "旺角",
            "address_sources": [source],
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert created.status_code == 201, created.text
    order = created.json()["data"]
    [draft] = [
        item
        for item in client.get("/api/v1/actions", params={"state": "pending_approval"}).json()[
            "items"
        ]
        if item["work_order_id"] == order["id"]
    ]
    approved = client.post(
        f"/api/v1/actions/{draft['id']}/approve",
        json={
            "expected_version": draft["bound_work_order_version"],
            "expected_context_version": draft["bound_context_version"],
            "expected_action_revision": draft["revision"],
            "snapshot_hash": draft["snapshot_hash"],
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert approved.status_code == 202, approved.text
    return order, approved.json()["data"]


def send_command(s, action, **override):
    with s[1]() as db:
        row = db.get(WahaConnection, s[3].connection_id)
        permission = db.get(WahaSendPermission, row.id)
        body = {
            "connection_id": row.id,
            "expected_control_version": row.control_version,
            "expected_permission_version": permission.version,
            "expected_action_revision": action["revision"],
            "snapshot_hash": action["snapshot_hash"],
        }
    return {**body, **override}


def send(s, action, key=None, **override):
    return s[0].post(
        f"/api/v1/actions/{action['id']}/send",
        json=send_command(s, action, **override),
        headers={**s[2], "Idempotency-Key": key or str(uuid4())},
    )


def detail(s, action):
    return s[0].get(f"/api/v1/actions/{action['id']}").json()["data"]


def test_approved_reply_is_sent_once_and_its_outcome_shows_on_the_business_action(setup):  # noqa: F811
    s = setup
    order, action = approved_question(s)
    response = send(s, action)
    assert response.status_code == 202, response.text
    queued = response.json()["data"]
    assert queued["state"] == "executing"
    assert queued["send_state"] == "queued"
    with s[1]() as db:
        gateway = db.get(WahaSendAction, queued["send_action_id"])
        assert gateway.command["payload"]["kind"] == "text"
        assert gateway.command["payload"]["text"] == action["body"]
        assert gateway.command["work_order_id"] == order["id"]
        assert gateway.command["expected_work_order_version"] == action["bound_work_order_version"]
    # Sending again (lost response, double click, new key) never creates a second send.
    again = send(s, action)
    assert again.status_code == 202
    assert again.json()["data"]["send_action_id"] == queued["send_action_id"]
    provider = Provider()
    assert execute(s, provider)
    assert not execute(s, provider)
    assert len(provider.calls) == 1
    assert provider.calls[0][1]["text"] == action["body"]
    shown = detail(s, action)
    assert shown["state"] == "succeeded"
    assert shown["delivery_status"] == "accepted"
    assert shown["provider_message_id"]
    with s[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSendAction)) == 1


def test_only_approved_current_replies_can_be_sent(setup):  # noqa: F811
    s = setup
    client, factory, headers, _, _ = s
    order, action = approved_question(s)
    wrong = send(s, action, snapshot_hash="sha256:" + "0" * 64)
    assert wrong.status_code == 409
    # The work order changed after approval: the reply is outdated.
    with factory.begin() as db:
        from gigmate.db import WorkOrderRow

        row = db.get(WorkOrderRow, order["id"])
        row.data = {**row.data, "version": row.data["version"] + 1}
    stale = send(s, action)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WahaSendAction)) == 0
        assert db.get(ActionRow, action["id"]).data["state"] == "approved"


def test_send_needs_separate_send_permission_and_consent(setup):  # noqa: F811
    s = setup
    client, factory, headers, _, _ = s
    _, action = approved_question(s)
    with factory.begin() as db:
        permission = db.get(WahaSendPermission, s[3].connection_id)
        permission.enabled = False
    refused = send(s, action)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "SEND_NOT_AUTHORIZED"
    with factory.begin() as db:
        permission = db.get(WahaSendPermission, s[3].connection_id)
        permission.enabled = True
        chat = db.scalar(select(WahaChat))
        db.get(ConversationRow, chat.conversation_id).allowlisted = False
    paused = send(s, action)
    assert paused.status_code == 403
    assert paused.json()["error"]["code"] == "CONSENT_REVOKED"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WahaSendAction)) == 0


def test_new_customer_message_after_hand_off_stops_the_queued_send(setup):  # noqa: F811
    s = setup
    _, action = approved_question(s)
    assert send(s, action).status_code == 202
    # The customer writes again before dispatch: the queued reply is outdated.
    event = raw(event_id="synthetic:event-2")
    event["payload"] = {**event["payload"], "id": "synthetic:second", "body": "Another"}
    assert post(s_ingress(s), event).status_code in {200, 202}
    provider = Provider()
    execute(s, provider)
    assert provider.calls == []
    assert detail(s, action)["state"] == "cancelled"


def test_unknown_outcome_is_shown_and_never_resent(setup):  # noqa: F811
    s = setup
    _, action = approved_question(s)
    assert send(s, action).status_code == 202
    provider = Provider()
    provider.error = TimeoutError("synthetic timeout after submission")
    execute(s, provider)
    shown = detail(s, action)
    assert shown["state"] in {"result_unknown", "failed"}
    if shown["state"] == "result_unknown":
        assert shown["delivery_status"] == "unknown"
    provider.error = None
    execute(s, provider)
    assert len(provider.calls) == 1


def test_merchant_can_withdraw_a_handed_off_reply_until_dispatch(setup):  # noqa: F811
    s = setup
    _, action = approved_question(s)
    assert send(s, action).status_code == 202
    body = {
        "expected_version": action["bound_work_order_version"],
        "expected_context_version": action["bound_context_version"],
        "expected_action_revision": action["revision"],
        "snapshot_hash": action["snapshot_hash"],
        "reason": "改用电话联系",
    }
    cancelled = s[0].post(
        f"/api/v1/actions/{action['id']}/cancel",
        json=body,
        headers={**s[2], "Idempotency-Key": str(uuid4())},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["state"] == "cancelled"
    provider = Provider()
    execute(s, provider)
    assert provider.calls == []


def test_dispatched_reply_cannot_be_withdrawn(setup):  # noqa: F811
    s = setup
    _, action = approved_question(s)
    assert send(s, action).status_code == 202
    execute(s, Provider())
    body = {
        "expected_version": action["bound_work_order_version"],
        "expected_context_version": action["bound_context_version"],
        "expected_action_revision": action["revision"],
        "snapshot_hash": action["snapshot_hash"],
        "reason": "太迟了",
    }
    late = s[0].post(
        f"/api/v1/actions/{action['id']}/cancel",
        json=body,
        headers={**s[2], "Idempotency-Key": str(uuid4())},
    )
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "SEND_ALREADY_DISPATCHED"
