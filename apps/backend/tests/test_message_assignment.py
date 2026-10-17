"""Role C: the merchant files a message the system could not assign (方案 §4.2, 契约 §1)."""

from uuid import uuid4

from sqlalchemy import select

from gigmate.db import ChangeRow, ConversationRow, Job
from gigmate.seed import uid
from gigmate.worker import run_once

CONVERSATION = uid(2)
SEED_ORDER = uid(3)


def second_order(client, headers):
    response = client.post(
        "/api/v1/work-orders",
        json={
            "conversation_id": CONVERSATION,
            "summary": "陈小姐家庭合照",
            "confirm_additional_order": True,
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def unassigned_message(client, factory, headers):
    response = client.post(
        "/api/v1/replay",
        json={"scenario": "available"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202
    assert run_once(factory)
    with factory() as db:
        job = db.scalar(select(Job).where(Job.error_code == "ASSIGNMENT_NEEDS_REVIEW"))
        context = db.get(ConversationRow, CONVERSATION).context_version
        assert db.scalar(select(ChangeRow)) is None
        return job.id, context


def assign(client, headers, job_id, context, **body):
    return client.post(
        f"/api/v1/review-items/{job_id}/assign",
        json={"expected_context_version": context, **body},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )


def test_assigning_a_message_reprocesses_it_for_that_order_only(signed_in):
    client, factory, _, headers = signed_in
    order = second_order(client, headers)
    job_id, context = unassigned_message(client, factory, headers)
    response = assign(client, headers, job_id, context, action="assign", work_order_id=order["id"])
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "pending"
    assert run_once(factory)
    with factory() as db:
        [change] = db.scalars(select(ChangeRow))
        # A proposal for the chosen order, still waiting for the merchant.
        assert change.work_order_id == order["id"]
        assert change.data["status"] == "proposed"
        assert db.get(Job, job_id).error_code is None
    again = assign(client, headers, job_id, context, action="dismiss")
    assert again.status_code == 409


def test_dismissing_a_message_closes_the_review_item(signed_in):
    client, factory, _, headers = signed_in
    second_order(client, headers)
    job_id, context = unassigned_message(client, factory, headers)
    response = assign(client, headers, job_id, context, action="dismiss")
    assert response.status_code == 200, response.text
    with factory() as db:
        job = db.get(Job, job_id)
        assert (job.state, job.error_code) == ("completed", "DISMISSED_BY_MERCHANT")
    assert not run_once(factory)


def test_only_open_orders_of_this_conversation_and_the_newest_message(signed_in):
    client, factory, _, headers = signed_in
    order = second_order(client, headers)
    job_id, context = unassigned_message(client, factory, headers)
    stale = assign(client, headers, job_id, context - 1, action="assign", work_order_id=order["id"])
    assert stale.status_code == 409
    foreign = assign(client, headers, job_id, context, action="assign", work_order_id=str(uuid4()))
    assert foreign.status_code == 404
    client.post(
        f"/api/v1/work-orders/{order['id']}/status",
        json={"status": "cancelled", "expected_version": order["version"]},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    closed = assign(client, headers, job_id, context, action="assign", work_order_id=order["id"])
    assert closed.status_code == 409
    invalid = assign(client, headers, job_id, context, action="assign")
    assert invalid.status_code == 422
    unknown = assign(client, headers, str(uuid4()), context, action="dismiss")
    assert unknown.status_code == 404
