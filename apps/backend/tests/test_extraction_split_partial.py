"""Per-message assignment, partial extraction and no cascading review.

Covers the 2026-10-18 fix batch:

* one conversation can hold several open orders; the model chooses one per
  message, and a new request is recognised even when orders already exist;
* one unreadable field no longer sends the whole message to review;
* a message that fails is reviewed alone; the next message is analysed fresh.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from test_extraction_gates import (
    ACCOUNT_ID,
    CANDIDATE,
    CONVERSATION_ID,
    MESSAGE_ID,
    RECEIVED_AT,
    _address_payload,
    _configure,
    _gate_open_provider,
    _grounded_request,
    _request,
    _run,
    _schedule_payload,
    _scripted_client,
)

from gigmate import worker as worker_module
from gigmate.contracts import ChangeProposal
from gigmate.db import (
    Account,
    Base,
    ChangeRow,
    ConversationOrder,
    ConversationRow,
    Inbox,
    WorkOrderRow,
)
from gigmate.extraction.registry import _reset_provider_for_testing
from gigmate.extraction.types import ExtractionOutcome
from gigmate.worker import _route_through_provider

SECOND = "00000000-0000-4000-8000-0000000000b2"


@pytest.fixture
def memory_factory(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "split.db").as_posix())
    try:
        Base.metadata.create_all(engine)
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()


def _two_orders(**overrides):
    values = {
        "candidate_work_order_ids": (CANDIDATE, SECOND),
        "base_work_order_version": None,
        "candidate_versions": {CANDIDATE: 3, SECOND: 7},
        "candidate_snapshots": {
            CANDIDATE: {"summary": "陈小姐证件照拍摄", "status": "confirmed", "fields": {}},
            SECOND: {"summary": "陈小姐全家福", "status": "pending_confirmation", "fields": {}},
        },
    }
    values.update(overrides)
    return _grounded_request(**values)


def _schedule_and_address(address_change: dict | None = None) -> dict:
    payload = _schedule_payload()
    payload["changes"].append(
        address_change
        or {
            "field": "address",
            "old_value": None,
            "new_value": "中环德辅道中 88 号",
            "field_status": "proposed",
            "customer_confirmation": "confirmed",
            "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
            "reason": "客人给了见面地址。",
        }
    )
    return payload


# --- Requirement 3: partial recognition still produces a proposal ---------------


def test_one_invalid_field_is_dropped_and_the_rest_is_kept(monkeypatch):
    payload = _schedule_and_address()
    payload["changes"][1]["customer_confirmation"] = "not-a-state"
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.refused_reason is None
    assert outcome.proposal.assignment.value == "matched"
    assert [c.field for c in outcome.proposal.changes] == ["schedule"]
    assert "llm:partial-dropped:address" in outcome.notes
    assert any("地址" in q for q in outcome.proposal.unresolved_questions)


def test_missing_time_basis_drops_only_the_date_fields(monkeypatch):
    """Gate 4 still never promotes a guessed date, but keeps the address."""
    outcome, _ = _run(monkeypatch, _schedule_and_address(), _request())
    assert outcome.proposal.assignment.value == "matched"
    assert [c.field for c in outcome.proposal.changes] == ["address"]
    assert "llm:partial-dropped:schedule" in outcome.notes
    assert any("时间" in q for q in outcome.proposal.unresolved_questions)


def test_a_message_with_nothing_usable_still_goes_to_review(monkeypatch):
    payload = _schedule_payload()
    payload["changes"][0]["sources"] = []
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.refused_reason == "llm:response-provenance-failed:source-missing"


def test_new_order_suggestion_keeps_valid_fields_and_marks_the_rest_missing(monkeypatch):
    payload = {
        "assignment": "needs_review",
        "work_order_id": None,
        "base_work_order_version": None,
        "candidates": [],
        "changes": [],
        "unresolved_questions": [],
        "draft_text": None,
        "new_work_order": {
            "summary": "陈小姐证件照拍摄",
            "fields": [
                {
                    "field": "address",
                    "value": "旺角弥敦道 1 号",
                    "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
                    "reason": "客人给了地址。",
                },
                {
                    "field": "schedule",
                    "value": {"kind": "timed", "start_at": "bad", "end_at": "bad"},
                    "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
                    "reason": "时间格式不对。",
                },
            ],
            "missing_fields": [],
            "unresolved_questions": [],
            "confidence": 0.9,
        },
    }
    outcome, _ = _run(monkeypatch, payload, _grounded_request(candidate_work_order_ids=()))
    suggestion = outcome.proposal.new_work_order
    assert suggestion is not None
    assert [f.field for f in suggestion.fields] == ["address"]
    assert "schedule" in suggestion.missing_fields


# --- Requirement 2: per-message assignment across several orders ----------------


def test_model_sees_every_open_order_and_the_output_language(monkeypatch):
    _, client = _run(monkeypatch, _schedule_payload(), _two_orders())
    sent = json.loads(client.requests[0]["json"]["messages"][-1]["content"])
    ids = [order["work_order_id"] for order in sent["candidate_work_orders"]]
    assert ids == [CANDIDATE, SECOND]
    assert sent["candidate_work_orders"][1]["version"] == 7
    assert sent["output_language"] == "zh-Hans"


def test_message_can_be_matched_to_the_second_open_order(monkeypatch):
    payload = _address_payload()
    payload.update(work_order_id=SECOND, base_work_order_version=7)
    outcome, _ = _run(monkeypatch, payload, _two_orders())
    assert outcome.proposal.assignment.value == "matched"
    assert outcome.proposal.work_order_id == SECOND
    assert outcome.proposal.base_work_order_version == 7


def test_version_must_be_the_chosen_orders_own_version(monkeypatch):
    payload = _address_payload()
    payload.update(work_order_id=SECOND, base_work_order_version=3)
    outcome, _ = _run(monkeypatch, payload, _two_orders())
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.refused_reason == "llm:response-provenance-failed:base_work_order_version"


def test_new_request_is_recognised_while_an_order_already_exists(monkeypatch):
    payload = {
        "assignment": "needs_review",
        "work_order_id": None,
        "base_work_order_version": None,
        "candidates": [{"work_order_id": CANDIDATE, "confidence": 0.0}],
        "changes": [],
        "unresolved_questions": [],
        "draft_text": None,
        "new_work_order": {
            "summary": "陈小姐全家福",
            "fields": [],
            "missing_fields": ["schedule", "address"],
            "unresolved_questions": ["几号拍？"],
            "confidence": 0.8,
        },
    }
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.proposal.new_work_order is not None
    assert outcome.proposal.work_order_id is None


# --- Requirement 4: one failed message does not affect the next -----------------


def _seed_two(memory_factory):
    db = memory_factory()
    db.add(Account(id=ACCOUNT_ID, username="split", password_hash="x", active=True))
    db.add(
        ConversationRow(
            id=CONVERSATION_ID, account_id=ACCOUNT_ID, context_version=5, allowlisted=True
        )
    )
    for order_id, version in ((CANDIDATE, 3), (SECOND, 7)):
        db.add(
            WorkOrderRow(
                id=order_id,
                account_id=ACCOUNT_ID,
                data={"id": order_id, "version": version, "pending_change_ids": []},
            )
        )
        db.add(ConversationOrder(conversation_id=CONVERSATION_ID, work_order_id=order_id))
    db.flush()
    return db


def _receipt(db):
    receipt = Inbox(
        id=str(uuid4()),
        account_id=ACCOUNT_ID,
        payload={},
        digest=uuid4().hex,
        received_at=datetime.now(UTC),
        context_version=5,
    )
    db.add(receipt)
    db.flush()
    return receipt


def _event():
    return {
        "occurred_at": RECEIVED_AT,
        "message_revision": 1,
        "payload": {"message_id": MESSAGE_ID, "text": "全家福那单地址改去旺角"},
    }


def _scripted_provider(monkeypatch, payload):
    _configure(
        monkeypatch,
        GIGMATE_WORKSPACE_TIMEZONE="Asia/Hong_Kong",
        GIGMATE_LLM_ALLOW_LIVE_ORIGIN="1",
    )
    return _gate_open_provider(_scripted_client(payload))


def test_failed_message_does_not_block_the_next_one_with_two_open_orders(
    memory_factory, monkeypatch
):
    db = _seed_two(memory_factory)
    monkeypatch.setattr(worker_module, "draft_for_change", lambda *a, **k: None)
    conversation = db.get(ConversationRow, CONVERSATION_ID)
    account = db.get(Account, ACCOUNT_ID)

    # Message 1: nothing usable → review, no change rows.
    broken = _schedule_payload()
    broken["changes"][0]["sources"] = []
    _reset_provider_for_testing(_scripted_provider(monkeypatch, broken))
    try:
        first = _route_through_provider(
            db,
            account=account,
            inbox=_receipt(db),
            event=_event(),
            conversation=conversation,
            linked=[CANDIDATE, SECOND],
        )
    finally:
        _reset_provider_for_testing(None)
    assert first is False
    assert db.scalar(select(ChangeRow).limit(1)) is None

    # Message 2: analysed fresh and filed to the second order. Before the fix,
    # two open orders meant every later message went straight to review.
    good = _address_payload()
    good.update(work_order_id=SECOND, base_work_order_version=7)
    _reset_provider_for_testing(_scripted_provider(monkeypatch, good))
    try:
        second = _route_through_provider(
            db,
            account=account,
            inbox=_receipt(db),
            event=_event(),
            conversation=conversation,
            linked=[CANDIDATE, SECOND],
        )
    finally:
        _reset_provider_for_testing(None)
    assert second is True
    rows = list(db.scalars(select(ChangeRow)))
    assert [row.work_order_id for row in rows] == [SECOND]
    assert db.get(WorkOrderRow, SECOND).data["pending_change_ids"] == [rows[0].id]
    assert db.get(WorkOrderRow, CANDIDATE).data["pending_change_ids"] == []


def test_stale_second_order_discards_the_result(memory_factory, monkeypatch):
    """Any offered order moving on during the call makes the comparison stale."""
    db = _seed_two(memory_factory)
    monkeypatch.setattr(worker_module, "draft_for_change", lambda *a, **k: None)
    good = _address_payload()
    good.update(work_order_id=SECOND, base_work_order_version=7)
    provider = _scripted_provider(monkeypatch, good)
    original = provider.propose

    def propose_then_bump(request):
        outcome = original(request)
        order = db.get(WorkOrderRow, CANDIDATE)
        order.data = {**order.data, "version": 4}
        db.flush()
        return outcome

    provider.propose = propose_then_bump
    _reset_provider_for_testing(provider)
    try:
        matched = _route_through_provider(
            db,
            account=db.get(Account, ACCOUNT_ID),
            inbox=_receipt(db),
            event=_event(),
            conversation=db.get(ConversationRow, CONVERSATION_ID),
            linked=[CANDIDATE, SECOND],
        )
    finally:
        _reset_provider_for_testing(None)
    assert matched is False
    assert db.scalar(select(ChangeRow).limit(1)) is None


def test_contract_still_forbids_matched_with_a_new_order():
    """The split is per message: one message → one order or one new suggestion."""
    data = {
        "schema_version": "0.1.0",
        "proposal_id": str(uuid4()),
        "conversation_id": CONVERSATION_ID,
        "work_order_id": CANDIDATE,
        "base_work_order_version": 3,
        "base_context_version": 5,
        "assignment": "matched",
        "candidates": [],
        "changes": [],
        "unresolved_questions": [],
        "new_work_order": {
            "summary": "x",
            "fields": [],
            "missing_fields": [],
            "unresolved_questions": [],
            "confidence": 0.5,
        },
        "draft_text": None,
        "model_version": "m",
        "prompt_version": "p",
    }
    try:
        ChangeProposal.model_validate(data)
    except ValueError:
        return
    raise AssertionError("matched + new_work_order must stay invalid")


def test_outcome_type_is_unchanged():
    assert ExtractionOutcome.__dataclass_fields__.keys() >= {"notes", "refused_reason"}


@pytest.mark.parametrize("malformed", [[], {}])
def test_malformed_order_identity_is_refused_without_exception(monkeypatch, malformed):
    payload = _address_payload()
    payload["work_order_id"] = malformed
    outcome, _ = _run(monkeypatch, payload, _two_orders())
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.refused_reason == "llm:response-provenance-failed:work_order_id"


@pytest.mark.parametrize("malformed", [["address"], {"name": "address"}])
def test_malformed_field_name_drops_only_that_field(monkeypatch, malformed):
    payload = _schedule_and_address()
    payload["changes"][1]["field"] = malformed
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.refused_reason is None
    assert [change.field for change in outcome.proposal.changes] == ["schedule"]


# --- Requirement: only the AI-identified order/field invalidates old proposals ---


def _old_change(db, order_id, field, *, version=4, source=None, status="proposed"):
    """An open proposal written for the previous message (context 4)."""
    change_id = str(uuid4())
    db.add(
        ChangeRow(
            id=change_id,
            account_id=ACCOUNT_ID,
            work_order_id=order_id,
            conversation_id=CONVERSATION_ID,
            context_version=version,
            data={
                "id": change_id,
                "field": field,
                "status": status,
                "sources": [
                    {"message_id": source or str(uuid4()), "message_revision": 1},
                ],
            },
        )
    )
    db.flush()
    return change_id


def _route(db, monkeypatch, payload, linked):
    monkeypatch.setattr(worker_module, "draft_for_change", lambda *a, **k: None)
    _reset_provider_for_testing(_scripted_provider(monkeypatch, payload))
    try:
        return _route_through_provider(
            db,
            account=db.get(Account, ACCOUNT_ID),
            inbox=_receipt(db),
            event=_event(),
            conversation=db.get(ConversationRow, CONVERSATION_ID),
            linked=linked,
        )
    finally:
        _reset_provider_for_testing(None)


def _status(db, change_id):
    row = db.get(ChangeRow, change_id)
    return row.data["status"], row.context_version


def _thanks():
    return {
        "assignment": "needs_review",
        "work_order_id": None,
        "base_work_order_version": None,
        "candidates": [],
        "changes": [],
        "unresolved_questions": [],
        "draft_text": None,
        "relevance": "unrelated",
    }


def test_thanks_keeps_every_open_proposal_confirmable(memory_factory, monkeypatch):
    db = _seed_two(memory_factory)
    a = _old_change(db, CANDIDATE, "schedule")
    b = _old_change(db, SECOND, "address")
    _route(db, monkeypatch, _thanks(), [CANDIDATE, SECOND])
    # Still proposed and moved to the current context: confirmable again.
    assert _status(db, a) == ("proposed", 5)
    assert _status(db, b) == ("proposed", 5)


def test_only_the_same_order_and_field_is_superseded(memory_factory, monkeypatch):
    db = _seed_two(memory_factory)
    same = _old_change(db, SECOND, "address")
    other_field = _old_change(db, SECOND, "schedule")
    other_order = _old_change(db, CANDIDATE, "address")
    payload = _address_payload()
    payload.update(work_order_id=SECOND, base_work_order_version=7, relevance="related")
    assert _route(db, monkeypatch, payload, [CANDIDATE, SECOND]) is True
    assert _status(db, same)[0] == "needs_review"
    assert _status(db, other_field) == ("proposed", 5)
    assert _status(db, other_order) == ("proposed", 5)


def test_a_field_the_ai_tried_but_failed_to_read_still_supersedes(memory_factory, monkeypatch):
    db = _seed_two(memory_factory)
    old_schedule = _old_change(db, SECOND, "schedule")
    payload = _address_payload()
    payload.update(work_order_id=SECOND, base_work_order_version=7)
    payload["changes"].append(
        {
            "field": "schedule",
            "old_value": None,
            "new_value": {"kind": "timed", "start_at": "bad"},
            "field_status": "proposed",
            "customer_confirmation": "pending",
            "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
            "reason": "客人想改时间。",
        }
    )
    _route(db, monkeypatch, payload, [CANDIDATE, SECOND])
    assert _status(db, old_schedule)[0] == "needs_review"


def test_when_the_ai_cannot_tell_every_old_proposal_is_superseded(memory_factory, monkeypatch):
    db = _seed_two(memory_factory)
    a = _old_change(db, CANDIDATE, "schedule")
    unsure = _thanks()
    unsure.pop("relevance")
    unsure["unresolved_questions"] = ["不确定是哪一单。"]
    _route(db, monkeypatch, unsure, [CANDIDATE, SECOND])
    assert _status(db, a)[0] == "needs_review"


def test_a_proposal_two_messages_old_is_superseded(memory_factory, monkeypatch):
    """An unanalysed message in between means nobody checked it: be conservative."""
    db = _seed_two(memory_factory)
    stale = _old_change(db, CANDIDATE, "schedule", version=3)
    _route(db, monkeypatch, _thanks(), [CANDIDATE, SECOND])
    assert _status(db, stale)[0] == "needs_review"


def test_revoking_a_message_supersedes_only_proposals_quoting_it(memory_factory):
    from gigmate.pending import on_source_changed

    db = _seed_two(memory_factory)
    quoted = _old_change(db, CANDIDATE, "schedule", source=MESSAGE_ID)
    unrelated = _old_change(db, SECOND, "address")
    conversation = db.get(ConversationRow, CONVERSATION_ID)
    on_source_changed(db, conversation, MESSAGE_ID, revoked=True, new_version=5)
    assert _status(db, quoted)[0] == "needs_review"
    assert _status(db, unrelated) == ("proposed", 5)


# --- Requirement: one message, a change to order A plus a separate new job ---


def _with_side_request():
    payload = _address_payload()
    payload.update(
        work_order_id=SECOND,
        base_work_order_version=7,
        also_new_work_order={
            "summary": "陈小姐另约全家福",
            "fields": [
                {
                    "field": "address",
                    "value": "旺角弥敦道 1 号",
                    "sources": [{"message_id": "wrong", "message_revision": 9}],
                    "reason": "客人给了地址。",
                }
            ],
            "missing_fields": ["schedule"],
            "unresolved_questions": ["全家福想约几号？"],
            "confidence": 0.8,
        },
    )
    return payload


def test_side_request_is_parsed_and_asked_about(monkeypatch):
    outcome, _ = _run(monkeypatch, _with_side_request(), _two_orders())
    assert outcome.proposal.assignment.value == "matched"
    assert outcome.side_request["summary"] == "陈小姐另约全家福"
    source = outcome.side_request["fields"][0]["sources"][0]
    assert source == {"message_id": MESSAGE_ID, "message_revision": 1}
    assert "llm:side-request" in outcome.notes
    assert any("另开一单" in q for q in outcome.proposal.unresolved_questions)


def test_side_request_is_ignored_without_a_matched_change(monkeypatch):
    payload = _thanks()
    payload["also_new_work_order"] = _with_side_request()["also_new_work_order"]
    outcome, _ = _run(monkeypatch, payload, _two_orders())
    assert outcome.side_request is None


def test_side_request_becomes_a_listed_suggestion_next_to_the_change(memory_factory, monkeypatch):
    from gigmate.db import Job, Proposal
    from gigmate.product_commands import available_suggestion_job

    db = _seed_two(memory_factory)
    assert _route(db, monkeypatch, _with_side_request(), [CANDIDATE, SECOND]) is True
    assert [row.work_order_id for row in db.scalars(select(ChangeRow))] == [SECOND]
    side = db.scalar(select(Proposal).where(Proposal.assignment == "needs_review"))
    assert side is not None and side.work_order_id is None
    assert side.proposal["new_work_order"]["summary"] == "陈小姐另约全家福"
    # The matched message's job completes cleanly and the suggestion is offered.
    db.add(
        Job(
            id=str(uuid4()),
            event_id=side.event_id,
            account_id=ACCOUNT_ID,
            state="completed",
            attempts=1,
            available_at=datetime.now(UTC),
            error_code=None,
        )
    )
    db.flush()
    assert db.scalar(available_suggestion_job(ACCOUNT_ID, side.event_id)) is not None
