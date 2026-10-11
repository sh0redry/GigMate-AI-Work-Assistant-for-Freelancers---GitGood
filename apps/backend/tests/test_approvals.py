"""Role C P0: send_text drafts are generated, approved or rejected locally, never sent here."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from gigmate.approvals import draft_for_change, snapshot_hash
from gigmate.config import ROOT
from gigmate.db import ActionRow, AuditRow, ChangeRow, ConversationRow, WorkOrderRow
from gigmate.messaging import fixture
from gigmate.seed import uid
from gigmate.worker import run_once

ORDER = uid(3)


def replay(client, headers, scenario):
    response = client.post(
        "/api/v1/replay",
        json={"scenario": scenario},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text


def pending(client):
    response = client.get("/api/v1/actions", params={"state": "pending_approval"})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def conflict_draft(client, factory, headers):
    replay(client, headers, "reschedule")
    assert run_once(factory)
    items = pending(client)
    assert len(items) == 1
    return items[0]


def command(action, **override):
    body = {
        "expected_version": action["bound_work_order_version"],
        "expected_context_version": action["bound_context_version"],
        "expected_action_revision": action["revision"],
        "snapshot_hash": action["snapshot_hash"],
    }
    return {**body, **override}


def post(client, headers, action, verb, body=None, key=None):
    return client.post(
        f"/api/v1/actions/{action['id']}/{verb}",
        json=body or command(action),
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def test_hash_matches_contract_examples():
    for name in ["action-pending", "action-unknown"]:
        example = json.loads(
            (ROOT / "contracts/examples" / f"{name}.json").read_text(encoding="utf-8")
        )
        assert snapshot_hash(example) == example["snapshot_hash"]


def test_conflicting_reschedule_creates_one_pending_draft(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    assert action["kind"] == "send_text"
    assert action["work_order_id"] == ORDER
    assert action["trigger"] == "schedule_conflict"
    assert action["delivery_status"] == "not_submitted"
    assert "已有其他安排" in action["body"]
    assert action["snapshot_hash"] == snapshot_hash(action)
    # A retried worker step for the same change never duplicates the draft.
    with factory.begin() as db:
        change = db.scalar(select(ChangeRow).where(ChangeRow.work_order_id == ORDER))
        order = db.get(WorkOrderRow, ORDER)
        conversation = db.get(ConversationRow, change.conversation_id)
        assert draft_for_change(db, order.account_id, order, conversation, change.data) is None
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ActionRow)) == 1


def test_free_time_creates_no_draft(signed_in):
    client, factory, _, headers = signed_in
    replay(client, headers, "available")
    assert run_once(factory)
    assert pending(client) == []


def test_approve_is_exact_and_idempotent(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    key = str(uuid4())
    first = post(client, headers, action, "approve", key=key)
    assert first.status_code == 202, first.text
    approved = first.json()["data"]
    assert approved["state"] == "approved"
    assert approved["approved_by"] and approved["approved_at"]
    assert approved["delivery_status"] == "not_submitted"
    # Same key and body: recorded result, no second approval.
    again = post(client, headers, action, "approve", key=key)
    assert again.status_code == 202
    assert again.json()["data"] == approved
    # New key: the draft is no longer pending.
    other = post(client, headers, action, "approve")
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "APPROVAL_STALE"
    with factory() as db:
        operations = [row.data["operation"] for row in db.scalars(select(AuditRow))]
    assert operations.count("approve_action") == 1


def test_approve_rejects_wrong_snapshot_or_versions(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    wrong_hash = post(
        client, headers, action, "approve", command(action, snapshot_hash="sha256:" + "0" * 64)
    )
    assert wrong_hash.status_code == 409
    assert wrong_hash.json()["error"]["code"] == "APPROVAL_STALE"
    wrong_revision = post(
        client, headers, action, "approve", command(action, expected_action_revision=2)
    )
    assert wrong_revision.json()["error"]["code"] == "APPROVAL_STALE"
    wrong_context = post(
        client,
        headers,
        action,
        "approve",
        command(action, expected_context_version=action["bound_context_version"] + 1),
    )
    assert wrong_context.status_code == 409
    assert wrong_context.json()["error"]["code"] == "VERSION_CONFLICT"
    assert pending(client)[0]["state"] == "pending_approval"


def custom_event(client, headers, event):
    response = client.post(
        "/api/v1/replay/events",
        json=event,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text


def thanks_event():
    event = fixture("message-reschedule")
    event.update(
        event_id=str(uuid4()),
        provider_message_id="synthetic:thanks",
        occurred_at="2026-10-01T02:05:00Z",
        received_at="2026-10-01T02:05:01Z",
    )
    event["payload"] = {"message_id": str(uuid4()), "text": "谢谢"}
    return event


def test_unrelated_message_keeps_the_question(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    custom_event(client, headers, thanks_event())
    # Until the new message has been read, nothing can be approved.
    assert pending(client) == []
    assert post(client, headers, action, "approve").status_code == 409
    run_once(factory)
    [carried] = pending(client)
    # Same question, re-issued against the newer conversation context.
    assert carried["id"] != action["id"]
    assert carried["body"] == action["body"]
    assert carried["sources"] == action["sources"]
    assert carried["bound_context_version"] == action["bound_context_version"] + 1
    old = client.get(f"/api/v1/actions/{action['id']}").json()["data"]
    assert old["state"] == "cancelled"
    assert old["closed_reason"] == "superseded"
    # The old text can never be approved; the re-issued one can.
    assert post(client, headers, action, "approve").status_code == 409
    assert post(client, headers, carried, "approve").status_code == 202


def test_customer_offering_a_free_time_answers_the_question(signed_in):
    client, factory, _, headers = signed_in
    conflict_draft(client, factory, headers)
    replay(client, headers, "available")
    assert run_once(factory)
    assert pending(client) == []
    reasons = [item["closed_reason"] for item in client.get("/api/v1/actions").json()["items"]]
    # The same question is never re-asked once the new message answered it.
    assert reasons == ["answered"]


def test_editing_the_source_message_cancels_the_question(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    custom_event(client, headers, fixture("message-edited"))
    run_once(factory)
    assert pending(client) == []
    old = client.get(f"/api/v1/actions/{action['id']}").json()["data"]
    assert old["closed_reason"] == "source_changed"


def test_reject_is_local_even_when_processing_is_paused(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    with factory.begin() as db:
        db.get(ConversationRow, action["conversation_id"]).allowlisted = False
    blocked = post(client, headers, action, "approve")
    assert blocked.status_code == 403
    response = post(client, headers, action, "reject", {**command(action), "reason": "不用回复"})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["state"] == "cancelled"
    assert data["closed_reason"] == "rejected"
    assert data["closed_note"] == "不用回复"
    assert pending(client) == []


def test_cancel_after_approval_before_dispatch(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    assert post(client, headers, action, "approve").status_code == 202
    response = post(client, headers, action, "cancel", {**command(action), "reason": "改主意"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "cancelled"
    # Rejecting is only for drafts that were never approved.
    again = post(client, headers, action, "reject", {**command(action), "reason": "x"})
    assert again.status_code == 409


def test_expired_draft_cannot_be_approved(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    with factory.begin() as db:
        row = db.get(ActionRow, action["id"])
        data = {**row.data, "expires_at": past}
        data["snapshot_hash"] = snapshot_hash(data)
        row.data = data
    stale = client.get(f"/api/v1/actions/{action['id']}").json()["data"]
    assert stale["state"] == "expired"
    response = post(client, headers, stale, "approve")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_STALE"


def test_other_account_cannot_see_or_approve(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    with factory.begin() as db:
        row = db.get(ActionRow, action["id"])
        row.account_id = uid(99)
    assert client.get(f"/api/v1/actions/{action['id']}").status_code == 404
    assert post(client, headers, action, "approve").status_code == 404
    assert pending(client) == []


def test_approved_but_unsent_reply_is_reissued_after_new_message(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    assert post(client, headers, action, "approve").status_code == 202
    custom_event(client, headers, thanks_event())
    run_once(factory)
    # The merchant approved text for an older context, so it must be approved again.
    old = client.get(f"/api/v1/actions/{action['id']}").json()["data"]
    assert (old["state"], old["closed_reason"]) == ("cancelled", "superseded")
    [again] = pending(client)
    assert again["body"] == action["body"]


def test_expired_question_comes_back_with_next_message(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    with factory.begin() as db:
        row = db.get(ActionRow, action["id"])
        data = {**row.data, "expires_at": past}
        data["snapshot_hash"] = snapshot_hash(data)
        row.data = data
    assert pending(client) == []
    custom_event(client, headers, thanks_event())
    run_once(factory)
    [regenerated] = pending(client)
    assert regenerated["body"] == action["body"]


def test_one_unsent_draft_per_order(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    assert post(client, headers, action, "approve").status_code == 202
    with factory() as db:
        open_rows = [
            row
            for row in db.scalars(select(ActionRow))
            if row.data["state"] in {"pending_approval", "approved"}
        ]
    assert len(open_rows) == 1
    assert open_rows[0].active_key == ORDER
