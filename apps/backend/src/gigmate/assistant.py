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
from gigmate.assistant_plan import AssistantPlan
from gigmate.contracts import (
    AssistantAnswer,
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
_REPLY = ("回复", "回覆", "回一下", "帮我回", "幫我回", "回佢", "reply", "respond")
_AVAILABILITY = (
    "有空",
    "空闲",
    "空閒",
    "得閒",
    "有冇時間",
    "档期",
    "檔期",
    "排得",
    "free",
    "available",
    "availability",
    "slot",
)
_ORDERS = ("工单", "工單", "订单", "訂單", "进度", "進度", "order", "status", "等客")
_WAITING = ("等客户", "等客戶", "等客人", "waiting")
_THIS_CUSTOMER = ("这个客户", "這個客戶", "呢個客", "this customer", "this client")
_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:个?小时|個?小時|个钟|個鐘|hours?|hrs?|h\b)", re.I)
_MINUTES = re.compile(r"(\d+)\s*(?:分钟|分鐘|mins?|minutes?)", re.I)


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
    if _has(text, ("下周", "下週", "下星期", "下禮拜", "next week")):
        start = today + timedelta(days=7 - today.weekday())
        return start, start + timedelta(days=6)
    if _has(text, ("明天", "聽日", "tomorrow")):
        day = today + timedelta(days=1)
        return day, day
    if _has(text, ("今天", "今日", "today")):
        return today, today
    if _has(text, ("这周", "這週", "本周", "本週", "this week")):
        return today, today + timedelta(days=6 - today.weekday())
    return today, today + timedelta(days=6)


def _duration(text: str) -> int:
    if match := _HOURS.search(text):
        return max(15, min(720, round(float(match.group(1)) * 60)))
    if match := _MINUTES.search(text):
        return max(15, min(720, int(match.group(1))))
    return 60


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
                        "duration_minutes": _duration(text),
                        "from_date": start.isoformat(),
                        "to_date": end.isoformat(),
                    }
                ],
            }
        elif _has(text, _ORDERS):
            scope = (
                "selected_conversation"
                if selection["conversation"] and _has(text, _THIS_CUSTOMER)
                else "account"
            )
            status = "waiting_customer" if _has(text, _WAITING) else "open"
            plan = {
                **base,
                "intent": "order_status",
                "tool_calls": [{"tool": "list_work_orders", "status": status, "scope": scope}],
            }
        else:
            plan = {**base, "intent": "unsupported", "tool_calls": []}
        return json.dumps(plan, ensure_ascii=False)


def planner_for() -> Planner:
    """Batch 1 ships only the offline planner; the reviewed model arrives in batch 5."""
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
    },
    "zh-Hant": {
        "pending_confirmation": "待確認",
        "confirmed": "已確認",
        "in_progress": "進行中",
        "waiting_customer": "等客人回覆",
        "completed": "已完成",
        "cancelled": "已取消",
    },
    "en": {
        "pending_confirmation": "pending confirmation",
        "confirmed": "confirmed",
        "in_progress": "in progress",
        "waiting_customer": "waiting for customer",
        "completed": "completed",
        "cancelled": "cancelled",
    },
}
_WEEKDAY_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _say(language: str, zh: str, hant: str, en: str) -> str:
    return {"zh-Hans": zh, "zh-Hant": hant}.get(language, en)


def _slot_line(slot: dict, timezone: str, language: str) -> str:
    from zoneinfo import ZoneInfo

    start = scheduling.parse(slot["start_at"]).astimezone(ZoneInfo(timezone))
    end = scheduling.parse(slot["end_at"]).astimezone(ZoneInfo(timezone))
    if language == "en":
        return f"{_WEEKDAY_EN[start.weekday()]} {start:%m/%d} {start:%H:%M}–{end:%H:%M}"
    return f"{slot['label']}–{end:%H:%M}"


def _citations(results: list[dict]) -> list[dict]:
    seen, out = set(), []
    for result in results:
        for item in result.get("citations", []):
            key = json.dumps(item, sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


def render(plan: AssistantPlan, results: list[dict]) -> dict:
    language = plan.language
    citations = _citations(results)
    if plan.intent == "clarify":
        answer = {"kind": "clarification", "text": plan.clarification_question}
    elif plan.intent == "availability":
        found = next(r for r in results if "slots" in r)
        hours = f"{found['duration_minutes'] / 60:g}"
        if found["slots"]:
            lines = "\n".join(
                "- " + _slot_line(s, found["timezone"], language) for s in found["slots"]
            )
            head = _say(
                language,
                f"可安排 {hours} 小时的时段（{found['timezone']}）：",
                f"可安排 {hours} 小時嘅時段（{found['timezone']}）：",
                f"Free {hours}-hour slots ({found['timezone']}):",
            )
            text = head + "\n" + lines
        else:
            text = _say(
                language,
                f"这段时间内没有可安排 {hours} 小时的空闲时段。",
                f"呢段時間冇可安排 {hours} 小時嘅空檔。",
                f"No free {hours}-hour slot in that period.",
            )
        answer = {"kind": "slots", "text": text, "slots": found["slots"]}
    elif plan.intent == "order_status":
        orders = next(r for r in results if "orders" in r)["orders"]
        labels = _STATUS[language]
        if orders:
            head = _say(
                language,
                f"共 {len(orders)} 张工单：",
                f"共 {len(orders)} 張工單：",
                f"{len(orders)} work orders:",
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
                language, "没有符合条件的工单。", "冇符合條件嘅工單。", "No matching work orders."
            )
        answer = {"kind": "orders", "text": text, "work_order_ids": [o["id"] for o in orders]}
    elif plan.intent in {"reply_draft", "polish"}:
        # Drafting arrives in batch 3; until then say so instead of inventing text.
        answer = {
            "kind": "unsupported",
            "text": _say(
                language,
                "生成回复草稿与润色尚未开放；目前请在客户会话中手动回复。",
                "生成回覆草稿同潤色仲未開放；暫時請喺客人對話手動回覆。",
                "Reply drafts and polishing are not available yet; reply manually in the chat.",
            ),
        }
    else:
        answer = {
            "kind": "unsupported",
            "text": _say(
                language,
                "我只能帮你查空闲时段、查工单状态，以及（即将开放）准备回复草稿。其他操作请使用对应页面。",
                "我只可以幫你查空檔、查工單狀態，同埋（即將開放）準備回覆草稿。其他操作請用對應頁面。",
                "I can check free slots and work-order status, and soon prepare reply drafts. "
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
        request = {
            "question": turn.question,
            "today": now.astimezone(ZoneInfo(config.timezone)).date().isoformat(),
            "timezone": config.timezone,
            "selection": {
                "conversation": context.conversation_id is not None,
                "work_order": context.work_order_id is not None,
                "selected_sources": len(context.selected_sources),
            },
        }
        return turn.id, token, request


def run_once(factory=Session, *, planner: Planner | None = None, now=None) -> bool:
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
        turn = db.scalar(
            select(AssistantTurn)
            .where(AssistantTurn.id == turn_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if turn is None or turn.state != "running" or turn.lease_token != token:
            return True
        turn.engine = getattr(planner, "engine", None)
        if outcome:
            _finish(turn, outcome[0], finished_at, code=outcome[1])
            return True
        turn.intent = plan.intent
        try:
            scope = resolve_scope(
                db, turn.account_id, AssistantContext.model_validate(turn.context)
            )
        except BusinessError as error:
            state = "superseded" if error.code == "ASSISTANT_CONTEXT_STALE" else "failed"
            _finish(turn, state, finished_at, code=error.code)
            return True
        results, used = [], []
        try:
            for call in plan.tool_calls:
                results.append(assistant_tools.run(db, scope, call))
                used.append(call.tool)
            answer = render(plan, results)
        except assistant_tools.ToolUnavailable as error:
            plan = AssistantPlan.model_validate(
                _clarify(
                    plan.language,
                    "请先选择相关的聊天或工单，再问一次。",
                    "請先揀選相關嘅聊天或者工單，再問一次。",
                    "Select the related chat or work order first, then ask again.",
                )
            )
            turn.intent, results, used = "clarify", [], used + [f"refused:{error.code}"]
            answer = render(plan, results)
        turn.trace = {"tools": used, "language": plan.language}
        _finish(turn, "completed", finished_at, answer=answer)
        log.info("assistant_turn_completed turn=%s intent=%s", turn.id, turn.intent)
    return True


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
