"""Fictional regression cases for field-local extraction and owned review recovery."""

import copy
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_create_order import create
from test_extraction_batch3 import (
    MESSAGE_ID,
    _configure,
    _gate_open_provider,
    _request,
    _scripted_client,
    _suggestion_payload,
)
from test_waha_ingress import ingress as ingress  # noqa: F401
from test_waha_ingress import post, raw

from gigmate.db import (
    ConversationRow,
    Inbox,
    Job,
    MessageRow,
    Proposal,
    WahaChat,
    WorkOrderRow,
)
from gigmate.extraction.disabled import DisabledProvider
from gigmate.extraction.registry import _reset_provider_for_testing
from gigmate.seed import uid
from gigmate.worker import run_once


@pytest.mark.parametrize(
    "bad",
    [
        {"start_at": "tomorrow"},
        {"kind": "timed", "start_at": "2026-10-20T02:00:00Z"},
        "tomorrow",
        {"kind": "instant", "at": "2026-10-20T02:00:00Z", "timezone": "Asia/Hong_Kong"},
    ],
)
def test_partial_new_order_keeps_summary_and_address(monkeypatch, bad):
    _configure(monkeypatch)
    payload = _suggestion_payload()
    payload["new_work_order"]["fields"].append(
        {
            "field": "schedule",
            "value": bad,
            "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
            "reason": "Incomplete fixture",
        }
    )
    outcome = _gate_open_provider(_scripted_client(payload)).propose(_request())
    suggestion = outcome.proposal.new_work_order
    assert suggestion is not None
    assert suggestion.summary == payload["new_work_order"]["summary"]
    assert [f.field for f in suggestion.fields] == ["address"]
    assert "schedule" in suggestion.missing_fields
    assert "llm:field-omitted:schedule" in outcome.notes


def test_partial_existing_change_survives_bad_unrelated_field(monkeypatch):
    _configure(monkeypatch)
    target = uid(3)
    good = {
        "field": "address",
        "old_value": None,
        "new_value": "合成地址",
        "field_status": "proposed",
        "customer_confirmation": "pending",
        "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
        "reason": "客户说明地点",
    }
    payload = _suggestion_payload(
        assignment="matched",
        work_order_id=target,
        base_work_order_version=3,
        new_work_order=None,
        changes=[good, {**good, "field": "deadline", "new_value": {"at": "missing-kind"}}],
    )
    outcome = _gate_open_provider(_scripted_client(payload)).propose(
        _request(candidate_work_order_ids=(target,), base_work_order_version=3)
    )
    assert outcome.refused_reason is None
    assert [c.field for c in outcome.proposal.changes] == ["address"]


def test_new_job_is_not_forced_into_an_existing_order(monkeypatch):
    _configure(monkeypatch)
    payload = _suggestion_payload()
    request = _request(
        candidate_work_order_ids=(uid(3),),
        base_work_order_version=3,
        extra={
            "candidate_orders": [
                {"id": uid(3), "version": 3, "summary": "合成摄影业务", "fields": {}}
            ]
        },
    )
    outcome = _gate_open_provider(_scripted_client(payload)).propose(request)
    assert outcome.proposal.new_work_order is not None
    assert outcome.proposal.work_order_id is None


def test_model_can_select_second_order_with_its_own_version(monkeypatch):
    _configure(monkeypatch)
    second = str(uuid4())
    payload = _suggestion_payload(
        assignment="matched",
        work_order_id=second,
        base_work_order_version=8,
        new_work_order=None,
        changes=[
            {
                "field": "address",
                "old_value": None,
                "new_value": "合成地点",
                "field_status": "proposed",
                "customer_confirmation": "pending",
                "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
                "reason": "只改第二单",
            }
        ],
    )
    request = _request(
        candidate_work_order_ids=(uid(3), second),
        extra={"candidate_orders": [{"id": uid(3), "version": 3}, {"id": second, "version": 8}]},
    )
    outcome = _gate_open_provider(_scripted_client(payload)).propose(request)
    assert outcome.proposal.work_order_id == second
    assert outcome.proposal.base_work_order_version == 8
    assert outcome.refused_reason is None


def prepared_review(ingress, monkeypatch):
    client, factory, _, headers, _, conversation = ingress
    assert post(ingress, raw()).status_code == 200
    _reset_provider_for_testing(DisabledProvider())
    try:
        assert run_once(factory)
    finally:
        _reset_provider_for_testing()
    monkeypatch.setattr("gigmate.extraction.reviewed.configured_for_live", lambda: True)
    with factory() as db:
        job = db.scalar(
            select(Job)
            .join(Inbox)
            .where(Inbox.payload["conversation_id"].as_string() == conversation)
        )
        job_id = job.id
        context = db.get(ConversationRow, conversation).context_version
    return client, factory, headers, conversation, job_id, context


def test_reanalysis_is_explicit_durable_and_fenced_after_reauthorization(ingress, monkeypatch):
    client, factory, headers, conversation, original, context = prepared_review(
        ingress, monkeypatch
    )
    with factory.begin() as db:
        before_orders = db.scalar(select(func.count()).select_from(WorkOrderRow))
        db.get(ConversationRow, conversation).context_version += 2
    body = {"expected_context_version": context + 2}
    route = f"/api/v1/review-items/{original}/reanalyze"
    first = client.post(route, json=body, headers={**headers, "Idempotency-Key": str(uuid4())})
    second = client.post(route, json=body, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert first.status_code == second.status_code == 200
    queued_id = first.json()["data"]["job_id"]
    assert queued_id == second.json()["data"]["job_id"]
    with factory() as db:
        assert db.get(Job, queued_id).state == "pending"
        assert db.get(Inbox, queued_id).context_version == context + 2
        assert db.scalar(select(func.count()).select_from(WorkOrderRow)) == before_orders
    stale = client.post(
        route,
        json={"expected_context_version": context},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert stale.status_code == 409


@pytest.mark.parametrize("denial", ["unknown", "revoked", "consumed"])
def test_reanalysis_cannot_bypass_unknown_outcomes_or_source_decisions(
    ingress, monkeypatch, denial
):
    client, factory, headers, conversation, original, context = prepared_review(
        ingress, monkeypatch
    )
    with factory.begin() as db:
        job = db.get(Job, original)
        if denial == "unknown":
            job.error_code = "MODEL_OUTCOME_UNKNOWN"
        elif denial == "revoked":
            db.get(ConversationRow, conversation).allowlisted = False
        else:
            job.error_code = "NEW_ORDER_REVIEWED"
    response = client.post(
        f"/api/v1/review-items/{original}/reanalyze",
        json={"expected_context_version": context},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code in {403, 409}
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 1


def test_order_sources_do_not_include_unrelated_messages_in_the_same_chat(signed_in):
    client, factory, _, headers = signed_in
    with factory.begin() as db:
        original = db.get(MessageRow, (uid(5), 1))
        other = copy.deepcopy(original.data)
        other_id = str(uuid4())
        other.update(id=other_id, provider_message_id="synthetic:other", text="无关的第二件事")
        db.add(
            MessageRow(
                id=other_id,
                revision=1,
                account_id=uid(1),
                conversation_id=uid(2),
                provider_message_id="synthetic:other",
                data=other,
            )
        )
    response = create(
        client, headers, source_messages=[{"message_id": uid(5), "message_revision": 1}]
    )
    assert response.status_code == 201, response.text
    order = response.json()["data"]
    visible = client.get(
        f"/api/v1/conversations/{uid(2)}/messages", params={"work_order_id": order["id"]}
    ).json()["items"]
    assert {m["id"] for m in visible} == {uid(5)}
    all_messages = client.get(f"/api/v1/conversations/{uid(2)}/messages").json()["items"]
    assert other_id in {m["id"] for m in all_messages}
    assert (
        client.get(
            f"/api/v1/conversations/{uid(2)}/messages", params={"work_order_id": str(uuid4())}
        ).status_code
        == 404
    )


def test_contact_views_use_owned_phone_instead_of_internal_id(ingress):
    client, factory, _, _, _, conversation = ingress
    with factory.begin() as db:
        chat = db.scalar(select(WahaChat).where(WahaChat.conversation_id == conversation))
        chat.provider_chat_id = "85200000000@c.us"
    value = client.get(f"/api/v1/conversations/{conversation}").json()["data"]
    assert value["display_name"] == "+85200000000"
    assert "api_key" not in value and "team_progress" not in value


def test_a_failed_message_does_not_poison_the_following_message(ingress):
    client, factory, _, _, _, conversation = ingress
    assert post(ingress, raw()).status_code == 200

    class Independent(DisabledProvider):
        calls = 0

        def propose(self, request):
            self.calls += 1
            outcome = super().propose(request)
            if self.calls == 1:
                return outcome
            from dataclasses import replace

            from gigmate.contracts import ChangeProposal

            data = outcome.proposal.model_dump(mode="json")
            data["new_work_order"] = {
                "summary": "合成摄影新需求",
                "fields": [],
                "missing_fields": ["schedule", "address"],
                "unresolved_questions": ["拍摄多久？"],
                "confidence": 0.9,
            }
            return replace(outcome, proposal=ChangeProposal.model_validate(data))

    provider = Independent()
    _reset_provider_for_testing(provider)
    try:
        assert run_once(factory)
        next_message = raw(event_id="synthetic:second-event")
        next_message["payload"].update(id="synthetic:second-message", body="下周还需要另拍一组照片")
        assert post(ingress, next_message).status_code == 200
        assert run_once(factory)
        with factory() as db:
            proposals = list(
                db.scalars(
                    select(Proposal)
                    .where(Proposal.conversation_id == conversation)
                    .order_by(Proposal.created_at)
                )
            )
            assert len(proposals) == 2 and proposals[-1].proposal["new_work_order"] is not None
        assert provider.calls == 2
    finally:
        _reset_provider_for_testing()


def test_an_unsourced_second_order_does_not_borrow_another_jobs_message(signed_in):
    client, _, _, headers = signed_in
    response = create(client, headers, source_messages=[])
    assert response.status_code == 201
    order = response.json()["data"]
    messages = client.get(
        f"/api/v1/conversations/{uid(2)}/messages", params={"work_order_id": order["id"]}
    ).json()["items"]
    assert messages == []
    assert not [
        a
        for a in client.get("/api/v1/actions").json()["items"]
        if a["work_order_id"] == order["id"]
    ]


@pytest.mark.parametrize("same_key", [True, False])
def test_postgres_reanalysis_concurrent_requests_queue_one_paid_call(
    ingress, monkeypatch, same_key
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    client, factory, headers, _, original, context = prepared_review(ingress, monkeypatch)
    with factory() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("PostgreSQL locking required")
    barrier = Barrier(2)
    key = str(uuid4())

    def submit(index):
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v1/review-items/{original}/reanalyze",
            json={"expected_context_version": context},
            headers={**headers, "Idempotency-Key": key if same_key else str(uuid4())},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json()["data"]["job_id"] == results[1].json()["data"]["job_id"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 2


def test_burst_messages_are_each_analyzed_without_reusing_a_failed_call(ingress):
    _, factory, _, _, _, conversation = ingress
    first = raw(event_id="synthetic:burst-1")
    second = raw(event_id="synthetic:burst-2")
    second["payload"].update(id="synthetic:message-second", body="另一个独立需求")
    assert post(ingress, first).status_code == post(ingress, second).status_code == 200

    class Recording(DisabledProvider):
        messages = []

        def propose(self, request):
            self.messages.append(request.message_id)
            return super().propose(request)

    provider = Recording()
    _reset_provider_for_testing(provider)
    try:
        assert run_once(factory) and run_once(factory)
        assert len(set(provider.messages)) == 2
    finally:
        _reset_provider_for_testing()


def test_pending_messages_do_not_auto_reprocess_across_withdrawal(ingress):
    from datetime import UTC, datetime, timedelta

    from gigmate.db import WahaExclusion

    _, factory, _, _, binding, conversation = ingress
    assert post(ingress, raw()).status_code == 200
    with factory.begin() as db:
        chat = db.scalar(select(WahaChat).where(WahaChat.conversation_id == conversation))
        now = datetime.now(UTC)
        db.add(
            WahaExclusion(
                id=str(uuid4()),
                connection_id=binding.connection_id,
                chat_id=chat.id,
                started_at=now,
                ended_at=now + timedelta(microseconds=1),
            )
        )
        db.get(ConversationRow, conversation).context_version += 2

    class NeverCalled(DisabledProvider):
        def propose(self, request):
            raise AssertionError("Consent change needs explicit reanalysis")

    _reset_provider_for_testing(NeverCalled())
    try:
        assert run_once(factory)
        with factory() as db:
            assert db.scalar(select(Job)).error_code == "SOURCE_SUPERSEDED"
    finally:
        _reset_provider_for_testing()


def test_owned_group_name_survives_candidate_expiry(ingress):
    client, factory, _, _, _, conversation = ingress
    with factory.begin() as db:
        chat = db.scalar(select(WahaChat).where(WahaChat.conversation_id == conversation))
        chat.provider_chat_id = "synthetic-group@g.us"
        chat.display_name = "合成项目群"
    assert (
        client.get(f"/api/v1/conversations/{conversation}").json()["data"]["display_name"]
        == "合成项目群"
    )


def interpreted_reanalysis(ingress, monkeypatch):
    from dataclasses import replace

    from gigmate.contracts import ChangeProposal

    client, factory, headers, conversation, original, context = prepared_review(
        ingress, monkeypatch
    )
    response = client.post(
        f"/api/v1/review-items/{original}/reanalyze",
        json={"expected_context_version": context},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200
    queued = response.json()["data"]["job_id"]

    class NewJob(DisabledProvider):
        def propose(self, request):
            outcome = super().propose(request)
            data = outcome.proposal.model_dump(mode="json")
            data["new_work_order"] = {
                "summary": "合成新任务",
                "fields": [],
                "missing_fields": ["schedule", "address"],
                "unresolved_questions": ["请补充时间"],
                "confidence": 0.9,
            }
            return replace(outcome, proposal=ChangeProposal.model_validate(data))

    _reset_provider_for_testing(NewJob())
    try:
        assert run_once(factory)
    finally:
        _reset_provider_for_testing()
    return client, factory, headers, conversation, original, context, queued


def test_reanalysis_suggestion_consumes_the_original_event_once(ingress, monkeypatch):
    from gigmate.db import ProposalDecision

    client, factory, headers, conversation, original, context, queued = interpreted_reanalysis(
        ingress, monkeypatch
    )
    [suggestion] = client.get("/api/v1/new-order-suggestions").json()["items"]
    response = client.post(
        "/api/v1/work-orders",
        json={
            "conversation_id": conversation,
            "summary": "合成摄影任务",
            "from_proposal_id": suggestion["id"],
            "expected_context_version": context,
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    with factory() as db:
        origin = db.get(Job, original).event_id
        assert db.get(ProposalDecision, origin) is not None
    retry = client.post(
        f"/api/v1/review-items/{original}/reanalyze",
        json={"expected_context_version": context},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert retry.status_code == 409
    assign = client.post(
        f"/api/v1/review-items/{queued}/assign",
        json={"action": "dismiss", "expected_context_version": context},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert assign.status_code == 409
    assert client.get("/api/v1/new-order-suggestions").json()["items"] == []


def test_dismissing_reanalysis_does_not_resurrect_the_parent_after_new_context(
    ingress, monkeypatch
):
    client, factory, headers, conversation, original, context, queued = interpreted_reanalysis(
        ingress, monkeypatch
    )
    response = client.post(
        f"/api/v1/review-items/{queued}/assign",
        json={"action": "dismiss", "expected_context_version": context},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    with factory.begin() as db:
        db.get(ConversationRow, conversation).context_version += 1
    response = client.post(
        f"/api/v1/review-items/{original}/reanalyze",
        json={"expected_context_version": context + 1},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 2
