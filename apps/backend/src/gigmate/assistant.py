"""Bounded merchant assistant turns (ADR 0011, batch 1).

A turn is submitted by an authenticated merchant, stored with an idempotency key
and executed by the worker under a lease:

1. the planner returns an ``AssistantPlan`` (batch 1: the offline rule planner);
2. the server re-resolves the merchant's selection, runs only allowlisted
   read-only tools and renders the answer itself;
3. a changed selection (context or order version) supersedes the turn.

Nothing here writes business data, confirms, approves or sends. Logs carry IDs
and stable codes only, never the question, customer text or answers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, update

from gigmate import assistant_tools, scheduling
from gigmate.assistant_plan import AssistantComposition, AssistantPlan
from gigmate.contracts import (
    AssistantAnswer,
    AssistantCapabilities,
    AssistantContext,
    AssistantTurnCommand,
    AssistantTurnView,
)
from gigmate.db import (
    AssistantThread,
    AssistantTurn,
    ConversationOrder,
    ConversationRow,
    MessageRow,
    Session,
    WorkOrderRow,
)
from gigmate.errors import BusinessError
from gigmate.extraction.language import detect_language
from gigmate.message_context import source_allowed

log = logging.getLogger(__name__)

LEASE = timedelta(seconds=60)
RETENTION = timedelta(days=30)
FINAL = {"completed", "failed", "unknown", "superseded"}


def enabled() -> bool:
    return os.environ.get("GIGMATE_ASSISTANT_ENABLED", "true").lower() != "false"


def daily_limit() -> int:
    try:
        return max(1, int(os.environ.get("GIGMATE_ASSISTANT_DAILY_TURNS", "200")))
    except ValueError:
        return 200


def _utc(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=UTC)


def _stamp(value):
    value = _utc(value)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def capabilities() -> dict:
    """Batches 1–4 run only the offline rule engine: nothing leaves the server."""
    return AssistantCapabilities(
        enabled=enabled(),
        engine="rules",
        vendor=None,
        sends_customer_text=False,
        daily_turns=daily_limit(),
    ).model_dump(mode="json")


# --- submission -----------------------------------------------------------


def _owned(db, model, identifier, account_id):
    row = db.scalar(select(model).where(model.id == identifier, model.account_id == account_id))
    if row is None:
        raise BusinessError(404, "NOT_FOUND", "Resource not found")
    return row


def resolve_scope(db, account_id: str, context: AssistantContext) -> assistant_tools.Scope:
    """Re-check ownership, consent and versions of the merchant's selection."""
    scope = assistant_tools.Scope(account_id=account_id)
    if context.conversation_id:
        conversation = _owned(db, ConversationRow, context.conversation_id, account_id)
        if not conversation.allowlisted:
            raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
        if conversation.context_version != context.expected_context_version:
            raise BusinessError(409, "ASSISTANT_CONTEXT_STALE", "The conversation changed")
        scope.conversation = conversation
    if context.work_order_id:
        order = _owned(db, WorkOrderRow, context.work_order_id, account_id)
        if order.data.get("version") != context.expected_work_order_version:
            raise BusinessError(409, "ASSISTANT_CONTEXT_STALE", "The work order changed")
        if scope.conversation is not None and not db.get(
            ConversationOrder, (scope.conversation.id, order.id)
        ):
            raise BusinessError(
                409, "ASSISTANT_SELECTION_MISMATCH", "The order is not linked to this chat"
            )
        scope.order = order
    for source in context.selected_sources:
        newest = db.scalar(
            select(func.max(MessageRow.revision)).where(
                MessageRow.id == source.message_id,
                MessageRow.account_id == account_id,
                MessageRow.conversation_id == scope.conversation.id,
            )
        )
        row = db.get(MessageRow, (source.message_id, source.message_revision))
        if (
            row is None
            or newest != source.message_revision
            or not source_allowed(db, scope.conversation, row)
        ):
            raise BusinessError(409, "ASSISTANT_SOURCE_STALE", "A selected message changed")
        scope.selected_sources.append(source.model_dump())
    return scope


def _digest(command: AssistantTurnCommand) -> str:
    raw = json.dumps(command.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def submit(db, account, command: AssistantTurnCommand, key: str | None, now=None) -> dict:
    if not key or len(key) > 128:
        raise BusinessError(
            422, "VALIDATION_FAILED", "Provide an Idempotency-Key of 1–128 characters"
        )
    now = now or datetime.now(UTC)
    digest = _digest(command)
    existing = db.scalar(
        select(AssistantTurn).where(
            AssistantTurn.account_id == account.id, AssistantTurn.request_key == key
        )
    )
    if existing is not None:
        if existing.digest != digest:
            raise BusinessError(
                409, "IDEMPOTENCY_CONFLICT", "Command key was reused with changed content"
            )
        return view(existing)
    if not enabled():
        raise BusinessError(503, "ASSISTANT_DISABLED", "The assistant is turned off")
    resolve_scope(db, account.id, command.context)
    if command.thread_id:
        thread = _owned(db, AssistantThread, command.thread_id, account.id)
        thread.updated_at = now
    else:
        thread = AssistantThread(id=str(uuid4()), account_id=account.id, created_at=now)
        thread.updated_at = now
        db.add(thread)
    used = db.scalar(
        select(func.count(AssistantTurn.id)).where(
            AssistantTurn.account_id == account.id,
            AssistantTurn.created_at > now - timedelta(days=1),
        )
    )
    if used >= daily_limit():
        raise BusinessError(429, "ASSISTANT_BUDGET_EXCEEDED", "Daily assistant limit reached")
    turn = AssistantTurn(
        id=str(uuid4()),
        account_id=account.id,
        thread_id=thread.id,
        request_key=key,
        digest=digest,
        question=command.question,
        context=command.context.model_dump(mode="json"),
        state="queued",
        attempts=0,
        created_at=now,
        updated_at=now,
    )
    db.add(turn)
    db.flush()
    log.info("assistant_turn_queued turn=%s", turn.id)
    return view(turn)


def view(turn: AssistantTurn) -> dict:
    return AssistantTurnView(
        id=turn.id,
        thread_id=turn.thread_id,
        status=turn.state,
        question=turn.question,
        intent=turn.intent,
        context=AssistantContext.model_validate(turn.context),
        answer=AssistantAnswer.model_validate(turn.answer) if turn.answer else None,
        error_code=turn.error_code,
        engine=turn.engine,
        created_at=_stamp(turn.created_at),
        completed_at=_stamp(turn.completed_at),
        scrubbed_at=_stamp(turn.scrubbed_at),
    ).model_dump(mode="json")


def get(db, account, turn_id: str) -> dict:
    return view(_owned(db, AssistantTurn, turn_id, account.id))


def list_for_thread(db, account, thread_id: str):
    _owned(db, AssistantThread, thread_id, account.id)
    return list(
        db.scalars(
            select(AssistantTurn).where(
                AssistantTurn.account_id == account.id, AssistantTurn.thread_id == thread_id
            )
        )
    )


# --- planning --------------------------------------------------------------


class PlannerUnavailable(Exception):
    pass


class Planner(Protocol):
    engine: str

    def plan(self, request: dict) -> str:
        """Return AssistantPlan JSON. May raise PlannerUnavailable or time out."""


_POLISH = ("润色", "潤色", "改得", "改一下", "礼貌", "禮貌", "polish", "rewrite", "politer")
# Explicit requests to write a reply; a bare "回复" also appears in status questions
# such as "等客户回复的订单".
_REPLY = (
    "帮我回",
    "幫我回",
    "替我回",
    "代我回",
    "回一下",
    "回复一下",
    "回覆一下",
    "回复这条",
    "回覆這條",
    "回覆呢條",
    "回佢",
    "reply to",
    "respond to",
    "draft a reply",
    "write a reply",
)
_AVAILABILITY = (
    "有空",
    "空闲",
    "空閒",
    "得閒",
    "有冇時間",
    "档期",
    "檔期",
    "排得",
    "能排",
    "可以排",
    "free",
    "available",
    "availability",
    "slot",
)
_ORDERS = (
    "工单",
    "工單",
    "订单",
    "訂單",
    "进度",
    "進度",
    "order",
    "status",
    "等客",
    "这单",
    "呢單",
)
_THIS_ORDER = (
    "这张",
    "這張",
    "这单",
    "這單",
    "呢張",
    "呢單",
    "这个工单",
    "這個工單",
    "this order",
    "this job",
)
_THIS_CUSTOMER = ("这个客户", "這個客戶", "呢個客", "这位客", "this customer", "this client")
_CUSTOMER = ("客户", "客戶", "客人", "customer", "client")
_STATUS_WORDS = (
    (("等客户", "等客戶", "等客人", "waiting"), "waiting_customer"),
    (("待确认", "待確認", "未确认", "未確認", "pending"), "pending_confirmation"),
    (("进行中", "進行中", "in progress"), "in_progress"),
    (("已确认", "已確認", "confirmed"), "confirmed"),
)
_PARTS = (
    (("上午", "早上", "朝早", "morning"), "morning"),
    (("下午", "afternoon"), "afternoon"),
    (("晚上", "夜晚", "evening", "tonight"), "evening"),
)
_DIGITS = {"一": 1, "两": 2, "兩": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8}
_WEEKDAY_NAMES = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}
_WEEKDAY_EN = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WEEKDAY_ZH = re.compile(r"(下)?(?:周|週|星期|礼拜|禮拜)([一二三四五六日天])")
_NUMBER = r"(\d+(?:\.\d+)?|[一两兩二三四五六七八])"
_HOURS = re.compile(
    _NUMBER + r"\s*(?:个半|個半)?\s*(?:个?小时|個?小時|个钟|個鐘|hours?|hrs?|h\b)", re.I
)
_HALF_EXTRA = re.compile(r"(?:个半|個半)")
_MINUTES = re.compile(r"(\d+)\s*(?:分钟|分鐘|mins?|minutes?)", re.I)
_HALF_HOUR = ("半小时", "半小時", "半个钟", "半個鐘", "half an hour", "half hour")


def _has(text: str, words) -> bool:
    return any(word in text for word in words)


def _clarify(language: str, zh: str, hant: str, en: str) -> dict:
    question = {"zh-Hans": zh, "zh-Hant": hant}.get(language, en)
    return {
        "schema_version": "1.0.0",
        "intent": "clarify",
        "language": language,
        "tool_calls": [],
        "clarification_question": question,
    }


def _window(text: str, today: date) -> tuple[date, date]:
    """Dates the merchant asked about; defaults to the next seven days."""
    next_monday = today + timedelta(days=7 - today.weekday())
    if match := _WEEKDAY_ZH.search(text):
        weekday = _WEEKDAY_NAMES[match.group(2)]
        if match.group(1):
            day = next_monday + timedelta(days=weekday)
        else:
            day = today + timedelta(days=(weekday - today.weekday()) % 7)
        return day, day
    for index, name in enumerate(_WEEKDAY_EN):
        if name in text:
            base = next_monday if "next" in text else today
            day = base + timedelta(days=(index - base.weekday()) % 7)
            return day, day
    if _has(text, ("下周末", "下週末", "next weekend")):
        saturday = next_monday + timedelta(days=5)
        return saturday, saturday + timedelta(days=1)
    if _has(text, ("周末", "週末", "weekend")):
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        return saturday, saturday + timedelta(days=1)
    if _has(text, ("下周", "下週", "下星期", "下禮拜", "下礼拜", "next week")):
        return next_monday, next_monday + timedelta(days=6)
    if _has(text, ("后天", "後天", "後日")):
        day = today + timedelta(days=2)
        return day, day
    if _has(text, ("明天", "聽日", "tomorrow")):
        day = today + timedelta(days=1)
        return day, day
    if _has(text, ("今天", "今日", "today")):
        return today, today
    if _has(text, ("这周", "這週", "本周", "本週", "this week")):
        return today, today + timedelta(days=6 - today.weekday())
    return today, today + timedelta(days=6)


def _number(value: str) -> float:
    return float(_DIGITS.get(value, value))


def _duration(text: str, default: int) -> int:
    # "一个半小时" contains "半小时": read an explicit number of hours first.
    if match := _HOURS.search(text):
        hours = _number(match.group(1)) + (0.5 if _HALF_EXTRA.search(match.group(0)) else 0)
        return max(15, min(720, round(hours * 60)))
    if match := _MINUTES.search(text):
        return max(15, min(720, int(match.group(1))))
    if _has(text, _HALF_HOUR):
        return 30
    return max(15, min(720, default))


def _first(text: str, table) -> str | None:
    return next((value for words, value in table if _has(text, words)), None)


class RulePlanner:
    """Deterministic offline planner: keyword intents, no model, no network."""

    engine = "rules"

    def plan(self, request: dict) -> str:
        question = request["question"]
        text = question.lower()
        language = detect_language(question)
        selection = request["selection"]
        today = date.fromisoformat(request["today"])
        base = {"schema_version": "1.0.0", "language": language}
        if _has(text, _POLISH):
            if not selection["conversation"]:
                plan = _clarify(
                    language,
                    "请先在客户会话中选择要发送的聊天，再让我润色。",
                    "請先喺客人對話揀選要發送嘅聊天，再叫我潤色。",
                    "Select the customer chat this text is for, then ask me to polish it.",
                )
            else:
                plan = {**base, "intent": "polish", "tool_calls": []}
        elif _has(text, _REPLY):
            if not selection["conversation"]:
                plan = _clarify(
                    language,
                    "请先在客户会话中选择要回复的聊天。",
                    "請先喺客人對話揀選要回覆嘅聊天。",
                    "Select the customer chat you want to reply to first.",
                )
            else:
                calls = [{"tool": "read_conversation", "target": "selected"}]
                if selection["work_order"]:
                    calls.append({"tool": "get_work_order", "target": "selected"})
                plan = {**base, "intent": "reply_draft", "tool_calls": calls}
        elif _has(text, _AVAILABILITY):
            start, end = _window(text, today)
            plan = {
                **base,
                "intent": "availability",
                "tool_calls": [
                    {
                        "tool": "find_free_slots",
                        "duration_minutes": _duration(text, request["default_duration_minutes"]),
                        "from_date": start.isoformat(),
                        "to_date": end.isoformat(),
                        "part_of_day": _first(text, _PARTS),
                    }
                ],
            }
        elif _has(text, _ORDERS):
            if _has(text, _THIS_ORDER):
                # A single order: only the merchant's selection, never a guess.
                plan = {
                    **base,
                    "intent": "order_status",
                    "tool_calls": [{"tool": "get_work_order", "target": "selected"}],
                }
            else:
                scope = (
                    "selected_conversation"
                    if selection["conversation"] and _has(text, _THIS_CUSTOMER)
                    else "account"
                )
                plan = {
                    **base,
                    "intent": "order_status",
                    "tool_calls": [
                        {
                            "tool": "list_work_orders",
                            "status": _first(text, _STATUS_WORDS) or "open",
                            "scope": scope,
                        }
                    ],
                }
        else:
            plan = {**base, "intent": "unsupported", "tool_calls": []}
        return json.dumps(plan, ensure_ascii=False)


def planner_for() -> Planner:
    """Batches 1–2 ship only the offline planner; the reviewed model arrives in batch 5."""
    return RulePlanner()


# --- rendering ---------------------------------------------------------------

_STATUS = {
    "zh-Hans": {
        "pending_confirmation": "待确认",
        "confirmed": "已确认",
        "in_progress": "进行中",
        "waiting_customer": "等客户回复",
        "completed": "已完成",
        "cancelled": "已取消",
        "open": "未结束",
    },
    "zh-Hant": {
        "pending_confirmation": "待確認",
        "confirmed": "已確認",
        "in_progress": "進行中",
        "waiting_customer": "等客人回覆",
        "completed": "已完成",
        "cancelled": "已取消",
        "open": "未完成",
    },
    "en": {
        "pending_confirmation": "pending confirmation",
        "confirmed": "confirmed",
        "in_progress": "in progress",
        "waiting_customer": "waiting for customer",
        "completed": "completed",
        "cancelled": "cancelled",
        "open": "open",
    },
}
_FIELDS = {
    "zh-Hans": {
        "schedule": "时间",
        "address": "地址",
        "specification": "规格",
        "quantity": "数量",
        "deadline": "截止时间",
    },
    "zh-Hant": {
        "schedule": "時間",
        "address": "地址",
        "specification": "規格",
        "quantity": "數量",
        "deadline": "截止時間",
    },
    "en": {
        "schedule": "time",
        "address": "address",
        "specification": "specification",
        "quantity": "quantity",
        "deadline": "deadline",
    },
}
_PART_LABEL = {
    "zh-Hans": {"morning": "上午", "afternoon": "下午", "evening": "晚上"},
    "zh-Hant": {"morning": "上午", "afternoon": "下晝", "evening": "夜晚"},
    "en": {"morning": "morning", "afternoon": "afternoon", "evening": "evening"},
}
_WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _say(language: str, zh: str, hant: str, en: str) -> str:
    return {"zh-Hans": zh, "zh-Hant": hant}.get(language, en)


def _window_line(slot: dict, timezone: str, language: str) -> str:
    from zoneinfo import ZoneInfo

    start = scheduling.parse(slot["start_at"]).astimezone(ZoneInfo(timezone))
    end = scheduling.parse(slot["end_at"]).astimezone(ZoneInfo(timezone))
    if language == "en":
        return f"{_WEEKDAY_SHORT[start.weekday()]} {start:%m/%d} {start:%H:%M}–{end:%H:%M}"
    return slot["label"]


def _citations(results: list[dict]) -> list[dict]:
    seen, out = set(), []
    for result in results:
        for item in result.get("citations", []):
            key = json.dumps(item, sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


def _hours(minutes: int) -> str:
    return f"{minutes / 60:g}"


def _render_availability(language: str, found: dict, customer_note: bool) -> dict:
    hours = _hours(found["duration_minutes"])
    days = (
        found["from_date"]
        if found["from_date"] == found["to_date"]
        else f"{found['from_date']} – {found['to_date']}"
    )
    part = _PART_LABEL[language].get(found["part_of_day"] or "", "")
    if found["slots"]:
        head = _say(
            language,
            f"{days}{part}你有空、可安排 {hours} 小时的时段（{found['timezone']}）：",
            f"{days}{part}你有空、可安排 {hours} 小時嘅時段（{found['timezone']}）：",
            f"Your free windows {days}{' ' + part if part else ''} that fit {hours} hours "
            f"({found['timezone']}):",
        )
        lines = "\n".join(
            "- " + _window_line(s, found["timezone"], language) for s in found["slots"]
        )
        text = head + "\n" + lines
    else:
        text = _say(
            language,
            f"{days}{part}没有能安排 {hours} 小时的空闲时段。",
            f"{days}{part}冇可以安排 {hours} 小時嘅空檔。",
            f"No free window of {hours} hours {days}{' ' + part if part else ''}.",
        )
    if customer_note:
        text += "\n" + _say(
            language,
            "以上是你自己的空闲时间；客户那天是否方便，需要向客户确认。",
            "以上係你自己嘅空檔；客人當日方唔方便，要同客人確認。",
            "These are your own free times; confirm with the customer whether they suit them.",
        )
    return {"kind": "slots", "text": text, "slots": found["slots"]}


def _render_orders(language: str, results: list[dict]) -> dict:
    labels, names = _STATUS[language], _FIELDS[language]
    single = next((r for r in results if "order" in r), None)
    if single:
        order = single["order"]
        # Key items decide confirmation; other details matter only when something is pending.
        gaps = [
            names.get(name, name)
            for name, status in order["field_status"].items()
            if (name in {"schedule", "address"} and status != "confirmed")
            or status in {"needs_review", "proposed"}
        ]
        status = labels.get(order["status"], order["status"])
        text = _say(
            language,
            f"工单「{order['summary']}」：{status}（版本 {order['version']}）。",
            f"工單「{order['summary']}」：{status}（版本 {order['version']}）。",
            f"Work order “{order['summary']}”: {status} (version {order['version']}).",
        )
        text += " " + (
            _say(
                language,
                "仍待确认：" + "、".join(gaps) + "。",
                "仲要確認：" + "、".join(gaps) + "。",
                "Still to confirm: " + ", ".join(gaps) + ".",
            )
            if gaps
            else _say(
                language, "关键信息都已确认。", "重要資料都已確認。", "Key details are confirmed."
            )
        )
        return {"kind": "orders", "text": text, "work_order_ids": [order["id"]]}
    listed = next(r for r in results if "orders" in r)
    orders, wanted = listed["orders"], labels.get(listed["status"], listed["status"])
    if orders:
        head = _say(
            language,
            f"{wanted}的工单共 {len(orders)} 张：",
            f"{wanted}嘅工單共 {len(orders)} 張：",
            f"{len(orders)} {wanted} work orders:",
        )
        lines = "\n".join(
            f"- {o['summary']}（{labels.get(o['status'], o['status'])}）"
            if language != "en"
            else f"- {o['summary']} ({labels.get(o['status'], o['status'])})"
            for o in orders
        )
        text = head + "\n" + lines
    else:
        text = _say(
            language,
            f"没有{wanted}的工单。",
            f"冇{wanted}嘅工單。",
            f"No {wanted} work orders.",
        )
    return {"kind": "orders", "text": text, "work_order_ids": [o["id"] for o in orders]}


def render(plan: AssistantPlan, results: list[dict], *, customer_note: bool = False) -> dict:
    language = plan.language
    citations = _citations(results)
    if plan.intent == "clarify":
        answer = {"kind": "clarification", "text": plan.clarification_question}
    elif plan.intent == "availability":
        found = next(r for r in results if "slots" in r)
        answer = _render_availability(language, found, customer_note)
    elif plan.intent == "order_status":
        answer = _render_orders(language, results)
    else:
        answer = {
            "kind": "unsupported",
            "text": _say(
                language,
                "我只能帮你查空闲时段、查工单状态、准备回复草稿和润色文字。其他操作请使用对应页面。",
                "我只可以幫你查空檔、查工單狀態、準備回覆草稿同潤色文字。其他操作請用對應頁面。",
                "I can check free slots and work-order status, prepare reply drafts and polish text. "
                "Use the normal pages for anything else.",
            ),
        }
    answer["citations"] = [
        {"message": None, "work_order_id": None, "work_order_version": None, **c} for c in citations
    ]
    return AssistantAnswer.model_validate(answer).model_dump(mode="json")


# --- execution ---------------------------------------------------------------


def _finish(turn, state, now, *, code=None, answer=None):
    turn.state, turn.error_code = state, code
    turn.lease_token = turn.lease_until = None
    turn.updated_at = turn.completed_at = now
    if answer is not None:
        turn.answer = answer


def _claim(factory, now):
    with factory.begin() as db:
        query = (
            select(AssistantTurn)
            .where(
                (AssistantTurn.state == "queued")
                | ((AssistantTurn.state == "running") & (AssistantTurn.lease_until <= now))
            )
            .order_by(AssistantTurn.created_at, AssistantTurn.id)
            .limit(1)
        )
        if db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        turn = db.scalar(query)
        if turn is None:
            return None
        if turn.state == "running":
            # The previous attempt may have reached the model: never retry blindly.
            _finish(turn, "unknown", now, code="ASSISTANT_RESULT_UNKNOWN")
            log.warning("assistant_turn_unknown turn=%s", turn.id)
            return True
        token = str(uuid4())
        turn.state, turn.lease_token, turn.lease_until = "running", token, now + LEASE
        turn.attempts += 1
        turn.updated_at = now
        config = scheduling.settings(db, turn.account_id)
        from zoneinfo import ZoneInfo

        context = AssistantContext.model_validate(turn.context)
        default = config.default_duration_minutes
        if context.work_order_id:
            order = db.get(WorkOrderRow, context.work_order_id)
            schedule = (
                ((order.data if order else {}).get("fields") or {}).get("schedule") or {}
            ).get("value")
            if isinstance(schedule, dict) and schedule.get("kind") == "timed":
                span = scheduling.parse(schedule["end_at"]) - scheduling.parse(schedule["start_at"])
                default = max(15, min(720, int(span.total_seconds() // 60)))
        request = {
            "question": turn.question,
            "default_duration_minutes": default,
            "today": now.astimezone(ZoneInfo(config.timezone)).date().isoformat(),
            "timezone": config.timezone,
            "selection": {
                "conversation": context.conversation_id is not None,
                "work_order": context.work_order_id is not None,
                "selected_sources": len(context.selected_sources),
            },
        }
        return turn.id, token, request


def _selection_question(db, scope, language: str) -> dict:
    """Ask the merchant to choose; say how many open orders the chosen chat has."""
    if scope.conversation is None:
        return _clarify(
            language,
            "请先在客户会话中选择聊天或工单，再问一次。",
            "請先喺客人對話揀選聊天或者工單，再問一次。",
            "Select a customer chat or work order first, then ask again.",
        )
    count = sum(
        1
        for order in db.scalars(
            select(WorkOrderRow)
            .join(ConversationOrder, ConversationOrder.work_order_id == WorkOrderRow.id)
            .where(
                ConversationOrder.conversation_id == scope.conversation.id,
                WorkOrderRow.account_id == scope.account_id,
            )
        )
        if order.data.get("status") in assistant_tools.OPEN
    )
    if count == 0:
        return _clarify(
            language,
            "这个聊天还没有未完成的工单；如需建单，请在会话中选择客户消息后新建。",
            "呢個聊天未有未完成嘅工單；如要開單，請喺對話揀選客人訊息再新建。",
            "This chat has no open work order yet; select customer messages to create one.",
        )
    return _clarify(
        language,
        f"这个聊天有 {count} 张未完成的工单，请先选择要问的那一张。",
        f"呢個聊天有 {count} 張未完成嘅工單，請先揀選要問嗰張。",
        f"This chat has {count} open work orders; select the one you mean first.",
    )


def run_once(factory=Session, *, planner: Planner | None = None, composer=None, now=None) -> bool:
    if not enabled():
        return False
    injected = now is not None
    now = now or datetime.now(UTC)
    claimed = _claim(factory, now)
    if claimed in (None, True):
        return bool(claimed)
    turn_id, token, request = claimed
    planner = planner or planner_for()
    outcome, plan = None, None
    try:
        plan = AssistantPlan.model_validate_json(planner.plan(request))
    except PlannerUnavailable:
        outcome = ("failed", "ASSISTANT_DISABLED")
    except ValidationError:
        outcome = ("failed", "ASSISTANT_PLAN_INVALID")
    except Exception as error:  # an interrupted planner call may have been processed
        log.warning("assistant_plan_interrupted turn=%s class=%s", turn_id, type(error).__name__)
        outcome = ("unknown", "ASSISTANT_RESULT_UNKNOWN")
    finished_at = now if injected else datetime.now(UTC)
    with factory.begin() as db:
        turn = _leased(db, turn_id, token)
        if turn is None:
            return True
        turn.engine = getattr(planner, "engine", None)
        if outcome:
            _finish(turn, outcome[0], finished_at, code=outcome[1])
            return True
        turn.intent = plan.intent
        scope = _scope_or_finish(db, turn, finished_at)
        if scope is None:
            return True
        scope.now = now if injected else None
        customer_note = plan.intent == "availability" and _has(
            (turn.question or "").lower(), _CUSTOMER
        )
        results, used = [], []
        try:
            for call in plan.tool_calls:
                results.append(assistant_tools.run(db, scope, call))
                used.append(call.tool)
        except assistant_tools.ToolUnavailable as error:
            plan = AssistantPlan.model_validate(_selection_question(db, scope, plan.language))
            turn.intent, results, used = "clarify", [], used + [f"refused:{error.code}"]
        turn.trace = {"tools": used, "language": plan.language}
        if plan.intent not in DRAFTING:
            _finish(
                turn,
                "completed",
                finished_at,
                answer=render(plan, results, customer_note=customer_note),
            )
            log.info("assistant_turn_completed turn=%s intent=%s", turn.id, turn.intent)
            return True
        compose_request = _compose_request(turn, plan, scope, results)
    # Phase 2 (reply/polish) runs outside any transaction: a model call may be slow.
    return _compose(factory, turn_id, token, plan, compose_request, composer, injected, now)


DRAFTING = {"reply_draft", "polish"}


def _leased(db, turn_id, token):
    turn = db.scalar(
        select(AssistantTurn)
        .where(AssistantTurn.id == turn_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if turn is None or turn.state != "running" or turn.lease_token != token:
        return None
    return turn


def _scope_or_finish(db, turn, finished_at):
    try:
        return resolve_scope(db, turn.account_id, AssistantContext.model_validate(turn.context))
    except BusinessError as error:
        state = "superseded" if error.code == "ASSISTANT_CONTEXT_STALE" else "failed"
        _finish(turn, state, finished_at, code=error.code)
        return None


def _compose_request(turn, plan, scope, results) -> dict:
    messages = next((r["messages"] for r in results if "messages" in r), [])
    order = next((r["order"] for r in results if "order" in r), None)
    windows = next((r for r in results if "slots" in r), None)
    return {
        "kind": plan.intent,
        "language": plan.language,
        "question": turn.question,
        "dictated": dictated_text(turn.question or ""),
        "selected_sources": scope.selected_sources,
        "messages": messages,
        "order": order,
        "free_windows": windows["slots"] if windows else [],
    }


def _allowed_sources(request: dict) -> set[tuple[str, int]]:
    cited = request["selected_sources"] or [
        {"message_id": m["message_id"], "message_revision": m["message_revision"]}
        for m in request["messages"]
    ]
    return {(s["message_id"], s["message_revision"]) for s in cited}


def _compose(factory, turn_id, token, plan, request, composer, injected, now) -> bool:
    from gigmate import assistant_drafts

    composer = composer or composer_for()
    failure, composition = None, None
    try:
        composition = AssistantComposition.model_validate_json(composer.compose(request))
    except ComposerUnavailable as error:
        failure = ("completed", error.code)
    except ValidationError:
        failure = ("failed", "ASSISTANT_COMPOSITION_INVALID")
    except Exception as error:
        log.warning("assistant_compose_interrupted turn=%s class=%s", turn_id, type(error).__name__)
        failure = ("unknown", "ASSISTANT_RESULT_UNKNOWN")
    if composition is not None and (
        composition.kind != plan.intent
        or not {(s.message_id, s.message_revision) for s in composition.sources}
        <= _allowed_sources(request)
    ):
        # The text may only answer revisions the merchant selected or the bounded context held.
        composition, failure = None, ("failed", "ASSISTANT_COMPOSITION_INVALID")
    finished_at = now if injected else datetime.now(UTC)
    with factory.begin() as db:
        turn = _leased(db, turn_id, token)
        if turn is None:
            return True
        turn.engine = getattr(composer, "engine", turn.engine)
        if failure and failure[0] != "completed":
            _finish(turn, failure[0], finished_at, code=failure[1])
            return True
        scope = _scope_or_finish(db, turn, finished_at)
        if scope is None:
            return True
        if failure:
            _finish(
                turn,
                "completed",
                finished_at,
                answer=_drafting_unavailable(plan.language, failure[1]),
            )
            return True
        draft = assistant_drafts.create(
            db, scope=scope, turn=turn, composition=composition, now=finished_at
        )
        citations = [
            {
                "kind": "message",
                "message": s.model_dump(),
                "work_order_id": None,
                "work_order_version": None,
            }
            for s in composition.sources
        ]
        if scope.order is not None:
            citations.append(
                {
                    "kind": "work_order",
                    "message": None,
                    "work_order_id": scope.order.id,
                    "work_order_version": scope.order.data.get("version"),
                }
            )
        heading = _say(
            plan.language,
            "已准备好草稿（尚未发送，可放入输入框核对后再发）：",
            "已準備好草稿（未發送，可放入輸入框核對後再發）：",
            "Draft ready (not sent; put it in the composer and review before sending):",
        )
        answer = AssistantAnswer.model_validate(
            {
                "kind": "draft",
                "text": heading + "\n" + composition.text,
                "draft_id": draft.id,
                "unverified_claims": composition.unverified_claims,
                "citations": citations,
            }
        ).model_dump(mode="json")
        _finish(turn, "completed", finished_at, answer=answer)
        log.info(
            "assistant_turn_completed turn=%s intent=%s draft=%s", turn.id, plan.intent, draft.id
        )
    return True


_UNAVAILABLE = {
    "ASSISTANT_DICTATION_REQUIRED": (
        "clarification",
        "请告诉我要回复的内容，例如：帮我回一下，说周二下午可以。（自动起草需要接入模型后才开放。）",
        "請講低要回覆嘅內容，例如：幫我回一下，話星期二下晝得。（自動起草要接入模型先開放。）",
        "Tell me what to say, for example: reply saying Tuesday afternoon works. "
        "(Automatic drafting needs the model, which is not enabled.)",
    ),
    "ASSISTANT_NO_SOURCE": (
        "unsupported",
        "这个聊天里没有可以引用的已授权客户消息，无法起草回复。",
        "呢個聊天冇可以引用嘅已授權客人訊息，未能起草回覆。",
        "This chat has no consented customer message to reply to.",
    ),
}


def _drafting_unavailable(language: str, code: str) -> dict:
    kind, zh, hant, en = _UNAVAILABLE.get(code, _UNAVAILABLE["ASSISTANT_DICTATION_REQUIRED"])
    return AssistantAnswer.model_validate(
        {"kind": kind, "text": _say(language, zh, hant, en), "citations": []}
    ).model_dump(mode="json")


# --- composing (phase 2) -----------------------------------------------------


class ComposerUnavailable(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Composer(Protocol):
    engine: str

    def compose(self, request: dict) -> str:
        """Return AssistantComposition JSON. May raise ComposerUnavailable or time out."""


# "说 / say" introduces dictated content only after punctuation, a space, the start or
# 回/回复: "客户说的那条" (what the customer said) is not dictation.
_DICTATION = re.compile(
    r"(?:(?:^|[，,。；;\s]|回复|回覆|回)(?:说|說|讲|講|話)"
    r"|告诉他|告诉她|告訴佢|跟他说|跟她说|同佢講"
    r"|\bsaying\b|\bsay\b|\btell (?:them|him|her)\b)\s*[:：,，]?\s*(.+)$",
    re.I | re.S,
)
_QUOTED = re.compile(r"[“「\"](.+?)[”」\"]", re.S)
_AFTER_COLON = re.compile(r"[:：]\s*(.+)$", re.S)


def dictated_text(question: str) -> str | None:
    """Text the merchant explicitly gave: quoted, after a colon, or after "说 / say"."""
    for pattern in (_QUOTED, _AFTER_COLON, _DICTATION):
        if match := pattern.search(question):
            value = match.group(1).strip().strip("。.!！ ")
            if value:
                return value[:800]
    return None


_GREETINGS = ("您好", "你好", "hi", "hello", "dear", "嗨", "早晨", "早上好", "下午好")


def _polite(text: str, language: str) -> str:
    body = text.strip()
    if not body.lower().startswith(_GREETINGS):
        body = _say(language, "您好，", "你好，", "Hi, ") + body
    if body[-1] not in "。.!！?？~～":
        body += "." if language == "en" else "。"
    closing = _say(language, "谢谢！", "多謝！", "Thanks!")
    if body.endswith(closing):
        return body
    return body + (" " if language == "en" else "") + closing


class RuleComposer:
    """Offline composer: wraps only what the merchant dictated; never invents content."""

    engine = "rules"

    def compose(self, request: dict) -> str:
        dictated = request["dictated"]
        if not dictated:
            raise ComposerUnavailable("ASSISTANT_DICTATION_REQUIRED")
        sources = []
        if request["kind"] == "reply_draft":
            sources = request["selected_sources"] or [
                {"message_id": m["message_id"], "message_revision": m["message_revision"]}
                for m in request["messages"][-1:]
            ]
            if not sources:
                raise ComposerUnavailable("ASSISTANT_NO_SOURCE")
        return json.dumps(
            {
                "schema_version": "1.0.0",
                "kind": request["kind"],
                "language": request["language"],
                "text": _polite(dictated, request["language"])[:1000],
                "sources": sources,
                "unverified_claims": [],
            },
            ensure_ascii=False,
        )


def composer_for() -> Composer:
    """Batch 3 ships only the offline composer; the reviewed model arrives in batch 5."""
    return RuleComposer()


def scrub(factory=Session, now=None) -> int:
    """Clear question and answer text after the retention window; keep IDs and codes."""
    now = now or datetime.now(UTC)
    with factory.begin() as db:
        result = db.execute(
            update(AssistantTurn)
            .where(
                AssistantTurn.created_at < now - RETENTION,
                AssistantTurn.scrubbed_at.is_(None),
                AssistantTurn.state.in_(sorted(FINAL)),
            )
            .values(question=None, answer=None, scrubbed_at=now, updated_at=now)
        )
        return result.rowcount or 0
