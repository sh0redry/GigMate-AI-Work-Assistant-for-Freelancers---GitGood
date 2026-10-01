from datetime import datetime

from sqlalchemy import select

from gigmate.contracts import TimedSchedule
from gigmate.db import CalendarRow


def conflicts(db, account_id, work_order_id, schedule):
    proposed = TimedSchedule.model_validate_json(__import__("json").dumps(schedule))
    start, end = datetime.fromisoformat(proposed.start_at), datetime.fromisoformat(proposed.end_at)
    matches = []
    for row in db.scalars(
        select(CalendarRow).where(
            CalendarRow.account_id == account_id, CalendarRow.work_order_id != work_order_id
        )
    ):
        current = row.data["schedule"]
        if (
            not row.data["tentative"]
            and current["kind"] == "timed"
            and start < datetime.fromisoformat(current["end_at"])
            and datetime.fromisoformat(current["start_at"]) < end
        ):
            matches.append(row.id)
    return matches
