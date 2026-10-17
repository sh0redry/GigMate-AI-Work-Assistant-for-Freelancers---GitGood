"""Daily summary and rule-based business suggestions (方案 §4.6).

Read-only aggregation of records that already exist. Each entry names the
record it comes from, so the merchant can open the basis; nothing here
changes a business commitment.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from gigmate import approvals, scheduling
from gigmate.db import (
    ActionRow,
    CalendarRow,
    ChangeRow,
    ConversationRow,
    Inbox,
    Job,
    TaskRow,
    WorkOrderRow,
)
from gigmate.planning import CLOSED

FIELD_NAMES = {
    "schedule": "时间安排",
    "address": "地址",
    "summary": "业务内容",
    "specification": "规格",
    "quantity": "数量",
    "deadline": "截止时间",
}

SOON = timedelta(hours=48)


def parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def task_due(task):
    due = task["due"]
    if not due:
        return None
    if due["kind"] == "date_only":
        day = date.fromisoformat(due["date"])
        return datetime(day.year, day.month, day.day, 23, 59, tzinfo=ZoneInfo(due["timezone"]))
    return parse(due["at"])


def build(db, account_id, day=None, now=None):
    now = now or datetime.now(UTC)
    config = scheduling.settings(db, account_id)
    tz = ZoneInfo(config.timezone)
    day = day or now.astimezone(tz).date()
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=1)
    orders = {
        row.id: row
        for row in db.scalars(select(WorkOrderRow).where(WorkOrderRow.account_id == account_id))
    }
    summary_of = {key: row.data["summary"] for key, row in orders.items()}
    today, waiting, due_soon, decide, suggestions = [], [], [], [], []

    # Today: appointments (formal and tentative) and tasks due today.
    busy_minutes = 0
    for row in db.scalars(select(CalendarRow).where(CalendarRow.account_id == account_id)):
        order = orders.get(row.work_order_id)
        if order is None or order.data["status"] in CLOSED:
            continue
        schedule = row.data["schedule"]
        if schedule["kind"] == "timed":
            begins, finishes = parse(schedule["start_at"]), parse(schedule["end_at"])
            if begins < end and start < finishes:
                today.append(
                    {
                        "kind": "appointment",
                        "title": f"{begins.astimezone(tz):%H:%M} {order.data['summary']}"
                        + ("（暂定）" if row.data["tentative"] else ""),
                        "at": begins.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                        "work_order_id": order.id,
                        "calendar_event_id": row.id,
                    }
                )
                if not row.data["tentative"]:
                    busy_minutes += int((finishes - begins).total_seconds() // 60)
        elif schedule["date"] == day.isoformat():
            today.append(
                {
                    "kind": "appointment",
                    "title": f"全天 {order.data['summary']}（暂定）",
                    "at": None,
                    "work_order_id": order.id,
                    "calendar_event_id": row.id,
                }
            )
    for row in db.scalars(select(TaskRow).where(TaskRow.account_id == account_id)):
        task = row.data
        if task["state"] not in {"pending", "blocked"}:
            continue
        due = task_due(task)
        entry = {
            "kind": "task",
            "title": task["title"],
            "at": due.astimezone(UTC).isoformat().replace("+00:00", "Z") if due else None,
            "work_order_id": row.work_order_id,
            "task_id": row.id,
        }
        if due is None:
            continue
        if due < now:
            suggestions.append(
                {
                    "code": "task_overdue",
                    "detail": f"待办已过期：{task['title']}",
                    "work_order_id": row.work_order_id,
                    "task_id": row.id,
                }
            )
        elif start <= due < end:
            today.append(entry)
        elif due < now + SOON:
            due_soon.append(entry)

    # Waiting for the customer: pending orders with open items, or orders set to wait.
    for order in orders.values():
        data = order.data
        if data["status"] == "waiting_customer":
            waiting.append({"title": f"{data['summary']}：等待客人", "work_order_id": order.id})
        elif data["status"] == "pending_confirmation":
            items, _ = approvals.open_items(data)
            deferred = sorted((data.get("deferred") or {}).keys())
            parts = items + [f"deferred_{name}" for name in deferred]
            waiting.append(
                {
                    "title": f"{data['summary']}：待确认",
                    "work_order_id": order.id,
                    "open_items": parts,
                }
            )
        if "customer_not_replying" in (data.get("attention") or []):
            decide.append(
                {
                    "kind": "customer_not_replying",
                    "title": f"{data['summary']}：客人一直未回复，要怎么处理？",
                    "work_order_id": order.id,
                }
            )
        for item in data.get("requirements") or []:
            if item["status"] != "open" or item["kind"] != "material":
                continue
            if item.get("due") and task_due({"due": item["due"]}) < now:
                suggestions.append(
                    {
                        "code": "material_missing",
                        "detail": f"{data['summary']}：{item['text']} 还没收到",
                        "work_order_id": order.id,
                    }
                )
        deadline = data["fields"].get("deadline") or {}
        if (
            data["status"] not in CLOSED
            and deadline.get("status") == "confirmed"
            and any(
                entry["status"] == "open" and entry["kind"] in {"material", "commitment"}
                for entry in data.get("requirements") or []
            )
            and task_due({"due": deadline["value"]}) < now + SOON
        ):
            suggestions.append(
                {
                    "code": "dependency_at_risk",
                    "detail": f"{data['summary']}：交付期限将到，仍有未完成的资料或承诺",
                    "work_order_id": order.id,
                }
            )

    # Needs a decision: drafts to approve, proposals to confirm, messages to file, unknown sends.
    action_rows = list(db.scalars(select(ActionRow).where(ActionRow.account_id == account_id)))
    for item in approvals.views(db, action_rows) if action_rows else []:
        if item["state"] == "pending_approval":
            decide.append(
                {
                    "kind": "approve_reply",
                    "title": f"{summary_of.get(item['work_order_id'], '')}：有一条回复等你批准",
                    "work_order_id": item["work_order_id"],
                    "action_id": item["id"],
                }
            )
        elif item["state"] == "result_unknown":
            decide.append(
                {
                    "kind": "check_send_result",
                    "title": f"{summary_of.get(item['work_order_id'], '')}：发送结果未知，请先核对",
                    "work_order_id": item["work_order_id"],
                    "action_id": item["id"],
                }
            )
    for change in db.scalars(select(ChangeRow).where(ChangeRow.account_id == account_id)):
        order = orders.get(change.work_order_id)
        if (
            order
            and order.data["status"] not in CLOSED
            and change.data["status"]
            in {
                "proposed",
                "needs_review",
            }
        ):
            decide.append(
                {
                    "kind": "review_proposal",
                    "title": f"{order.data['summary']}：客人提出新的{FIELD_NAMES.get(change.data['field'], '内容')}，要确认吗？",
                    "work_order_id": order.id,
                    "change_id": change.id,
                }
            )
    allowed = {
        row.id
        for row in db.scalars(
            select(ConversationRow).where(
                ConversationRow.account_id == account_id, ConversationRow.allowlisted.is_(True)
            )
        )
    }
    for job, inbox in db.execute(
        select(Job, Inbox)
        .join(Inbox, Job.event_id == Inbox.id)
        .where(
            Job.account_id == account_id,
            Job.error_code.in_(["ASSIGNMENT_NEEDS_REVIEW", "EXTRACTION_NEEDS_REVIEW"]),
        )
    ):
        if inbox.payload.get("conversation_id") in allowed:
            decide.append(
                {
                    "kind": "file_message",
                    "title": "有一条消息需要你决定归到哪一单",
                    "job_id": job.id,
                }
            )

    working = scheduling.hhmm(config.work_hours.end) - scheduling.hhmm(config.work_hours.start)
    working -= sum(scheduling.hhmm(b.end) - scheduling.hhmm(b.start) for b in config.breaks)
    appointments = [entry for entry in today if entry["kind"] == "appointment" and entry["at"]]
    needed = busy_minutes + config.buffer_minutes * max(len(appointments) - 1, 0)
    if needed > working > 0:
        suggestions.append(
            {
                "code": "day_overbooked",
                "detail": f"今天预约和缓冲共 {needed} 分钟，超过可用工作时间 {working} 分钟",
            }
        )
    today.sort(key=lambda entry: entry["at"] or "")
    due_soon.sort(key=lambda entry: entry["at"] or "")
    return {
        "date": day.isoformat(),
        "timezone": config.timezone,
        "today": today,
        "waiting_for_customer": waiting,
        "due_soon": due_soon,
        "needs_decision": decide,
        "suggestions": suggestions,
    }
