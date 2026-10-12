import json
from datetime import datetime

from sqlalchemy import select

from gigmate.contracts import TimedSchedule
from gigmate.db import CalendarRow, WorkOrderRow

CLOSED = {"cancelled", "completed"}


def overlaps(db, account_id, work_order_id, schedule):
    """Yield (calendar row, order row) pairs whose confirmed time overlaps ``schedule``."""
    proposed = TimedSchedule.model_validate_json(json.dumps(schedule))
    start, end = datetime.fromisoformat(proposed.start_at), datetime.fromisoformat(proposed.end_at)
    query = (
        select(CalendarRow, WorkOrderRow)
        .join(WorkOrderRow, WorkOrderRow.id == CalendarRow.work_order_id)
        .where(CalendarRow.account_id == account_id)
    )
    if work_order_id:
        query = query.where(CalendarRow.work_order_id != work_order_id)
    for row, order in db.execute(query):
        current = row.data["schedule"]
        # Cancelled or completed orders no longer occupy their time slot.
        if (
            order.data["status"] not in CLOSED
            and not row.data["tentative"]
            and current["kind"] == "timed"
            and start < datetime.fromisoformat(current["end_at"])
            and datetime.fromisoformat(current["start_at"]) < end
        ):
            yield row, order


def conflicts(db, account_id, work_order_id, schedule):
    return [row.id for row, _ in overlaps(db, account_id, work_order_id, schedule)]


def conflicting_orders(db, account_id, work_order_id, schedule):
    return sorted({order.id for _, order in overlaps(db, account_id, work_order_id, schedule)})
