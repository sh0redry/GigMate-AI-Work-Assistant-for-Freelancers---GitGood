"""Bounded agent drafts: text only, never authority (issue #29, B/C item 6).

The suite pins the constraints that make a draft safe to expose:

* there is no free-form question path — a draft comes from an already-gated
  proposal or from the merchant's own text, never from an arbitrary prompt;
* a draft grants no execution authority: consuming it returns text and marks it
  used, and no send, no confirmation and no work-order write happens;
* the rules bite: a daily ceiling, a TTL that reads as ``expired``, revocation
  and one-time consumption;
* a draft cannot outlive its bindings: a proposal from an older context version
  is refused instead of being reused.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from gigmate.db import (
    AgentDraftRow,
    ConversationOrder,
    ConversationRow,
    Proposal,
    WorkOrderRow,
)
from gigmate.seed import uid

ORDER = uid(3)


@pytest.fixture
def proposal(signed_in):
    """One gated extraction proposal with merchant-facing draft text."""

    client, factory, _engine, headers = signed_in
    with factory.begin() as db:
        order = db.get(WorkOrderRow, ORDER)
        if order is None:
            order = WorkOrderRow(
                id=ORDER,
                account_id=uid(1),
                data={"id": ORDER, "version": 3, "pending_change_ids": []},
            )
            db.add(order)
            db.flush()
        conversation = db.get(ConversationRow, uid(2))
        if conversation is None:
            conversation = ConversationRow(id=uid(2), account_id=uid(1), context_version=5)
            db.add(conversation)
            db.flush()
        link = db.get(ConversationOrder, (uid(2), ORDER))
        if link is None:
            db.add(ConversationOrder(conversation_id=uid(2), work_order_id=ORDER))
            db.flush()
        row = Proposal(
            id=str(uuid4()),
            account_id=uid(1),
            conversation_id=uid(2),
            event_id=str(uuid4()),
            work_order_id=ORDER,
            assignment="matched",
            context_version=conversation.context_version,
            base_work_order_version=order.data["version"],
            proposal={},
            changes=[],
            unresolved_questions=[],
            model_version="synthetic:fixed-stub-v1",
            prompt_version="1.3.0",
            draft_text="Hi! Could we move the visit to Thursday 3pm?",
            created_at=datetime.now(UTC),
        )
        db.add(row)
    return (client, factory, headers, row.id, ORDER)


def _create(ctx, body):
    client, _factory, headers, _proposal_id, order = ctx
    return client.post(f"/api/v1/work-orders/{order}/drafts", json=body, headers=headers)


def test_draft_from_a_gated_proposal_is_text_only(proposal):
    client, factory, headers, proposal_id, order = proposal
    response = _create(
        proposal, {"kind": "follow_up", "base_proposal_id": proposal_id, "note": "ping"}
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["text"] == "Hi! Could we move the visit to Thursday 3pm?"
    assert data["status"] == "proposed"
    assert data["execution_authority"] is False
    assert data["proposal_id"] == proposal_id
    assert data["expires_at"]

    # Idempotent for the same proposal: one draft, not two.
    again = _create(proposal, {"kind": "follow_up", "base_proposal_id": proposal_id})
    assert again.status_code == 201 and again.json()["data"]["id"] == data["id"]

    listed = client.get(f"/api/v1/work-orders/{order}/drafts", headers=headers).json()["items"]
    assert [item["id"] for item in listed] == [data["id"]]

    # Consuming returns text and marks it used; nothing is sent.
    consumed = client.post(f"/api/v1/drafts/{data['id']}/consume", headers=headers)
    assert consumed.status_code == 200
    assert consumed.json()["data"]["status"] == "consumed"
    assert consumed.json()["data"]["text"]
    assert client.post(f"/api/v1/drafts/{data['id']}/consume", headers=headers).status_code == 409

    with factory() as db:
        order_row = db.get(WorkOrderRow, order)
        assert order_row.data["pending_change_ids"] == []


def test_draft_can_be_revoked_and_then_refuses_consumption(proposal):
    client, _factory, headers, proposal_id, _order = proposal
    created = _create(proposal, {"kind": "polish", "base_proposal_id": proposal_id})
    draft_id = created.json()["data"]["id"]
    revoked = client.post(f"/api/v1/drafts/{draft_id}/revoke", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["data"]["status"] == "revoked"
    assert revoked.json()["data"]["revoked_at"]
    consume = client.post(f"/api/v1/drafts/{draft_id}/consume", headers=headers)
    assert consume.status_code == 409
    assert consume.json()["error"]["code"] == "AGENT_DRAFT_NOT_USABLE"


def test_expired_draft_is_never_usable(proposal):
    client, factory, headers, proposal_id, _order = proposal
    draft_id = _create(proposal, {"kind": "follow_up", "base_proposal_id": proposal_id}).json()[
        "data"
    ]["id"]
    with factory.begin() as db:
        row = db.get(AgentDraftRow, draft_id)
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    listed = client.get(
        f"/api/v1/work-orders/{_order_of(proposal)}/drafts", headers=headers
    ).json()["items"]
    assert listed[0]["status"] == "expired"
    consume = client.post(f"/api/v1/drafts/{draft_id}/consume", headers=headers)
    assert consume.status_code == 409


def _order_of(ctx):
    return ctx[4]


def test_daily_ceiling_stops_new_drafts(proposal, monkeypatch):
    client, _factory, headers, _proposal_id, order = proposal
    monkeypatch.setenv("GIGMATE_AGENT_DRAFT_DAILY_LIMIT", "2")
    first = client.post(
        f"/api/v1/work-orders/{order}/drafts",
        json={"kind": "polish", "text": "merchant wrote this"},
        headers=headers,
    )
    assert first.status_code == 201
    assert first.json()["data"]["text"] == "merchant wrote this"
    assert first.json()["data"]["proposal_id"] is None
    second = client.post(
        f"/api/v1/work-orders/{order}/drafts",
        json={"kind": "polish", "text": "second"},
        headers=headers,
    )
    assert second.status_code == 201
    third = client.post(
        f"/api/v1/work-orders/{order}/drafts",
        json={"kind": "polish", "text": "third"},
        headers=headers,
    )
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "AGENT_DRAFT_LIMIT_REACHED"


def test_quiet_hours_refuse_creation(proposal, monkeypatch):
    client, _factory, headers, proposal_id, order = proposal
    # 00-24 covers every UTC hour, so the rule fires whatever the clock says.
    monkeypatch.setenv("GIGMATE_AGENT_QUIET_HOURS", "0-24")
    response = client.post(
        f"/api/v1/work-orders/{order}/drafts",
        json={"kind": "follow_up", "base_proposal_id": proposal_id},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AGENT_QUIET_HOURS"


def test_stale_proposal_cannot_seed_a_draft(proposal):
    client, factory, headers, proposal_id, order = proposal
    with factory.begin() as db:
        db.get(ConversationRow, uid(2)).context_version = 9
    response = client.post(
        f"/api/v1/work-orders/{order}/drafts",
        json={"kind": "follow_up", "base_proposal_id": proposal_id},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AGENT_DRAFT_STALE"


def test_command_requires_exactly_one_source(proposal):
    client, _factory, headers, proposal_id, order = proposal
    both = client.post(
        f"/api/v1/work-orders/{order}/drafts",
        json={"kind": "follow_up", "base_proposal_id": proposal_id, "text": "x"},
        headers=headers,
    )
    assert both.status_code == 422
    neither = client.post(
        f"/api/v1/work-orders/{order}/drafts", json={"kind": "follow_up"}, headers=headers
    )
    assert neither.status_code == 422
