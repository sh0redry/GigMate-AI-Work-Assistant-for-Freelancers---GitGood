"""Bounded assistant turns, batch 1 (ADR 0011): durable, owned, read-only, offline.

Synthetic data only. No model, network, WhatsApp or sending is involved.
"""

import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from gigmate import assistant, assistant_tools
from gigmate.assistant_plan import ReadConversation
from gigmate.db import (
    AgentDraftRow,
    AssistantTurn,
    ChangeRow,
    ConversationOrder,
    ConversationRow,
    Inbox,
    MessageRow,
    WahaSendAction,
    WorkOrderRow,
)
from gigmate.seed import uid

CONV, ORDER, MESSAGE = uid(2), uid(3), uid(5)
OTHER_CONV, OTHER_ORDER = uid(22), uid(23)


def ask(client, headers, question, context=None, key=None, thread_id=None):
    body = {"question": question}
    if context is not None:
        body["context"] = context
    if thread_id:
        body["thread_id"] = thread_id
    return client.post(
        "/api/v1/assistant/turns",
        json=body,
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def selected(**extra):
    return {"conversation_id": CONV, "expected_context_version": 4, **extra}


def turn_row(factory, turn_id):
    with factory() as db:
        return db.get(AssistantTurn, turn_id)


def app_message(db, conversation_id, at, text, *, revision=1, revoked=False, context_version=1):
    """A consented live message: an accepted inbox event plus its revision."""
    message_id = str(uuid4())
    db.add(
        Inbox(
            id=str(uuid4()),
            account_id=uid(1),
            payload={
                "conversation_id": conversation_id,
                "payload": {"message_id": message_id},
                "message_revision": revision,
            },
            digest="0" * 64,
            context_version=context_version,
            received_at=at,
        )
    )
    db.add(
        MessageRow(
            id=message_id,
            revision=revision,
            account_id=uid(1),
            conversation_id=conversation_id,
            provider_message_id="synthetic:" + message_id,
            data={
                "id": message_id,
                "text": text,
                "direction": "incoming",
                "source": "app",
                "revoked": revoked,
                "occurred_at": at.isoformat().replace("+00:00", "Z"),
            },
        )
    )
    db.flush()
    return message_id


class Fixed:
    engine = "rules"

    def __init__(self, plan=None, error=None):
        self.value, self.error, self.calls = plan, error, 0

    def plan(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return json.dumps(self.value)


def test_availability_turn_answers_from_server_slots(signed_in):
    client, factory, _engine, headers = signed_in
    response = ask(client, headers, "下周哪几天有空？要2小时")
    assert response.status_code == 202, response.text
    queued = response.json()["data"]
    assert queued["status"] == "queued" and queued["answer"] is None
    assert assistant.run_once(factory) is True
    done = client.get(f"/api/v1/assistant/turns/{queued['id']}").json()["data"]
    assert done["status"] == "completed"
    assert (done["intent"], done["engine"]) == ("availability", "rules")
    answer = done["answer"]
    assert answer["kind"] == "slots" and answer["execution_authority"] is False
    assert answer["citations"] == [
        {"kind": "free_slots", "message": None, "work_order_id": None, "work_order_version": None}
    ]
    for slot in answer["slots"]:
        start = datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(slot["end_at"].replace("Z", "+00:00"))
        assert end - start >= timedelta(hours=2)
        assert slot["label"] in answer["text"]
    assert turn_row(factory, queued["id"]).trace == {
        "tools": ["find_free_slots"],
        "language": "zh-Hans",
    }


def test_order_status_lists_only_the_merchants_own_open_orders(signed_in):
    client, factory, _engine, headers = signed_in
    turn = ask(client, headers, "我现在有哪些订单？").json()["data"]
    assistant.run_once(factory)
    answer = client.get(f"/api/v1/assistant/turns/{turn['id']}").json()["data"]["answer"]
    assert answer["kind"] == "orders"
    with factory() as db:
        own_open = sorted(
            row.id
            for row in db.scalars(select(WorkOrderRow).where(WorkOrderRow.account_id == uid(1)))
            if row.data.get("status") in assistant_tools.OPEN
        )
    assert ORDER in own_open
    assert answer["work_order_ids"] == own_open
    assert OTHER_ORDER not in json.dumps(answer)
    assert {"kind": "work_order", "work_order_id": ORDER, "work_order_version": 3} in [
        {k: v for k, v in c.items() if v is not None} for c in answer["citations"]
    ]


def test_idempotent_submission_and_changed_reuse(signed_in):
    client, factory, _engine, headers = signed_in
    first = ask(client, headers, "我有哪些订单？", key="assistant-key-1")
    again = ask(client, headers, "我有哪些订单？", key="assistant-key-1")
    assert first.status_code == again.status_code == 202
    assert first.json()["data"]["id"] == again.json()["data"]["id"]
    changed = ask(client, headers, "下周有空吗？", key="assistant-key-1")
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    with factory() as db:
        assert db.scalar(select(func.count(AssistantTurn.id))) == 1


@pytest.mark.parametrize(
    ("context", "status", "code"),
    [
        ({"conversation_id": OTHER_CONV, "expected_context_version": 4}, 404, "NOT_FOUND"),
        (
            {"work_order_id": OTHER_ORDER, "expected_work_order_version": 3},
            404,
            "NOT_FOUND",
        ),
        (selected(expected_context_version=3), 409, "ASSISTANT_CONTEXT_STALE"),
        (
            {"work_order_id": ORDER, "expected_work_order_version": 2},
            409,
            "ASSISTANT_CONTEXT_STALE",
        ),
        (
            selected(selected_sources=[{"message_id": MESSAGE, "message_revision": 1}]),
            409,
            "ASSISTANT_SOURCE_STALE",
        ),
    ],
)
def test_selection_is_owned_current_and_consented(signed_in, context, status, code):
    client, factory, _engine, headers = signed_in
    response = ask(client, headers, "帮我回一下", context)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    with factory() as db:
        assert db.scalar(select(func.count(AssistantTurn.id))) == 0


def test_unlinked_order_and_paused_chat_are_refused(signed_in):
    client, factory, _engine, headers = signed_in
    with factory.begin() as db:
        order = db.get(WorkOrderRow, ORDER)
        db.add(WorkOrderRow(id=uid(77), account_id=uid(1), data={**order.data, "id": uid(77)}))
    mismatch = ask(
        client, headers, "看看工单", selected(work_order_id=uid(77), expected_work_order_version=3)
    )
    assert mismatch.json()["error"]["code"] == "ASSISTANT_SELECTION_MISMATCH"
    with factory.begin() as db:
        db.get(ConversationRow, CONV).allowlisted = False
    paused = ask(client, headers, "帮我回一下", selected())
    assert paused.status_code == 403 and paused.json()["error"]["code"] == "CONSENT_REVOKED"


def test_a_consented_current_source_can_be_selected(signed_in):
    client, factory, _engine, headers = signed_in
    with factory.begin() as db:
        message = app_message(db, CONV, datetime.now(UTC), "周二下午可以吗？")
    response = ask(
        client,
        headers,
        "帮我回一下这条",
        selected(selected_sources=[{"message_id": message, "message_revision": 1}]),
    )
    assert response.status_code == 202, response.text


def test_changed_conversation_supersedes_a_queued_turn(signed_in):
    client, factory, _engine, headers = signed_in
    turn = ask(client, headers, "帮我回一下", selected()).json()["data"]
    with factory.begin() as db:
        db.get(ConversationRow, CONV).context_version = 5
    assistant.run_once(factory)
    done = client.get(f"/api/v1/assistant/turns/{turn['id']}").json()["data"]
    assert (done["status"], done["error_code"]) == ("superseded", "ASSISTANT_CONTEXT_STALE")
    assert done["answer"] is None


def test_expired_lease_becomes_unknown_and_is_never_retried(signed_in):
    client, factory, _engine, headers = signed_in
    turn = ask(client, headers, "我有哪些订单？").json()["data"]
    with factory.begin() as db:
        row = db.get(AssistantTurn, turn["id"])
        row.state, row.lease_token = "running", str(uuid4())
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    planner = Fixed(error=AssertionError("must not plan"))
    assert assistant.run_once(factory, planner=planner) is True
    assert assistant.run_once(factory, planner=planner) is False
    row = turn_row(factory, turn["id"])
    assert (row.state, row.error_code, planner.calls) == (
        "unknown",
        "ASSISTANT_RESULT_UNKNOWN",
        0,
    )


@pytest.mark.parametrize(
    ("planner", "state", "code"),
    [
        (Fixed(error=assistant.PlannerUnavailable()), "failed", "ASSISTANT_DISABLED"),
        (
            Fixed(
                {
                    "schema_version": "1.0.0",
                    "intent": "reply_draft",
                    "language": "zh-Hans",
                    "tool_calls": [{"tool": "send_message", "target": "selected"}],
                }
            ),
            "failed",
            "ASSISTANT_PLAN_INVALID",
        ),
        (Fixed(error=TimeoutError()), "unknown", "ASSISTANT_RESULT_UNKNOWN"),
    ],
)
def test_planner_failures_are_stable_and_not_retried(signed_in, planner, state, code):
    client, factory, _engine, headers = signed_in
    turn = ask(client, headers, "下周有空吗").json()["data"]
    assistant.run_once(factory, planner=planner)
    assert assistant.run_once(factory, planner=planner) is False
    row = turn_row(factory, turn["id"])
    assert (row.state, row.error_code, row.answer) == (state, code, None)
    assert planner.calls == 1


def test_a_lost_lease_never_writes_a_result(signed_in):
    client, factory, _engine, headers = signed_in
    turn = ask(client, headers, "我有哪些订单？").json()["data"]

    class Stolen(Fixed):
        def plan(self, request):
            with factory.begin() as db:
                db.get(AssistantTurn, turn["id"]).lease_token = str(uuid4())
            return super().plan(request)

    plan = {
        "schema_version": "1.0.0",
        "intent": "order_status",
        "language": "zh-Hans",
        "tool_calls": [{"tool": "list_work_orders"}],
    }
    assistant.run_once(factory, planner=Stolen(plan))
    row = turn_row(factory, turn["id"])
    assert (row.state, row.answer) == ("running", None)


def test_a_second_worker_does_not_pick_up_a_turn_in_progress(signed_in):
    client, factory, _engine, headers = signed_in
    ask(client, headers, "我有哪些订单？")
    entered, release = threading.Event(), threading.Event()

    class Slow(Fixed):
        def plan(self, request):
            entered.set()
            release.wait(10)
            return super().plan(request)

    slow = Slow(
        {
            "schema_version": "1.0.0",
            "intent": "order_status",
            "language": "zh-Hans",
            "tool_calls": [{"tool": "list_work_orders"}],
        }
    )
    worker = threading.Thread(target=assistant.run_once, args=(factory,), kwargs={"planner": slow})
    worker.start()
    assert entered.wait(10)
    second = Fixed(error=AssertionError("must not plan"))
    assert assistant.run_once(factory, planner=second) is False
    release.set()
    worker.join(10)
    assert second.calls == 0 and slow.calls == 1


def test_reply_needs_a_selected_chat_and_never_invents_content(signed_in):
    client, factory, _engine, headers = signed_in
    unselected = ask(client, headers, "帮我回一下客户").json()["data"]
    assistant.run_once(factory)
    answer = client.get(f"/api/v1/assistant/turns/{unselected['id']}").json()["data"]["answer"]
    assert answer["kind"] == "clarification" and "选择" in answer["text"]
    chosen = ask(client, headers, "帮我回一下客户", selected()).json()["data"]
    assistant.run_once(factory)
    done = client.get(f"/api/v1/assistant/turns/{chosen['id']}").json()["data"]
    assert done["intent"] == "reply_draft"
    # Without dictated content the offline composer asks what to say instead of inventing it.
    assert done["answer"]["kind"] == "clarification" and done["answer"]["draft_id"] is None
    assert turn_row(factory, chosen["id"]).trace["tools"] == ["read_conversation"]


def test_tools_refuse_objects_the_merchant_did_not_select(signed_in):
    client, factory, _engine, headers = signed_in
    turn = ask(client, headers, "看看这张工单").json()["data"]
    plan = {
        "schema_version": "1.0.0",
        "intent": "order_status",
        "language": "zh-Hans",
        "tool_calls": [{"tool": "get_work_order", "target": "selected"}],
    }
    assistant.run_once(factory, planner=Fixed(plan))
    done = client.get(f"/api/v1/assistant/turns/{turn['id']}").json()["data"]
    assert (done["status"], done["intent"]) == ("completed", "clarify")
    assert done["answer"]["kind"] == "clarification"
    assert turn_row(factory, turn["id"]).trace["tools"] == ["refused:ASSISTANT_SELECTION_REQUIRED"]


def test_read_conversation_is_bounded_and_carries_no_provider_ids(signed_in):
    _client, factory, _engine, _headers = signed_in
    now = datetime.now(UTC)
    with factory.begin() as db:
        conversation = db.get(ConversationRow, CONV)
        kept = [
            app_message(db, CONV, now - timedelta(seconds=20 * i), f"消息 {i}") for i in range(10)
        ]
        app_message(db, CONV, now - timedelta(minutes=9), "太早的消息")
        app_message(db, CONV, now + timedelta(seconds=1), "已撤回", revoked=True)
        app_message(db, OTHER_CONV, now, "另一个会话")
        scope = assistant_tools.Scope(account_id=uid(1), conversation=conversation)
        result = assistant_tools.read_conversation(
            db, scope, ReadConversation(tool="read_conversation", target="selected")
        )
    texts = [m["text"] for m in result["messages"]]
    assert len(texts) == 8 and texts[-1] == "消息 0" and texts[0] == "消息 7"
    assert not {"太早的消息", "已撤回", "另一个会话"} & set(texts)
    assert {m["message_id"] for m in result["messages"]} <= set(kept)
    assert all(
        set(m) == {"message_id", "message_revision", "occurred_at", "text"}
        for m in result["messages"]
    )
    assert "synthetic:" not in json.dumps(result)


def test_turns_never_write_business_data(signed_in):
    client, factory, _engine, headers = signed_in

    def snapshot():
        with factory() as db:
            return (
                json.dumps(db.get(WorkOrderRow, ORDER).data, sort_keys=True),
                db.scalar(select(func.count(ChangeRow.id))),
                db.scalar(select(func.count(AgentDraftRow.id))),
                db.scalar(select(func.count(WahaSendAction.id))),
                db.scalar(select(func.count()).select_from(ConversationOrder)),
                db.get(ConversationRow, CONV).context_version,
            )

    before = snapshot()
    for question in ("下周有空吗", "我有哪些订单", "帮我回一下", "确认预约并通知客户"):
        ask(client, headers, question, selected(work_order_id=ORDER, expected_work_order_version=3))
    while assistant.run_once(factory):
        pass
    assert snapshot() == before
    with factory() as db:
        answers = [row.answer for row in db.scalars(select(AssistantTurn))]
    assert all(a["execution_authority"] is False for a in answers)
    assert answers[-1]["kind"] == "unsupported"


def test_daily_ceiling_and_disable_switch(signed_in, monkeypatch):
    client, factory, _engine, headers = signed_in
    monkeypatch.setenv("GIGMATE_ASSISTANT_DAILY_TURNS", "2")
    assert ask(client, headers, "一").status_code == 202
    assert ask(client, headers, "二").status_code == 202
    third = ask(client, headers, "三")
    assert (third.status_code, third.json()["error"]["code"]) == (429, "ASSISTANT_BUDGET_EXCEEDED")
    monkeypatch.setenv("GIGMATE_ASSISTANT_ENABLED", "false")
    off = ask(client, headers, "四")
    assert (off.status_code, off.json()["error"]["code"]) == (503, "ASSISTANT_DISABLED")
    assert assistant.run_once(factory) is False


def test_threads_and_reads_are_account_scoped(signed_in):
    client, factory, _engine, headers = signed_in
    first = ask(client, headers, "我有哪些订单？").json()["data"]
    second = ask(client, headers, "下周有空吗", thread_id=first["thread_id"]).json()["data"]
    assert second["thread_id"] == first["thread_id"]
    listed = client.get(f"/api/v1/assistant/threads/{first['thread_id']}/turns?limit=1").json()
    assert len(listed["items"]) == 1 and listed["next_cursor"]
    client.post("/api/v1/auth/logout", headers=headers)
    other = client.post(
        "/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"}
    ).json()["data"]
    other_headers = {"X-CSRF-Token": other["csrf_token"]}
    assert client.get(f"/api/v1/assistant/turns/{first['id']}").status_code == 404
    assert client.get(f"/api/v1/assistant/threads/{first['thread_id']}/turns").status_code == 404
    hijack = ask(client, other_headers, "继续", thread_id=first["thread_id"])
    assert hijack.status_code == 404


def test_csrf_and_idempotency_key_are_required(signed_in):
    client, _factory, _engine, headers = signed_in
    no_csrf = client.post(
        "/api/v1/assistant/turns", json={"question": "hi"}, headers={"Idempotency-Key": "k"}
    )
    assert no_csrf.status_code == 403
    no_key = client.post("/api/v1/assistant/turns", json={"question": "hi"}, headers=headers)
    assert no_key.status_code == 422


def test_retention_scrubs_text_but_keeps_identity(signed_in):
    client, factory, _engine, headers = signed_in
    old = ask(client, headers, "旧问题：我有哪些订单").json()["data"]
    recent = ask(client, headers, "新问题：我有哪些订单").json()["data"]
    while assistant.run_once(factory):
        pass
    with factory.begin() as db:
        db.get(AssistantTurn, old["id"]).created_at = datetime.now(UTC) - timedelta(days=31)
    assert assistant.scrub(factory) == 1
    scrubbed = client.get(f"/api/v1/assistant/turns/{old['id']}").json()["data"]
    assert scrubbed["question"] is None and scrubbed["answer"] is None
    assert scrubbed["scrubbed_at"] and scrubbed["status"] == "completed"
    kept = client.get(f"/api/v1/assistant/turns/{recent['id']}").json()["data"]
    assert kept["question"].startswith("新问题") and kept["answer"]


def test_logs_never_contain_question_or_answer_text(signed_in, caplog):
    client, factory, _engine, headers = signed_in
    caplog.set_level(logging.DEBUG)
    ask(client, headers, "机密问题甲乙丙：我有哪些订单")
    assistant.run_once(factory)
    ask(client, headers, "机密问题丁戊己：下周有空吗")
    assistant.run_once(factory, planner=Fixed(error=TimeoutError("机密问题丁戊己")))
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "机密问题" not in joined and "合成" not in joined
