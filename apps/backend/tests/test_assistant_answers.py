"""Bounded assistant batch 2 (ADR 0011): deterministic availability and order answers.

A fixed clock is injected; nothing calls a model. Default schedule settings:
Monday–Saturday 09:00–19:00 Hong Kong time, break 12:30–13:30, 30-minute buffer,
60-minute preparation lead.
"""

import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from gigmate import assistant, scheduling
from gigmate.db import CalendarRow, ConversationRow, WorkOrderRow
from gigmate.seed import uid

NOW = datetime(2026, 11, 30, 1, 0, tzinfo=UTC)  # Monday 09:00 in Hong Kong
TODAY = "2026-11-30"
CONV, ORDER = uid(2), uid(3)


def plan(question, *, conversation=False, work_order=False, default=60):
    raw = assistant.RulePlanner().plan(
        {
            "question": question,
            "today": TODAY,
            "timezone": "Asia/Hong_Kong",
            "default_duration_minutes": default,
            "selection": {
                "conversation": conversation,
                "work_order": work_order,
                "selected_sources": 0,
            },
        }
    )
    return json.loads(raw)


def hk(day, hhmm):
    hours, minutes = map(int, hhmm.split(":"))
    return datetime(2026, 12, day, hours - 8, minutes, tzinfo=UTC)


def spans(windows):
    return [(w["start_at"], w["end_at"]) for w in windows]


def z(moment):
    return moment.isoformat().replace("+00:00", "Z")


def book(factory, day, start, end):
    """Move the seeded confirmed appointment of ORDER onto a December day."""
    with factory.begin() as db:
        row = db.query(CalendarRow).filter(CalendarRow.work_order_id == ORDER).one()
        data = dict(row.data)
        data["schedule"] = {
            "kind": "timed",
            "start_at": z(hk(day, start)),
            "end_at": z(hk(day, end)),
            "timezone": "Asia/Hong_Kong",
        }
        row.data = data


def ask(client, headers, question, context=None):
    body = {"question": question, **({"context": context} if context else {})}
    response = client.post(
        "/api/v1/assistant/turns",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]["id"]


def answer_of(client, factory, turn_id):
    assistant.run_once(factory, now=NOW)
    return client.get(f"/api/v1/assistant/turns/{turn_id}").json()["data"]


# --- free windows ------------------------------------------------------------


def test_windows_follow_hours_breaks_and_preparation(signed_in):
    _client, factory, _engine, _headers = signed_in
    with factory() as db:
        today = scheduling.free_windows(
            db, uid(1), date(2026, 11, 30), date(2026, 11, 30), timedelta(hours=1), now=NOW
        )
        tuesday = scheduling.free_windows(
            db, uid(1), date(2026, 12, 1), date(2026, 12, 1), timedelta(hours=1), now=NOW
        )
        sunday = scheduling.free_windows(
            db, uid(1), date(2026, 12, 6), date(2026, 12, 6), timedelta(hours=1), now=NOW
        )
    # Today starts after the one-hour preparation lead.
    assert spans(today) == [
        (z(datetime(2026, 11, 30, 2, 0, tzinfo=UTC)), z(datetime(2026, 11, 30, 4, 30, tzinfo=UTC))),
        (
            z(datetime(2026, 11, 30, 5, 30, tzinfo=UTC)),
            z(datetime(2026, 11, 30, 11, 0, tzinfo=UTC)),
        ),
    ]
    assert spans(tuesday) == [
        (z(hk(1, "09:00")), z(hk(1, "12:30"))),
        (z(hk(1, "13:30")), z(hk(1, "19:00"))),
    ]
    assert tuesday[1]["label"] == "12/01（周二）13:30–19:00"
    assert sunday == []


def test_appointments_and_buffers_split_windows(signed_in):
    _client, factory, _engine, _headers = signed_in
    book(factory, 1, "15:00", "16:00")
    with factory() as db:
        windows = scheduling.free_windows(
            db, uid(1), date(2026, 12, 1), date(2026, 12, 1), timedelta(hours=1), now=NOW
        )
        long_only = scheduling.free_windows(
            db, uid(1), date(2026, 12, 1), date(2026, 12, 1), timedelta(hours=3), now=NOW
        )
    assert spans(windows) == [
        (z(hk(1, "09:00")), z(hk(1, "12:30"))),
        (z(hk(1, "13:30")), z(hk(1, "14:30"))),
        (z(hk(1, "16:30")), z(hk(1, "19:00"))),
    ]
    assert spans(long_only) == [(z(hk(1, "09:00")), z(hk(1, "12:30")))]


def test_part_of_day_limits_windows(signed_in):
    _client, factory, _engine, _headers = signed_in
    with factory() as db:
        afternoon = scheduling.free_windows(
            db,
            uid(1),
            date(2026, 12, 1),
            date(2026, 12, 1),
            timedelta(hours=1),
            now=NOW,
            part="afternoon",
        )
        evening = scheduling.free_windows(
            db,
            uid(1),
            date(2026, 12, 1),
            date(2026, 12, 1),
            timedelta(hours=1),
            now=NOW,
            part="evening",
        )
    assert spans(afternoon) == [(z(hk(1, "13:30")), z(hk(1, "18:00")))]
    assert spans(evening) == [(z(hk(1, "18:00")), z(hk(1, "19:00")))]


# --- rule planner --------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "language", "start", "end", "minutes", "part"),
    [
        ("下周二下午有空吗，要一个半小时", "zh-Hans", "2026-12-08", "2026-12-08", 90, "afternoon"),
        ("周四能排吗？两小时", "zh-Hans", "2026-12-03", "2026-12-03", 120, None),
        ("後日得唔得閒？半個鐘就夠", "zh-Hant", "2026-12-02", "2026-12-02", 30, None),
        (
            "Am I free next Tuesday morning for 2 hours?",
            "en",
            "2026-12-08",
            "2026-12-08",
            120,
            "morning",
        ),
        ("这周末有空吗", "zh-Hans", "2026-12-05", "2026-12-06", 60, None),
        ("下周哪天有空？45分钟", "zh-Hans", "2026-12-07", "2026-12-13", 45, None),
        ("什么时候有空", "zh-Hans", "2026-11-30", "2026-12-06", 60, None),
    ],
)
def test_rule_planner_reads_days_durations_and_parts(question, language, start, end, minutes, part):
    result = plan(question)
    assert (result["intent"], result["language"]) == ("availability", language)
    call = result["tool_calls"][0]
    assert (call["from_date"], call["to_date"], call["duration_minutes"], call["part_of_day"]) == (
        start,
        end,
        minutes,
        part,
    )


def test_rule_planner_uses_the_supplied_default_duration():
    assert plan("明天有空吗", default=150)["tool_calls"][0]["duration_minutes"] == 150


@pytest.mark.parametrize(
    ("question", "selection", "call"),
    [
        (
            "等客户回复的订单有哪些",
            {},
            {"tool": "list_work_orders", "status": "waiting_customer", "scope": "account"},
        ),
        (
            "待确认的工单",
            {},
            {"tool": "list_work_orders", "status": "pending_confirmation", "scope": "account"},
        ),
        ("我有哪些订单", {}, {"tool": "list_work_orders", "status": "open", "scope": "account"}),
        (
            "这个客户有哪些工单",
            {"conversation": True},
            {"tool": "list_work_orders", "status": "open", "scope": "selected_conversation"},
        ),
        (
            "这张工单进度怎样",
            {"conversation": True},
            {"tool": "get_work_order", "target": "selected"},
        ),
    ],
)
def test_rule_planner_order_questions(question, selection, call):
    result = plan(question, **selection)
    assert result["intent"] == "order_status"
    assert result["tool_calls"] == [call]


# --- end-to-end answers ----------------------------------------------------------


def test_availability_answer_lists_windows_and_flags_customer_availability(signed_in):
    client, factory, _engine, headers = signed_in
    book(factory, 1, "15:00", "16:00")
    done = answer_of(client, factory, ask(client, headers, "这个客户下周二下午有空吗？要1小时"))
    answer = done["answer"]
    assert answer["kind"] == "slots"
    assert spans(answer["slots"]) == [
        (z(hk(8, "13:30")), z(hk(8, "18:00"))),
    ]
    assert "12/08（周二）13:30–18:00" in answer["text"]
    assert "需要向客户确认" in answer["text"]
    tuesday = answer_of(client, factory, ask(client, headers, "周二有空吗"))["answer"]
    assert spans(tuesday["slots"]) == [
        (z(hk(1, "09:00")), z(hk(1, "12:30"))),
        (z(hk(1, "13:30")), z(hk(1, "14:30"))),
        (z(hk(1, "16:30")), z(hk(1, "19:00"))),
    ]
    assert "需要向客户确认" not in tuesday["text"]


def test_english_and_empty_availability(signed_in):
    client, factory, _engine, headers = signed_in
    done = answer_of(client, factory, ask(client, headers, "Am I free on Sunday?"))
    assert done["answer"]["slots"] == []
    assert done["answer"]["text"].startswith("No free window")


def test_selected_order_duration_is_the_default(signed_in):
    client, factory, _engine, headers = signed_in
    with factory.begin() as db:
        order = db.get(WorkOrderRow, ORDER)
        data = json.loads(json.dumps(order.data))
        data["fields"]["schedule"]["value"]["end_at"] = "2026-10-07T09:30:00Z"
        order.data = data
    context = {
        "conversation_id": CONV,
        "expected_context_version": 4,
        "work_order_id": ORDER,
        "expected_work_order_version": 3,
    }
    done = answer_of(client, factory, ask(client, headers, "下周二有空吗", context))
    assert all(
        datetime.fromisoformat(s["end_at"].replace("Z", "+00:00"))
        - datetime.fromisoformat(s["start_at"].replace("Z", "+00:00"))
        >= timedelta(minutes=150)
        for s in done["answer"]["slots"]
    )
    assert "2.5 小时" in done["answer"]["text"]


def test_selected_order_detail_names_open_fields(signed_in):
    client, factory, _engine, headers = signed_in
    context = {
        "conversation_id": CONV,
        "expected_context_version": 4,
        "work_order_id": ORDER,
        "expected_work_order_version": 3,
    }
    done = answer_of(client, factory, ask(client, headers, "这张工单进度怎样", context))
    with factory() as db:
        summary = db.get(WorkOrderRow, ORDER).data["summary"]
    answer = done["answer"]
    assert (answer["kind"], answer["work_order_ids"]) == ("orders", [ORDER])
    assert f"工单「{summary}」：已确认（版本 3）" in answer["text"]
    # Schedule is confirmed and optional details are merely empty: only the address is open.
    assert answer["text"].endswith("仍待确认：地址。")
    assert answer["citations"][0]["work_order_id"] == ORDER


def test_this_order_without_selection_reports_how_many_orders_the_chat_has(signed_in):
    client, factory, _engine, headers = signed_in
    chat = {"conversation_id": CONV, "expected_context_version": 4}
    one = answer_of(client, factory, ask(client, headers, "这张工单进度怎样", chat))
    assert one["intent"] == "clarify"
    assert "有 1 张未完成的工单" in one["answer"]["text"]
    with factory.begin() as db:
        db.add(ConversationRow(id=uid(40), account_id=uid(1), context_version=1, allowlisted=True))
    empty = answer_of(
        client,
        factory,
        ask(
            client,
            headers,
            "这张工单进度怎样",
            {"conversation_id": uid(40), "expected_context_version": 1},
        ),
    )
    assert "还没有未完成的工单" in empty["answer"]["text"]
    none = answer_of(client, factory, ask(client, headers, "这张工单进度怎样"))
    assert "请先在客户会话中选择" in none["answer"]["text"]


def test_status_filter_lists_only_matching_orders(signed_in):
    client, factory, _engine, headers = signed_in
    with factory.begin() as db:
        order = db.get(WorkOrderRow, ORDER)
        order.data = {**order.data, "status": "waiting_customer"}
    done = answer_of(client, factory, ask(client, headers, "等客户回复的订单有哪些"))
    answer = done["answer"]
    assert answer["work_order_ids"] == [ORDER]
    assert answer["text"].startswith("等客户回复的工单共 1 张")
    traditional = answer_of(client, factory, ask(client, headers, "邊啲訂單等緊客人回覆？等客人"))
    assert traditional["answer"]["text"].startswith("等客人回覆嘅工單共 1 張")
