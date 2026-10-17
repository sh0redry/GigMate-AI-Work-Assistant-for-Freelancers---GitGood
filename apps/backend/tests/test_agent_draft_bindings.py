"""Drafts stay bound to the reviewed order and current, authorised context."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from test_agent_drafts import proposal as proposal

from gigmate.db import (
    AgentDraftRow,
    ConversationOrder,
    ConversationRow,
    Proposal,
    WorkOrderRow,
)
from gigmate.seed import uid


def create(ctx, *, order_id=None, merchant_text=False):
    client, _, headers, proposal_id, original_order = ctx
    body = (
        {"text": "Synthetic merchant draft"} if merchant_text else {"base_proposal_id": proposal_id}
    )
    return client.post(
        f"/api/v1/work-orders/{order_id or original_order}/drafts",
        json={"kind": "follow_up", **body},
        headers=headers,
    )


@pytest.mark.parametrize("merchant_text", [False, True])
@pytest.mark.parametrize("change", ["context", "order_version", "consent", "link", "closed"])
def test_read_and_consume_revalidate_existing_draft(proposal, merchant_text, change):
    client, factory, headers, _, order_id = proposal
    response = create(proposal, merchant_text=merchant_text)
    assert response.status_code == 201, response.text
    draft_id = response.json()["data"]["id"]
    with factory.begin() as db:
        conversation = db.get(ConversationRow, uid(2))
        order = db.get(WorkOrderRow, order_id)
        if change == "context":
            conversation.context_version += 1
        elif change == "order_version":
            order.data = {**order.data, "version": order.data["version"] + 1}
        elif change == "consent":
            conversation.allowlisted = False
        elif change == "link":
            db.delete(db.get(ConversationOrder, (conversation.id, order_id)))
        else:
            order.data = {**order.data, "status": "completed"}
    listed = client.get(f"/api/v1/work-orders/{order_id}/drafts")
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["status"] == "revoked"
    response = client.post(f"/api/v1/drafts/{draft_id}/consume", headers=headers)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "AGENT_DRAFT_NOT_USABLE"
    with factory() as db:
        row = db.get(AgentDraftRow, draft_id)
        assert row.status == "proposed" and row.consumed_at is None


@pytest.mark.parametrize("existing", [False, True])
def test_proposal_cannot_cross_orders_even_when_a_draft_already_exists(proposal, existing):
    client, factory, _, _, _ = proposal
    if existing:
        assert create(proposal).status_code == 201
    other_id = str(uuid4())
    with factory.begin() as db:
        db.add(WorkOrderRow(id=other_id, account_id=uid(1), data={"id": other_id, "version": 1}))
        db.flush()
        db.add(ConversationOrder(conversation_id=uid(2), work_order_id=other_id))
    response = create(proposal, order_id=other_id)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "AGENT_DRAFT_PROPOSAL_MISMATCH"
    assert client.get(f"/api/v1/work-orders/{other_id}/drafts").json()["items"] == []


@pytest.mark.parametrize(
    "change", ["order_version", "unassigned", "version_missing", "consent", "closed"]
)
def test_new_draft_refuses_invalid_proposal_bindings(proposal, change):
    _, factory, _, proposal_id, order_id = proposal
    with factory.begin() as db:
        row = db.get(Proposal, proposal_id)
        order = db.get(WorkOrderRow, order_id)
        if change == "order_version":
            order.data = {**order.data, "version": order.data["version"] + 1}
        elif change == "unassigned":
            row.work_order_id, row.assignment = None, "needs_review"
        elif change == "version_missing":
            row.base_work_order_version = None
        elif change == "consent":
            db.get(ConversationRow, uid(2)).allowlisted = False
        else:
            order.data = {**order.data, "status": "completed"}
    response = create(proposal)
    assert response.status_code == (403 if change == "consent" else 409), response.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AgentDraftRow)) == 0


def second_conversation(ctx):
    _, factory, _, _, order_id = ctx
    identifier = str(uuid4())
    with factory.begin() as db:
        db.add(
            ConversationRow(id=identifier, account_id=uid(1), context_version=7, allowlisted=True)
        )
        db.flush()
        db.add(ConversationOrder(conversation_id=identifier, work_order_id=order_id))
    return identifier


def test_proposal_chooses_its_linked_conversation_instead_of_the_first_link(proposal):
    _, factory, _, proposal_id, _ = proposal
    conversation_id = second_conversation(proposal)
    with factory.begin() as db:
        row = db.get(Proposal, proposal_id)
        row.conversation_id, row.context_version = conversation_id, 7
    response = create(proposal)
    assert response.status_code == 201, response.text
    assert response.json()["data"]["conversation_id"] == conversation_id
    assert response.json()["data"]["context_version"] == 7


def test_manual_draft_requires_an_unambiguous_conversation(proposal):
    second_conversation(proposal)
    response = create(proposal, merchant_text=True)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "AGENT_DRAFT_CONVERSATION_AMBIGUOUS"


def test_lost_proposal_binding_makes_an_existing_draft_unusable(proposal):
    client, factory, headers, proposal_id, order_id = proposal
    draft_id = create(proposal).json()["data"]["id"]
    with factory.begin() as db:
        db.get(Proposal, proposal_id).work_order_id = None
    assert (
        client.get(f"/api/v1/work-orders/{order_id}/drafts").json()["items"][0]["status"]
        == "revoked"
    )
    assert client.post(f"/api/v1/drafts/{draft_id}/consume", headers=headers).status_code == 409


def test_duplicate_creation_recovers_original_draft_after_daily_limit(proposal, monkeypatch):
    monkeypatch.setenv("GIGMATE_AGENT_DRAFT_DAILY_LIMIT", "1")
    response = create(proposal)
    assert response.status_code == 201
    repeated = create(proposal)
    assert repeated.status_code == 201
    assert repeated.json()["data"] == response.json()["data"]
    assert create(proposal, merchant_text=True).status_code == 429


def test_postgres_concurrent_consumption_returns_text_once(proposal, signed_in):
    client, _, headers, _, _ = proposal
    _, _, engine, _ = signed_in
    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrent consumption requires PostgreSQL account locks")
    draft_id = create(proposal).json()["data"]["id"]
    barrier, connections = Barrier(2), set()

    def before_lock(conn, cursor, statement, parameters, execution_context, executemany):
        if "accounts" in statement and "FOR UPDATE" in statement and id(conn) not in connections:
            connections.add(id(conn))
            barrier.wait(timeout=10)

    def consume():
        return client.post(f"/api/v1/drafts/{draft_id}/consume", headers=headers)

    event.listen(engine, "before_cursor_execute", before_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = executor.submit(consume), executor.submit(consume)
            responses = [first.result(timeout=15), second.result(timeout=15)]
    finally:
        event.remove(engine, "before_cursor_execute", before_lock)
    assert sorted(response.status_code for response in responses) == [200, 409]
