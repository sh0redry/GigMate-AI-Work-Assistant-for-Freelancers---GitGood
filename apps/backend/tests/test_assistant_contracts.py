"""Batch 0 of the bounded assistant (ADR 0011): contracts only, no route or provider."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gigmate.api import app
from gigmate.assistant_plan import ALLOWED_TOOLS, AssistantComposition, AssistantPlan
from gigmate.contracts import (
    AssistantAnswer,
    AssistantCitation,
    AssistantContext,
    AssistantTurnCommand,
    AssistantTurnView,
)

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "contracts/examples"
CONV = "00000000-0000-4000-8000-0000000a0001"
ORDER = "00000000-0000-4000-8000-0000000a0002"
MSG = "00000000-0000-4000-8000-0000000a0003"


def plan(**changes):
    value = {
        "schema_version": "1.0.0",
        "intent": "availability",
        "language": "zh-Hans",
        "tool_calls": [
            {
                "tool": "find_free_slots",
                "duration_minutes": 120,
                "from_date": "2026-11-30",
                "to_date": "2026-12-06",
            }
        ],
    }
    value.update(changes)
    # Providers return JSON; validate exactly as the future seam will.
    return AssistantPlan.model_validate_json(json.dumps(value))


def composition(**changes):
    value = {
        "schema_version": "1.0.0",
        "kind": "reply_draft",
        "language": "zh-Hans",
        "text": "您好，周二下午可以安排。",
        "sources": [{"message_id": MSG, "message_revision": 1}],
    }
    value.update(changes)
    return AssistantComposition.model_validate_json(json.dumps(value))


def test_valid_availability_plan_requests_only_a_read_tool():
    result = plan()
    assert result.intent == "availability"
    assert [call.tool for call in result.tool_calls] == ["find_free_slots"]


@pytest.mark.parametrize(
    "tool",
    [
        {"tool": "send_message", "target": "selected", "text": "好的"},
        {"tool": "confirm_field", "target": "selected", "field": "address"},
        {"tool": "approve_action", "target": "selected"},
    ],
)
def test_no_write_or_send_tool_exists(tool):
    with pytest.raises(ValidationError):
        plan(intent="reply_draft", tool_calls=[tool])


def test_tools_must_match_the_intent_allowlist():
    # polish may read the conversation only; it cannot look at the calendar.
    with pytest.raises(ValidationError, match="not allowed for intent polish"):
        plan(
            intent="polish",
            tool_calls=[
                {
                    "tool": "find_free_slots",
                    "duration_minutes": 60,
                    "from_date": "2026-11-30",
                    "to_date": "2026-11-30",
                }
            ],
        )
    assert ALLOWED_TOOLS["clarify"] == frozenset()
    assert ALLOWED_TOOLS["unsupported"] == frozenset()


def test_tools_cannot_be_pointed_at_model_chosen_ids():
    # A prompt-injected message must not be able to redirect a tool to another chat or order.
    for call in (
        {"tool": "read_conversation", "target": CONV},
        {"tool": "get_work_order", "target": ORDER},
        {"tool": "get_work_order", "target": "selected", "work_order_id": ORDER},
    ):
        with pytest.raises(ValidationError):
            plan(intent="reply_draft", tool_calls=[call])


@pytest.mark.parametrize(
    ("start", "end"),
    [("2026-12-06", "2026-11-30"), ("2026-11-01", "2026-12-15")],
)
def test_free_slot_window_is_bounded(start, end):
    with pytest.raises(ValidationError, match="slot window"):
        plan(
            tool_calls=[
                {
                    "tool": "find_free_slots",
                    "duration_minutes": 60,
                    "from_date": start,
                    "to_date": end,
                }
            ]
        )


def test_at_most_three_tool_calls():
    call = {"tool": "list_work_orders", "status": "open", "scope": "account"}
    plan(intent="order_status", tool_calls=[call] * 3)
    with pytest.raises(ValidationError):
        plan(intent="order_status", tool_calls=[call] * 4)


def test_clarification_rules():
    asked = plan(intent="clarify", tool_calls=[], clarification_question="是哪一张工单？")
    assert asked.clarification_question
    with pytest.raises(ValidationError, match="requires clarification_question"):
        plan(intent="clarify", tool_calls=[])
    with pytest.raises(ValidationError, match="only for intent clarify"):
        plan(clarification_question="是哪一张工单？")
    with pytest.raises(ValidationError, match="requires at least one read tool"):
        plan(tool_calls=[])


@pytest.mark.parametrize(
    "extra",
    [{"execution_authority": True}, {"answer": "周二有空"}, {"schema_version": "2.0.0"}],
)
def test_plan_rejects_authority_free_text_and_unknown_versions(extra):
    with pytest.raises(ValidationError):
        plan(**extra)


def test_reply_draft_must_cite_customer_revisions():
    assert composition().sources[0].message_revision == 1
    with pytest.raises(ValidationError, match="must cite"):
        composition(sources=[])
    assert composition(kind="polish", sources=[]).kind == "polish"
    with pytest.raises(ValidationError, match="duplicate source"):
        composition(sources=[{"message_id": MSG, "message_revision": 1}] * 2)


@pytest.mark.parametrize(
    "extra",
    [{"recipient": "synthetic:1@c.us"}, {"approved": True}, {"send": True}, {"text": ""}],
)
def test_composition_cannot_carry_sending_fields(extra):
    with pytest.raises(ValidationError):
        composition(**extra)


def test_context_bindings_travel_with_their_versions():
    AssistantContext()
    AssistantContext(conversation_id=CONV, expected_context_version=0)
    with pytest.raises(ValidationError, match="expected_context_version"):
        AssistantContext(conversation_id=CONV)
    with pytest.raises(ValidationError, match="expected_work_order_version"):
        AssistantContext(work_order_id=ORDER)
    with pytest.raises(ValidationError, match="require a selected conversation"):
        AssistantContext(selected_sources=[{"message_id": MSG, "message_revision": 1}])
    with pytest.raises(ValidationError):
        AssistantTurnCommand(question="")


def test_answers_never_carry_execution_authority():
    with pytest.raises(ValidationError):
        AssistantAnswer(kind="slots", text="周二有空", execution_authority=True)
    with pytest.raises(ValidationError, match="exactly one draft"):
        AssistantAnswer(kind="draft", text="草稿已准备")
    with pytest.raises(ValidationError, match="exactly one draft"):
        AssistantAnswer(kind="slots", text="周二有空", draft_id=ORDER)


def test_citation_shapes():
    AssistantCitation(kind="free_slots")
    AssistantCitation(kind="message", message={"message_id": MSG, "message_revision": 2})
    AssistantCitation(kind="work_order", work_order_id=ORDER, work_order_version=3)
    with pytest.raises(ValidationError):
        AssistantCitation(kind="message")
    with pytest.raises(ValidationError):
        AssistantCitation(kind="work_order", work_order_id=ORDER)
    with pytest.raises(ValidationError):
        AssistantCitation(kind="free_slots", work_order_id=ORDER, work_order_version=1)


FIXTURE_MODELS = {
    "AssistantTurnCommand": AssistantTurnCommand,
    "AssistantTurnView": AssistantTurnView,
    "AssistantAnswer": AssistantAnswer,
    "assistant-plan.schema.json": AssistantPlan,
    "assistant-composition.schema.json": AssistantComposition,
}


def assistant_fixtures():
    manifest = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))
    return [item for item in manifest["fixtures"] if "assistant" in item["file"]]


def test_assistant_fixtures_cross_validate_with_the_source_models():
    fixtures = assistant_fixtures()
    assert len(fixtures) == 7
    for item in fixtures:
        model = FIXTURE_MODELS[item["schema"].rsplit("/", 1)[-1]]
        raw = (EXAMPLES / item["file"]).read_text(encoding="utf-8")
        if item["valid"]:
            model.model_validate_json(raw)
        else:
            with pytest.raises(ValidationError):
                model.model_validate_json(raw)


def test_batch_zero_adds_no_route():
    paths = app.openapi()["paths"]
    assert not [path for path in paths if "assistant" in path]
