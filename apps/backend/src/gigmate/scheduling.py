"""Working-time settings, free slots and schedule risks (方案 §4.4、§5.1、附录 A).

Everything here is deterministic: the model never proposes a time. A
suggested slot only comes from the merchant's own working hours, breaks,
durations and buffers and from confirmed appointments. Buffers are the
user's own numbers; no travel time is estimated.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from gigmate.contracts import ScheduleSettings
from gigmate.db import CalendarRow, ScheduleSettingsRow, WorkOrderRow
from gigmate.errors import BusinessError
from gigmate.planning import CLOSED

WEEKDAYS = "一二三四五六日"
STEP = timedelta(minutes=30)


def settings(db, account_id):
    row = db.get(ScheduleSettingsRow, account_id)
    return ScheduleSettings.model_validate(row.data) if row else ScheduleSettings()


def update(db, account_id, command):
    row = db.scalar(
        select(ScheduleSettingsRow)
        .where(ScheduleSettingsRow.account_id == account_id)
        .with_for_update()
    )
    current = row.data["version"] if row else 0
    if command.expected_version != current:
        raise BusinessError(409, "VERSION_CONFLICT", "Settings changed; reload them first")
    data = command.settings.model_dump(mode="json")
    data["version"] = current + 1
    for item in data["breaks"]:
        if not (
            data["work_hours"]["start"] <= item["start"] < item["end"] <= data["work_hours"]["end"]
        ):
            raise BusinessError(422, "VALIDATION_FAILED", "Breaks must sit inside working hours")
    if row:
        row.data = data
    else:
        db.add(ScheduleSettingsRow(account_id=account_id, data=data))
    db.flush()
    return data


def parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def text(moment):
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def label(moment, timezone):
    local = moment.astimezone(ZoneInfo(timezone))
    return f"{local:%m/%d}（周{WEEKDAYS[local.weekday()]}）{local:%H:%M}"


def busy(db, account_id, exclude_order_id=None):
    """Confirmed timed appointments of open orders: (start, end, order id)."""
    result = []
    for row, order in db.execute(
        select(CalendarRow, WorkOrderRow)
        .join(WorkOrderRow, WorkOrderRow.id == CalendarRow.work_order_id)
        .where(CalendarRow.account_id == account_id)
    ):
        schedule = row.data["schedule"]
        if (
            order.id == exclude_order_id
            or order.data["status"] in CLOSED
            or row.data["tentative"]
            or schedule["kind"] != "timed"
        ):
            continue
        result.append((parse(schedule["start_at"]), parse(schedule["end_at"]), order.id))
    return result


def local_minutes(moment, timezone):
    local = moment.astimezone(ZoneInfo(timezone))
    return local.hour * 60 + local.minute


def hhmm(value):
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def inside_work(start, end, config):
    """True when [start, end) is on a working day, inside hours, outside breaks."""
    tz = config.timezone
    local_start = start.astimezone(ZoneInfo(tz))
    if local_start.isoweekday() not in config.work_days:
        return False
    if local_start.date() != (end - timedelta(seconds=1)).astimezone(ZoneInfo(tz)).date():
        return False
    begin, finish = local_minutes(start, tz), local_minutes(end, tz) or 24 * 60
    if begin < hhmm(config.work_hours.start) or finish > hhmm(config.work_hours.end):
        return False
    return not any(begin < hhmm(b.end) and hhmm(b.start) < finish for b in config.breaks)


def free_slots(db, account_id, duration, after, *, exclude_order_id=None, count=3, days=14):
    """Free working-time slots of ``duration`` at or after ``after``, honoring buffers.

    A slot also leaves room for the merchant's preparation lead time from now.
    """
    config = settings(db, account_id)
    tz = ZoneInfo(config.timezone)
    buffer = timedelta(minutes=config.buffer_minutes)
    earliest = max(after, datetime.now(UTC) + timedelta(minutes=config.preparation_minutes))
    taken = busy(db, account_id, exclude_order_id)
    local = earliest.astimezone(tz)
    cursor = local.replace(
        minute=0 if local.minute == 0 else 30 if local.minute <= 30 else 0, second=0, microsecond=0
    )
    if local.minute > 30:
        cursor += timedelta(hours=1)
    end_search = earliest + timedelta(days=days)
    found = []
    while cursor.astimezone(UTC) < end_search and len(found) < count:
        start = cursor.astimezone(UTC)
        end = start + duration
        if (
            start >= earliest
            and inside_work(start, end, config)
            and not any(
                start < other_end + buffer and other_start - buffer < end
                for other_start, other_end, _ in taken
            )
        ):
            found.append(
                {
                    "start_at": text(start),
                    "end_at": text(end),
                    "label": label(start, config.timezone),
                }
            )
        cursor += STEP
    return found


def risks(db, account_id, order):
    """Checks for an order's own timed schedule (方案 §4.4: 时间重叠、缺少准备时间)."""
    schedule = order.data["fields"]["schedule"]["value"]
    if not isinstance(schedule, dict) or schedule.get("kind") != "timed":
        return []
    config = settings(db, account_id)
    start, end = parse(schedule["start_at"]), parse(schedule["end_at"])
    found = []
    now = datetime.now(UTC)
    if start <= now:
        found.append({"code": "in_the_past", "detail": "预约时间已经过去"})
    elif start - now < timedelta(minutes=config.preparation_minutes):
        found.append(
            {
                "code": "preparation_time_short",
                "detail": f"距开始不足 {config.preparation_minutes} 分钟准备时间",
            }
        )
    if not inside_work(start, end, config):
        local_start = start.astimezone(ZoneInfo(config.timezone))
        if local_start.isoweekday() in config.work_days and any(
            local_minutes(start, config.timezone) < hhmm(b.end)
            and hhmm(b.start) < (local_minutes(end, config.timezone) or 1440)
            for b in config.breaks
        ):
            found.append({"code": "during_break", "detail": "时间落在休息时段"})
        else:
            found.append({"code": "outside_working_hours", "detail": "时间不在设定的工作时间内"})
    buffer = timedelta(minutes=config.buffer_minutes)
    overlapping, tight = [], []
    for other_start, other_end, other_id in busy(db, account_id, order.id):
        if start < other_end and other_start < end:
            overlapping.append(other_id)
        elif start < other_end + buffer and other_start - buffer < end:
            tight.append(other_id)
    if overlapping:
        found.append(
            {
                "code": "schedule_conflict",
                "detail": "与已确认的预约重叠",
                "related_work_order_ids": sorted(set(overlapping)),
            }
        )
    if tight:
        found.append(
            {
                "code": "buffer_too_short",
                "detail": f"与前后预约间隔少于 {config.buffer_minutes} 分钟",
                "related_work_order_ids": sorted(set(tight)),
            }
        )
    return found


def check(db, account_id, order):
    """Risks plus free slots of the same length when something needs changing."""
    found = risks(db, account_id, order)
    schedule = order.data["fields"]["schedule"]["value"]
    config = settings(db, account_id)
    if isinstance(schedule, dict) and schedule.get("kind") == "timed":
        duration = parse(schedule["end_at"]) - parse(schedule["start_at"])
        after = parse(schedule["start_at"])
    else:
        duration = timedelta(minutes=config.default_duration_minutes)
        after = datetime.now(UTC)
    blocking = {"schedule_conflict", "outside_working_hours", "during_break", "in_the_past"}
    timed = isinstance(schedule, dict) and schedule.get("kind") == "timed"
    wanted = not timed or any(item["code"] in blocking for item in found)
    suggestions = (
        free_slots(db, account_id, duration, after, exclude_order_id=order.id) if wanted else []
    )
    return {"work_order_id": order.id, "risks": found, "suggestions": suggestions}
