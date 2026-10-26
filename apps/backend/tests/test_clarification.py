"""Synthetic AI semantics and review-only replies; no real model or connector."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_authorized_context import authorize, event, submit
from test_authorized_context import authorized_context as authorized_context
from test_waha_ingress import ingress as ingress

from gigmate.approvals import ask_open_items, open_items
from gigmate.clarification import field_for_code, memory_for, parse_assessment, reply_plan
from gigmate.contracts import ChangeProposal, DeferItemCommand
from gigmate.db import (
    Account,
    ActionRow,
    CalendarRow,
    ConversationOrder,
    ConversationRow,
    Inbox,
    MessageRow,
    Proposal,
    ProposalDecision,
    WahaChat,
    WahaSendAction,
    WorkOrderRow,
)
from gigmate.extraction.disabled import DisabledProvider
from gigmate.extraction.registry import _reset_provider_for_testing
from gigmate.extraction.types import ExtractionRequest
from gigmate.seed import uid
from gigmate.worker import run_once


def request(text="周六下午3点开始，地址稍后发"):
    return ExtractionRequest(
        account_id=uid(1),
        conversation_id=uid(2),
        message_id=str(uuid4()),
        message_revision=1,
        message_text=text,
        context_version=1,
    )


def assessment(req, *, deferred=False, ambiguous=False, language="zh-Hans"):
    ref = {"message_id": req.message_id, "message_revision": req.message_revision}

    def fact(item, state, text=None, quote=None):
        return {
            "item": item,
            "state": state,
            "text": text,
            "evidence": [{"source": ref, "quote": quote or req.message_text}]
            if state != "missing"
            else [],
        }

    return {
        "schema_version": "1.0.0",
        "language": language,
        "tone": "concise",
        "facts": [
            fact("date", "known", "周日" if "周日" in req.message_text else "周六"),
            fact("start_time", "ambiguous" if ambiguous else "known", "下午3点"),
            fact("end_time", "missing"),
            fact("duration", "deferred" if deferred else "missing"),
            fact("address", "deferred"),
        ],
        "questions": ["start_time"] if ambiguous else [] if deferred else ["duration"],
    }


@pytest.mark.parametrize("kind", ["duration", "deferred", "ambiguous", "correction"])
def test_model_can_distinguish_partial_correction_ambiguity_and_deferral(kind):
    req = request(
        "不对，改周日，仍是下午3点；时长和地址稍后发"
        if kind == "correction"
        else "周六下午3点开始，时长和地址稍后发"
    )
    raw = assessment(
        req, deferred=kind in {"deferred", "correction"}, ambiguous=kind == "ambiguous"
    )
    result = parse_assessment(raw, req)
    assert result is not None
    assert "date" not in result["questions"]
    assert result["questions"] == raw["questions"]


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign_id",
        "old_revision",
        "invented_quote",
        "invented_value",
        "drop_question",
        "extra_question",
        "duplicate_fact",
        "authority",
        "wrong_language",
    ],
)
def test_invalid_analysis_falls_back_without_trusting_model(mutation):
    req = request()
    raw = assessment(req)
    if mutation == "foreign_id":
        raw["facts"][0]["evidence"][0]["source"]["message_id"] = str(uuid4())
    elif mutation == "old_revision":
        raw["facts"][0]["evidence"][0]["source"]["message_revision"] = 2
    elif mutation == "invented_quote":
        raw["facts"][0]["evidence"][0]["quote"] = "已确认周六"
    elif mutation == "invented_value":
        raw["facts"][0]["text"] = "周五"
    elif mutation == "drop_question":
        raw["questions"] = []
    elif mutation == "extra_question":
        raw["questions"].append("start_time")
    elif mutation == "duplicate_fact":
        raw["facts"][1] = raw["facts"][0]
    elif mutation == "authority":
        raw["confirmed"] = True
    else:
        raw["language"] = "en"
    assert parse_assessment(raw, req) is None


@pytest.fixture
def partial_order(authorized_context, monkeypatch):
    ctx = authorized_context
    authorize(ctx)
    with ctx.factory.begin() as db:
        chat = db.scalar(select(WahaChat).where(WahaChat.provider_chat_id == "syntheticguest1@lid"))
        data = copy.deepcopy(db.get(WorkOrderRow, uid(3)).data)
        ctx.order_id = str(uuid4())
        ctx.conversation_id = chat.conversation_id
        data.update(
            id=ctx.order_id,
            conversation_ids=[ctx.conversation_id],
            status="pending_confirmation",
            version=1,
            pending_change_ids=[],
        )
        for name in ("schedule", "address"):
            data["fields"][name] = {
                "value": None,
                "status": "missing",
                "sources": [],
                "interpretation": None,
            }
        db.add(WorkOrderRow(id=ctx.order_id, account_id=ctx.binding.account_id, data=data))
        db.flush()
        db.add(ConversationOrder(conversation_id=ctx.conversation_id, work_order_id=ctx.order_id))
    return ctx


def process(ctx, *, deferred=False, malformed=False):
    text = "周六下午3点开始，时长和地址稍后发" if deferred else "周六下午3点开始，地址稍后发"
    submit(ctx, *event(ctx, body=text))

    class AI(DisabledProvider):
        def propose(self, req):
            original = super().propose(req)
            data = original.proposal.model_dump(mode="json")
            data.update(
                assignment="matched",
                work_order_id=ctx.order_id,
                base_work_order_version=1,
                changes=[
                    {
                        "field": "schedule",
                        "old_value": None,
                        "new_value": "周六下午3点",
                        "field_status": "needs_review",
                        "customer_confirmation": "pending",
                        "sources": [{"message_id": req.message_id, "message_revision": 1}],
                        "reason": "缺少时长",
                    }
                ],
            )
            raw = assessment(req, deferred=deferred)
            if malformed:
                raw["questions"] = []
            return replace(
                original, proposal=ChangeProposal.model_validate(data), clarification=raw
            )

    _reset_provider_for_testing(AI())
    try:
        assert run_once(ctx.factory)
    finally:
        _reset_provider_for_testing()


def test_partial_start_asks_only_duration_without_calendar_or_external_write(partial_order):
    ctx = partial_order
    with ctx.factory() as db:
        calendar = {r.id: copy.deepcopy(r.data) for r in db.scalars(select(CalendarRow))}
    process(ctx)
    with ctx.factory() as db:
        draft = db.scalar(select(ActionRow).where(ActionRow.work_order_id == ctx.order_id))
        assert draft is not None
        assert "下午3点" in draft.data["body"] and "持续多久" in draft.data["body"]
        assert "哪天" not in draft.data["body"] and "几点方便" not in draft.data["body"]
        assert "地址" not in draft.data["body"]
        assert draft.data["state"] == "pending_approval"
        assert db.get(WorkOrderRow, ctx.order_id).data["fields"]["schedule"]["value"] is None
        assert list(db.scalars(select(WahaSendAction))) == []
        assert calendar == {r.id: r.data for r in db.scalars(select(CalendarRow))}
        assert db.scalar(
            select(Proposal).where(Proposal.work_order_id == ctx.order_id)
        ).clarification


def test_customer_promised_later_does_not_trigger_immediate_repeat(partial_order):
    process(partial_order, deferred=True)
    with partial_order.factory() as db:
        assert (
            db.scalar(select(ActionRow).where(ActionRow.work_order_id == partial_order.order_id))
            is None
        )
        # Recognition does not grant the model permission to apply a formal deferral.
        assert not db.get(WorkOrderRow, partial_order.order_id).data.get("deferred")


def test_bad_assessment_keeps_extraction_and_template_fallback(partial_order):
    process(partial_order, malformed=True)
    with partial_order.factory.begin() as db:
        p = db.scalar(select(Proposal).where(Proposal.work_order_id == partial_order.order_id))
        assert p.clarification is None
        order = db.get(WorkOrderRow, partial_order.order_id)
        conv = db.get(ConversationRow, partial_order.conversation_id)
        draft = ask_open_items(db, order.account_id, order, conv)
        assert draft and "哪天几点方便" in draft["body"]


@pytest.mark.parametrize("change", ["edit", "revoke", "pause", "new_context", "other_order"])
def test_analysis_cannot_survive_changed_sources_or_cross_order_binding(partial_order, change):
    ctx = partial_order
    process(ctx)
    with ctx.factory.begin() as db:
        order = db.get(WorkOrderRow, ctx.order_id)
        conv = db.get(ConversationRow, ctx.conversation_id)
        p = db.scalar(select(Proposal).where(Proposal.work_order_id == ctx.order_id))
        ref = p.clarification["assessment"]["facts"][0]["evidence"][0]["source"]
        row = db.get(MessageRow, (ref["message_id"], 1))
        if change == "edit":
            db.add(
                MessageRow(
                    id=row.id,
                    revision=2,
                    account_id=row.account_id,
                    conversation_id=row.conversation_id,
                    provider_message_id=row.provider_message_id,
                    data={**row.data, "text": "周日"},
                )
            )
        elif change == "revoke":
            row.data = {**row.data, "revoked": True}
        elif change == "pause":
            conv.allowlisted = False
        elif change == "new_context":
            conv.context_version += 1
        else:
            order = db.get(WorkOrderRow, uid(3))
        db.flush()
        items, questions = open_items(order.data)
        assert reply_plan(db, order.account_id, order, conv, items, questions) is None


def test_explicit_new_order_adoption_can_use_the_analysis(partial_order):
    ctx = partial_order
    process(ctx)
    with ctx.factory.begin() as db:
        p = db.scalar(select(Proposal).where(Proposal.work_order_id == ctx.order_id))
        p.work_order_id, p.assignment, p.base_work_order_version = None, "needs_review", None
        db.add(
            ProposalDecision(
                event_id=p.event_id,
                proposal_id=p.id,
                account_id=p.account_id,
                work_order_id=ctx.order_id,
            )
        )
        db.flush()
        order = db.get(WorkOrderRow, ctx.order_id)
        conv = db.get(ConversationRow, ctx.conversation_id)
        plan = reply_plan(db, order.account_id, order, conv, *open_items(order.data))
        assert plan and plan[0] == ["missing_duration"]


def test_original_confirmed_interval_survives_a_partial_amendment(partial_order):
    ctx = partial_order
    with ctx.factory.begin() as db:
        order = db.get(WorkOrderRow, ctx.order_id)
        original = copy.deepcopy(db.get(WorkOrderRow, uid(3)).data["fields"]["schedule"])
        order.data = {
            **order.data,
            "status": "confirmed",
            "fields": {**order.data["fields"], "schedule": original},
        }
    process(ctx)
    with ctx.factory() as db:
        order = db.get(WorkOrderRow, ctx.order_id)
        assert order.data["fields"]["schedule"] == original
        draft = db.scalar(select(ActionRow).where(ActionRow.work_order_id == ctx.order_id))
        assert draft and "持续多久" in draft.data["body"]


def test_new_duration_code_is_a_schedule_item():
    assert field_for_code("missing_duration") == "schedule"
    assert field_for_code("clarify_start_time") == "schedule"
    assert field_for_code("clarify_address") == "address"
    assert field_for_code("unknown") is None


def test_date_only_order_retains_known_start_from_the_ai_assessment(partial_order):
    ctx = partial_order
    with ctx.factory.begin() as db:
        order = db.get(WorkOrderRow, ctx.order_id)
        fields = copy.deepcopy(order.data["fields"])
        fields["schedule"] = {
            "value": {"kind": "date_only", "date": "2026-10-31", "timezone": "Asia/Hong_Kong"},
            "status": "proposed",
            "sources": [],
            "interpretation": None,
        }
        order.data = {**order.data, "fields": fields}
    process(ctx)
    with ctx.factory() as db:
        action = db.scalar(select(ActionRow).where(ActionRow.work_order_id == ctx.order_id))
        assert action and "持续多久" in action.data["body"]
        assert "几点方便" not in action.data["body"]


def test_full_confirmed_time_is_not_asked_again(partial_order):
    ctx = partial_order
    process(ctx)
    with ctx.factory.begin() as db:
        order = db.get(WorkOrderRow, ctx.order_id)
        original = copy.deepcopy(db.get(WorkOrderRow, uid(3)).data["fields"]["schedule"])
        original["status"] = "confirmed"
        order.data = {
            **order.data,
            "version": 2,
            "fields": {**order.data["fields"], "schedule": original},
        }
        conv = db.get(ConversationRow, ctx.conversation_id)
        plan = reply_plan(db, order.account_id, order, conv, *open_items(order.data))
        assert plan is not None and not plan[0]


def test_explicit_deferral_handles_duration_code_and_suppresses_the_question(partial_order):
    from gigmate.workorders import defer_item

    ctx = partial_order
    process(ctx)
    with ctx.factory.begin() as db:
        order = db.get(WorkOrderRow, ctx.order_id)
        draft = db.scalar(select(ActionRow).where(ActionRow.work_order_id == order.id))
        command = DeferItemCommand(
            field="schedule", expected_version=1, sources=draft.data["sources"]
        )
        result = defer_item(
            db,
            db.get(Account, order.account_id),
            order.id,
            command,
            str(uuid4()),
            str(uuid4()),
        )
        assert "schedule" in result["deferred"]
        assert draft.data["state"] == "cancelled"


def test_own_api_echo_retains_partial_facts_but_new_customer_message_does_not(partial_order):
    ctx = partial_order
    process(ctx)
    with ctx.factory.begin() as db:
        conv = db.get(ConversationRow, ctx.conversation_id)
        conv.context_version += 1
        db.add(
            Inbox(
                id=str(uuid4()),
                account_id=ctx.binding.account_id,
                payload={"conversation_id": conv.id, "direction": "outgoing", "source": "api"},
                digest="synthetic-echo",
                context_version=conv.context_version,
                received_at=datetime.now(UTC),
            )
        )
        db.flush()
        order = db.get(WorkOrderRow, ctx.order_id)
        plan = reply_plan(db, order.account_id, order, conv, *open_items(order.data))
        assert plan and plan[0] == ["missing_duration"]


def test_memory_survives_recent_window_and_is_scoped_to_one_order(partial_order):
    ctx = partial_order
    process(ctx)
    with ctx.factory.begin() as db:
        # Current source revisions remain available even when their timestamps
        # no longer fit the five-minute recent-bubble window.
        p = db.scalar(select(Proposal).where(Proposal.work_order_id == ctx.order_id))
        ref = p.clarification["assessment"]["facts"][0]["evidence"][0]["source"]
        message = db.get(MessageRow, (ref["message_id"], 1))
        message.data = {
            **message.data,
            "occurred_at": (datetime.now(UTC) - timedelta(minutes=10))
            .isoformat()
            .replace("+00:00", "Z"),
        }
        conv = db.get(ConversationRow, ctx.conversation_id)
        conv.context_version += 1
        db.flush()
        remembered = memory_for(db, ctx.binding.account_id, conv, [ctx.order_id])
        assert remembered and remembered[0]["work_order_id"] == ctx.order_id
        assert memory_for(db, ctx.binding.account_id, conv, [uid(3)]) == ()
        current = request("2小时")
        current = replace(current, clarification_context=remembered)
        raw = copy.deepcopy(p.clarification["assessment"])
        raw["facts"][3] = {
            "item": "duration",
            "state": "known",
            "text": "2小时",
            "evidence": [
                {
                    "source": {"message_id": current.message_id, "message_revision": 1},
                    "quote": "2小时",
                }
            ],
        }
        raw["questions"] = []
        assert parse_assessment(raw, current, ctx.order_id) is not None
        assert parse_assessment(raw, current, uid(3)) is None
        assert parse_assessment(raw, current) is None  # A new job cannot inherit old facts.
        message.data = {**message.data, "revoked": True}
        db.flush()
        assert memory_for(db, ctx.binding.account_id, conv, [ctx.order_id]) == ()


def test_schema_matches_exported_clarification_contract():
    import json
    from pathlib import Path

    from gigmate.clarification import Assessment

    path = Path(__file__).resolve().parents[3] / "contracts/ai/clarification-assessment.schema.json"
    exported = json.loads(path.read_text(encoding="utf-8"))
    expected = Assessment.model_json_schema()
    assert all(exported[k] == v for k, v in expected.items())


@pytest.mark.parametrize("invalid", [False, True])
def test_provider_extracts_nested_assessment_without_changing_domain_contract(invalid):
    import time

    from gigmate.extraction.llm import LLMProvider

    req = request()
    raw = assessment(req)
    if invalid:
        raw["questions"] = []
    payload = {
        "assignment": "needs_review",
        "base_context_version": req.context_version,
        "changes": [],
        "candidates": [],
        "unresolved_questions": ["Review fictional request"],
        "new_work_order": {
            "summary": "Fictional photography",
            "fields": [],
            "missing_fields": ["start_time", "duration", "address"],
            "unresolved_questions": [],
            "confidence": 0.8,
        },
        "clarification": raw,
    }
    result = LLMProvider()._parse_response(
        payload, req, time.monotonic(), "1.8.0", "synthetic:mock"
    )
    assert result.proposal.new_work_order.missing_fields == ["schedule", "address"]
    assert "llm:missing-field-normalized" in result.notes
    assert bool(result.clarification) == (not invalid)
    assert "clarification" not in result.proposal.model_dump()
    if invalid:
        assert "clarification:invalid" in result.notes


@pytest.mark.parametrize("ask_duration", [False, True])
def test_ai_can_prioritize_independent_duration_without_reasking_deferred_start(ask_duration):
    req = request("周六，开始时间我稍后确认，地址稍后发")
    raw = assessment(req)
    raw["facts"][1] = {
        "item": "start_time",
        "state": "deferred",
        "text": None,
        "evidence": [
            {
                "source": {"message_id": req.message_id, "message_revision": 1},
                "quote": "开始时间我稍后确认",
            }
        ],
    }
    raw["questions"] = ["duration"] if ask_duration else []
    result = parse_assessment(raw, req)
    assert result is not None and "start_time" not in result["questions"]


def test_ai_reply_is_visible_approvable_and_invalidated_by_customer_edit(partial_order):
    ctx = partial_order
    process(ctx)
    client, _, _, headers, _, _ = ctx.ingress
    with ctx.factory() as db:
        action = db.scalar(select(ActionRow).where(ActionRow.work_order_id == ctx.order_id))
        data = copy.deepcopy(action.data)
    view = client.get(f"/api/v1/actions/{data['id']}")
    assert view.status_code == 200
    assert "missing_duration" in view.json()["data"]["open_items"]
    command = {
        "expected_version": data["bound_work_order_version"],
        "expected_context_version": data["bound_context_version"],
        "expected_action_revision": data["revision"],
        "snapshot_hash": data["snapshot_hash"],
    }
    response = client.post(
        f"/api/v1/actions/{data['id']}/approve",
        json=command,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    with ctx.factory() as db:
        assert list(db.scalars(select(WahaSendAction))) == []
    submit(ctx, *event(ctx, body="改成周日，时间尚未确定", kind="message.edited", seconds=6))
    with ctx.factory() as db:
        assert db.get(ActionRow, data["id"]).data["state"] == "cancelled"


def test_adopted_date_only_request_respects_deferred_start_after_other_field_changes(partial_order):
    from gigmate.db import CommandResult

    ctx = partial_order
    process(ctx)
    with ctx.factory.begin() as db:
        p = db.scalar(select(Proposal).where(Proposal.work_order_id == ctx.order_id))
        ref = p.clarification["assessment"]["facts"][0]["evidence"][0]["source"]
        message = db.get(MessageRow, (ref["message_id"], 1))
        message.data = {**message.data, "text": "周六，开始时间我稍后确认，地址稍后发"}
        req = request(message.data["text"])
        req = replace(req, message_id=message.id)
        raw = assessment(req)
        raw["facts"][1] = {
            "item": "start_time",
            "state": "deferred",
            "text": None,
            "evidence": [{"source": ref, "quote": "开始时间我稍后确认"}],
        }
        raw["questions"] = []
        assert parse_assessment(raw, req)
        p.clarification = {"assessment": raw, "basis": {}}
        p.work_order_id, p.assignment, p.base_work_order_version, p.changes = (
            None,
            "needs_review",
            None,
            [],
        )
        db.add(
            ProposalDecision(
                event_id=p.event_id,
                proposal_id=p.id,
                account_id=p.account_id,
                work_order_id=ctx.order_id,
            )
        )
        order = db.get(WorkOrderRow, ctx.order_id)
        fields = copy.deepcopy(order.data["fields"])
        fields["schedule"] = {
            "value": {"kind": "date_only", "date": "2026-10-31", "timezone": "Asia/Hong_Kong"},
            "status": "proposed",
            "sources": [ref],
            "interpretation": None,
        }
        order.data = {**order.data, "fields": fields}
        db.flush()
        conv = db.get(ConversationRow, ctx.conversation_id)
        assert reply_plan(db, order.account_id, order, conv, *open_items(order.data))[0] == []

        # Immutable creation receipt preserves the reviewed basis after an
        # unrelated merchant edit, without mutating old proposal evidence.
        db.add(
            CommandResult(
                id=str(uuid4()),
                account_id=order.account_id,
                scope="create_work_order",
                key=str(uuid4()),
                digest="synthetic",
                data=copy.deepcopy(order.data),
            )
        )
        fields = copy.deepcopy(fields)
        fields["address"] = {
            "value": "虚构场地A",
            "status": "confirmed",
            "sources": [ref],
            "interpretation": None,
        }
        order.data = {**order.data, "version": 2, "fields": fields}
        db.flush()
        assert reply_plan(db, order.account_id, order, conv, *open_items(order.data))[0] == []


def test_derived_end_is_not_mistaken_for_a_customer_quote():
    req = request("周六下午3点开始，预计2小时，地址稍后发")
    raw = assessment(req)
    ref = {"message_id": req.message_id, "message_revision": 1}
    raw["facts"][2] = {
        "item": "end_time",
        "state": "known",
        "text": "下午5点",
        "evidence": [{"source": ref, "quote": "下午3点开始，预计2小时"}],
    }
    raw["facts"][3] = {
        "item": "duration",
        "state": "known",
        "text": "2小时",
        "evidence": [{"source": ref, "quote": "预计2小时"}],
    }
    raw["questions"] = []
    result = parse_assessment(raw, req)
    assert result and result["facts"][2]["state"] == "missing"
    assert result["facts"][3]["state"] == "known"
    assert result["questions"] == []
    raw["facts"][2]["evidence"][0]["source"]["message_id"] = str(uuid4())
    assert parse_assessment(raw, req) is None


def test_invalid_incomplete_interval_can_keep_independent_clarification():
    import time

    from gigmate.extraction.llm import LLMProvider

    req = replace(
        request(), message_received_at="2026-10-23T01:00:00Z", workspace_timezone="Asia/Hong_Kong"
    )
    payload = {
        "assignment": "needs_review",
        "base_context_version": 1,
        "changes": [],
        "candidates": [],
        "unresolved_questions": [],
        "new_work_order": {
            "summary": "Fictional photography",
            "fields": [
                {
                    "field": "schedule",
                    "value": {
                        "kind": "timed",
                        "start_at": "2026-10-24T07:00:00Z",
                        "timezone": "Asia/Hong_Kong",
                    },
                    "sources": [{"message_id": req.message_id, "message_revision": 1}],
                    "reason": "Partial start only",
                }
            ],
            "missing_fields": ["schedule"],
            "unresolved_questions": [],
            "confidence": 0.8,
        },
        "clarification": assessment(req),
    }
    result = LLMProvider()._parse_response(
        payload, req, time.monotonic(), "1.8.0", "synthetic:mock"
    )
    assert result.proposal.new_work_order and result.proposal.new_work_order.fields == []
    assert result.clarification and result.clarification["questions"] == ["duration"]
    assert "llm:partial-time-kept-for-clarification" in result.notes


def test_newer_assessment_cannot_extend_older_source_text_retention(partial_order):
    from gigmate.waha_ingress import purge_expired

    ctx = partial_order
    process(ctx)
    with ctx.factory.begin() as db:
        proposal = db.scalar(select(Proposal).where(Proposal.work_order_id == ctx.order_id))
        ref = proposal.clarification["assessment"]["facts"][0]["evidence"][0]["source"]
        message = db.get(MessageRow, (ref["message_id"], 1))
        message.data = {
            **message.data,
            "occurred_at": (datetime.now(UTC) - timedelta(days=31))
            .isoformat()
            .replace("+00:00", "Z"),
        }
        purge_expired(db, ctx.binding.connection_id)
        assert db.get(Proposal, proposal.id) is not None
        assert proposal.clarification is None
        assert message.data["text"] is None


def test_reauthorization_does_not_reopen_old_partial_facts(partial_order):
    ctx = partial_order
    process(ctx)
    with ctx.factory.begin() as db:
        conv = db.get(ConversationRow, ctx.conversation_id)
        conv.context_version += 2  # revoke and regrant, with no new customer text
        conv.consent_context_version = conv.context_version
        db.flush()
        assert memory_for(db, ctx.binding.account_id, conv, [ctx.order_id]) == ()
        order = db.get(WorkOrderRow, ctx.order_id)
        assert reply_plan(db, order.account_id, order, conv, *open_items(order.data)) is None


def test_memory_only_request_does_not_rebind_a_foreign_source_to_new_job():
    from gigmate.extraction.llm import LLMProvider

    req = replace(request(), clarification_context=({"work_order_id": uid(3)},))
    foreign = {"message_id": str(uuid4()), "message_revision": 1}
    original = foreign.copy()
    problem, rebound = LLMProvider._bind_source(foreign, req)
    assert problem == "llm:response-provenance-failed:source-message-id"
    assert not rebound and foreign == original
