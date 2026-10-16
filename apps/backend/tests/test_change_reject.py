"""Role C: the merchant rejects a proposal; history is kept and dependent drafts are withdrawn."""

from uuid import uuid4

from sqlalchemy import select

from gigmate.db import ActionRow, AuditRow
from gigmate.seed import uid
from gigmate.worker import run_once

ORDER = uid(3)


def conflicting_proposal(client, factory, headers):
    response = client.post(
        "/api/v1/replay",
        json={"scenario": "reschedule"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202
    assert run_once(factory)
    [change] = client.get(f"/api/v1/work-orders/{ORDER}/changes").json()["items"]
    order = client.get(f"/api/v1/work-orders/{ORDER}").json()["data"]
    return order, change


def reject(client, headers, order, change, reason="客人只是问问，不改期", version=None, key=None):
    return client.post(
        f"/api/v1/work-orders/{order['id']}/changes/{change['id']}/reject",
        json={"expected_version": version or order["version"], "reason": reason},
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def test_rejecting_a_proposal_keeps_history_and_withdraws_its_question(signed_in):
    client, factory, _, headers = signed_in
    order, change = conflicting_proposal(client, factory, headers)
    with factory() as db:
        [draft] = db.scalars(select(ActionRow).where(ActionRow.work_order_id == ORDER))
        assert draft.data["state"] == "pending_approval"
    response = reject(client, headers, order, change)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["version"] == order["version"] + 1
    assert change["id"] not in data["pending_change_ids"]
    # The order keeps its current confirmed time.
    assert data["fields"]["schedule"] == order["fields"]["schedule"]
    [stored] = client.get(f"/api/v1/work-orders/{ORDER}/changes").json()["items"]
    assert stored["status"] == "rejected"
    assert stored["rejection_reason"] == "客人只是问问，不改期"
    with factory() as db:
        draft = db.get(ActionRow, draft.id)
        assert (draft.data["state"], draft.reason) == ("cancelled", "proposal_rejected")
        operations = [row.data["operation"] for row in db.scalars(select(AuditRow))]
    assert "reject_change" in operations


def test_rejected_proposal_cannot_be_confirmed_or_rejected_again(signed_in):
    client, factory, _, headers = signed_in
    order, change = conflicting_proposal(client, factory, headers)
    data = reject(client, headers, order, change).json()["data"]
    again = reject(client, headers, data, change)
    assert again.status_code == 409
    confirmed = client.post(
        f"/api/v1/work-orders/{ORDER}/changes/{change['id']}/confirm",
        json={
            "expected_version": data["version"],
            "expected_context_version": change["context_version"],
            "apply_calendar_update": True,
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert confirmed.status_code == 409


def test_reject_needs_a_reason_and_the_current_version(signed_in):
    client, factory, _, headers = signed_in
    order, change = conflicting_proposal(client, factory, headers)
    assert reject(client, headers, order, change, reason="   ").status_code == 422
    stale = reject(client, headers, order, change, version=order["version"] + 1)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    key = str(uuid4())
    first = reject(client, headers, order, change, key=key)
    second = reject(client, headers, order, change, key=key)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    missing = client.post(
        f"/api/v1/work-orders/{ORDER}/changes/{uuid4()}/reject",
        json={"expected_version": 1, "reason": "x"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert missing.status_code == 404
