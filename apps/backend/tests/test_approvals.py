"""Role C P0: send_text drafts are generated, approved or rejected locally, never sent here."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from gigmate.approvals import draft_for_change, snapshot_hash
from gigmate.config import ROOT
from gigmate.db import (
    ActionRow,
    AuditRow,
    CalendarRow,
    ChangeRow,
    ConversationRow,
    Job,
    WorkOrderRow,
)
from gigmate.messaging import fixture, ingest
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


def test_other_account_cannot_see_or_approve(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    with factory.begin() as db:
        row = db.get(ActionRow, action["id"])
        row.account_id = uid(99)
    assert client.get(f"/api/v1/actions/{action['id']}").status_code == 404
    assert post(client, headers, action, "approve").status_code == 404
    assert pending(client) == []


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


def expire(factory, action):
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    with factory.begin() as db:
        row = db.get(ActionRow, action["id"])
        data = {**row.data, "expires_at": past}
        data["snapshot_hash"] = snapshot_hash(data)
        row.data = data


def reissue(client, headers, action, context_version):
    return client.post(
        f"/api/v1/actions/{action['id']}/reissue",
        json={"expected_context_version": context_version},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )


def detail(client, action):
    return client.get(f"/api/v1/actions/{action['id']}").json()["data"]


def test_unclear_message_keeps_question_for_the_merchant(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    custom_event(client, headers, thanks_event())
    run_once(factory)
    # Not understanding "谢谢" is not proof the question is still open: no automatic re-ask.
    assert pending(client) == []
    old = detail(client, action)
    assert (old["state"], old["closed_reason"], old["reissuable"]) == (
        "cancelled",
        "superseded",
        True,
    )
    assert post(client, headers, action, "approve").status_code == 409
    # The merchant decides to ask again, against the newest context.
    stale = reissue(client, headers, action, action["bound_context_version"])
    assert stale.status_code == 409
    again = reissue(client, headers, action, action["bound_context_version"] + 1)
    assert again.status_code == 201, again.text
    fresh = again.json()["data"]
    assert fresh["body"] == action["body"]
    assert fresh["bound_context_version"] == action["bound_context_version"] + 1
    assert post(client, headers, fresh, "approve").status_code == 202
    # The superseded one is no longer the newest, so it cannot be reissued twice.
    assert reissue(client, headers, action, fresh["bound_context_version"]).status_code == 409


def test_own_api_send_echo_never_creates_a_new_question(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    echo = thanks_event()
    echo.update(connector="waha", source="api", direction="outgoing")
    echo["payload"]["text"] = action["body"]
    with factory.begin() as db:
        from gigmate.db import Account

        ingest(db, db.get(Account, uid(1)), echo, trusted_waha=True)
    assert run_once(factory)
    with factory() as db:
        job = db.scalar(select(Job).where(Job.event_id == echo["event_id"]))
        assert (job.state, job.error_code) == ("completed", "OWN_SEND_ECHO")
    # The echo still advances the context and supersedes the old draft ...
    assert detail(client, action)["closed_reason"] == "superseded"
    # ... but it is not customer input, so nothing is re-asked automatically.
    assert pending(client) == []


def test_reading_expired_drafts_never_writes(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    expire(factory, action)
    assert detail(client, action)["state"] == "expired"
    assert pending(client) == []
    with factory() as db:
        # GET only computes the view; the stored row is changed by commands.
        assert db.get(ActionRow, action["id"]).data["state"] == "pending_approval"
    stale = detail(client, action)
    response = post(client, headers, stale, "approve")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_STALE"
    with factory() as db:
        assert db.get(ActionRow, action["id"]).data["approved_by"] is None


def test_expired_question_can_be_asked_again_after_a_new_message(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    expire(factory, action)
    custom_event(client, headers, thanks_event())
    run_once(factory)
    assert detail(client, action)["reissuable"] is True
    again = reissue(client, headers, action, action["bound_context_version"] + 1)
    assert again.status_code == 201, again.text


def test_repeated_expiry_rounds_can_each_be_reissued(signed_in):
    """Expire → reissue → expire again (no new message) → reissue again (PR #22 review)."""
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    context = action["bound_context_version"]
    expire(factory, action)
    first = reissue(client, headers, action, context)
    assert first.status_code == 201, first.text
    second_round = first.json()["data"]
    expire(factory, second_round)
    assert detail(client, second_round)["reissuable"] is True
    key = str(uuid4())

    def again(body):
        return client.post(
            f"/api/v1/actions/{second_round['id']}/reissue",
            json=body,
            headers={**headers, "Idempotency-Key": key},
        )

    second = again({"expected_context_version": context})
    assert second.status_code == 201, second.text
    third_round = second.json()["data"]
    assert third_round["id"] != second_round["id"]
    assert third_round["body"] == action["body"]
    # Same key, same request: the same result, no extra draft.
    replay = again({"expected_context_version": context})
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == third_round["id"]
    # Same key reused for a different request is refused.
    changed = again({"expected_context_version": context + 1})
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    # Older rounds are no longer the newest question and cannot come back.
    assert reissue(client, headers, second_round, context).status_code == 409
    assert reissue(client, headers, action, context).status_code == 409
    assert [item["id"] for item in pending(client)] == [third_round["id"]]
    assert post(client, headers, third_round, "approve").status_code == 202


def test_expired_question_does_not_return_after_its_source_was_edited(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    expire(factory, action)
    custom_event(client, headers, fixture("message-edited"))
    run_once(factory)
    old = detail(client, action)
    assert (old["state"], old["closed_reason"], old["reissuable"]) == (
        "expired",
        "source_changed",
        False,
    )
    assert reissue(client, headers, action, action["bound_context_version"] + 1).status_code == 409
    assert all(item["body"] != action["body"] for item in pending(client))


def test_question_is_outdated_once_the_time_is_free(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    # The other appointment moved away, so the proposed time no longer collides.
    with factory.begin() as db:
        other = db.scalar(select(CalendarRow).where(CalendarRow.work_order_id == uid(13)))
        other.data = {
            **other.data,
            "schedule": {
                **other.data["schedule"],
                "start_at": "2030-01-01T01:00:00Z",
                "end_at": "2030-01-01T02:00:00Z",
            },
        }
    response = post(client, headers, action, "approve")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_STALE"


def test_approved_but_unsent_reply_needs_new_approval_after_new_message(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    assert post(client, headers, action, "approve").status_code == 202
    custom_event(client, headers, thanks_event())
    run_once(factory)
    old = detail(client, action)
    assert (old["state"], old["closed_reason"]) == ("cancelled", "superseded")
    assert pending(client) == []


def test_editing_a_draft_needs_a_fresh_approval(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    edited = client.post(
        f"/api/v1/actions/{action['id']}/edit",
        json={
            "body": "收到！这个时间我有安排，星期四四点半可以吗？",
            "expected_action_revision": action["revision"],
            "snapshot_hash": action["snapshot_hash"],
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert edited.status_code == 200, edited.text
    new = edited.json()["data"]
    assert new["revision"] == action["revision"] + 1
    assert new["body"] == "收到！这个时间我有安排，星期四四点半可以吗？"
    assert new["snapshot_hash"] != action["snapshot_hash"]
    # The old approval no longer matches the edited text.
    assert post(client, headers, action, "approve").status_code == 409
    assert post(client, headers, new, "approve").status_code == 202
    late = client.post(
        f"/api/v1/actions/{action['id']}/edit",
        json={
            "body": "x",
            "expected_action_revision": new["revision"],
            "snapshot_hash": new["snapshot_hash"],
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert late.status_code == 409


def test_action_pages_are_read_in_batches_without_gaps_or_writes(signed_in):
    client, factory, _, headers = signed_in
    action = conflict_draft(client, factory, headers)
    # Many synthetic historical drafts for the same order (closed), plus the live one.
    with factory.begin() as db:
        row = db.get(ActionRow, action["id"])
        for number in range(120):
            data = {**row.data, "id": str(uuid4()), "state": "cancelled"}
            db.add(
                ActionRow(
                    id=data["id"],
                    account_id=row.account_id,
                    work_order_id=row.work_order_id,
                    conversation_id=row.conversation_id,
                    trigger=f"schedule_conflict:history-{number}",
                    active_key=None,
                    reason="superseded",
                    created_at=row.created_at,
                    data=data,
                )
            )
    seen, cursor = [], None
    while True:
        params = {"limit": 25, **({"cursor": cursor} if cursor else {})}
        body = client.get("/api/v1/actions", params=params).json()
        seen += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 121
    assert seen == sorted(seen)
    pending = client.get("/api/v1/actions", params={"state": "pending_approval", "limit": 5}).json()
    assert [item["id"] for item in pending["items"]] == [action["id"]]
    assert pending["next_cursor"] is None
    expire(factory, action)
    expired = client.get("/api/v1/actions", params={"state": "expired"}).json()["items"]
    assert [item["id"] for item in expired] == [action["id"]]
    with factory() as db:
        assert db.get(ActionRow, action["id"]).data["state"] == "pending_approval"
    import base64

    bad = base64.urlsafe_b64encode(b"not-an-id").decode()
    assert client.get("/api/v1/actions", params={"cursor": bad}).status_code == 422
