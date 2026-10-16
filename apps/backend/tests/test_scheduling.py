"""Working-time settings, free slots and risks (方案 §4.4、§5.1、附录 A)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from test_create_order import create

from gigmate.db import TaskRow

HK = ZoneInfo("Asia/Hong_Kong")


def next_weekday(days=3):
    """A future Monday–Friday (default working day) in Hong Kong."""
    day = (datetime.now(HK) + timedelta(days=days)).date()
    while day.isoweekday() > 5:
        day += timedelta(days=1)
    return day


def timed(day, hour, minute=0, minutes=60):
    start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=HK).astimezone(UTC)
    return {
        "kind": "timed",
        "start_at": start.isoformat().replace("+00:00", "Z"),
        "end_at": (start + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
        "timezone": "Asia/Hong_Kong",
    }


def check(client, order):
    response = client.get(f"/api/v1/work-orders/{order['id']}/schedule-check")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def put_settings(client, headers, version=0, **changes):
    current = client.get("/api/v1/settings/schedule").json()["data"]
    body = {**{k: v for k, v in current.items() if k != "version"}, **changes}
    return client.put(
        "/api/v1/settings/schedule",
        json={"expected_version": version, "settings": body},
        headers=headers,
    )


def test_settings_have_defaults_and_versioned_updates(signed_in):
    client, _, _, headers = signed_in
    data = client.get("/api/v1/settings/schedule").json()["data"]
    assert data["work_hours"] == {"start": "09:00", "end": "19:00"}
    assert (data["buffer_minutes"], data["preparation_minutes"], data["version"]) == (30, 60, 0)
    updated = put_settings(client, headers, buffer_minutes=45)
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["version"] == 1
    assert put_settings(client, headers, version=0, buffer_minutes=10).status_code == 409
    outside = put_settings(client, headers, version=1, breaks=[{"start": "20:00", "end": "21:00"}])
    assert outside.status_code == 422


def test_free_slots_respect_hours_breaks_buffers_and_appointments(signed_in):
    client, _, _, headers = signed_in
    day = next_weekday()
    create(client, headers, schedule=timed(day, 10), address="旺角")
    pending = create(client, headers).json()["data"]
    slots = check(client, pending)["suggestions"]
    assert slots
    for slot in slots:
        start = datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00")).astimezone(HK)
        end = datetime.fromisoformat(slot["end_at"].replace("Z", "+00:00")).astimezone(HK)
        assert start.isoweekday() <= 6 and 9 <= start.hour and end.hour * 60 + end.minute <= 19 * 60
        assert not (
            start.hour * 60 + start.minute < 13 * 60 + 30
            and 12 * 60 + 30 < end.hour * 60 + end.minute
        )
        if start.date() == day:
            # 10:00–11:00 is taken; with a 30-minute buffer nothing from 09:30 to 11:30 is offered.
            assert not (
                start < datetime(day.year, day.month, day.day, 11, 30, tzinfo=HK)
                and datetime(day.year, day.month, day.day, 9, 30, tzinfo=HK) < end
            )


def test_risks_name_break_buffer_and_preparation_problems(signed_in):
    client, _, _, headers = signed_in
    day = next_weekday()
    create(client, headers, schedule=timed(day, 15), address="旺角")
    lunch = create(client, headers, schedule=timed(day, 12, 45, 30), address="旺角").json()["data"]
    assert [r["code"] for r in check(client, lunch)["risks"]] == ["during_break"]
    tight = create(client, headers, schedule=timed(day, 16, 15), address="旺角").json()["data"]
    risks = check(client, tight)["risks"]
    assert [r["code"] for r in risks] == ["buffer_too_short"]
    assert check(client, tight)["suggestions"] == []
    soon_start = datetime.now(UTC) + timedelta(minutes=20)
    soon = {
        "kind": "timed",
        "start_at": soon_start.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "end_at": (soon_start + timedelta(hours=1))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "timezone": "Asia/Hong_Kong",
    }
    hurried = create(client, headers, schedule=soon, address="旺角").json()["data"]
    assert "preparation_time_short" in [r["code"] for r in check(client, hurried)["risks"]]


def test_preparation_task_uses_the_merchants_lead_time(signed_in):
    client, factory, _, headers = signed_in
    assert put_settings(client, headers, preparation_minutes=90).status_code == 200
    day = next_weekday()
    order = create(client, headers, schedule=timed(day, 16), address="旺角").json()["data"]
    with factory() as db:
        [task] = db.scalars(select(TaskRow).where(TaskRow.work_order_id == order["id"]))
    assert task.data["title"].startswith(f"{day:%m/%d} 14:30 准备 16:00 的")


def test_conflict_question_offers_a_checked_free_time(signed_in):
    client, factory, _, headers = signed_in
    from test_approvals import conflict_draft

    action = conflict_draft(client, factory, headers)
    assert "已有其他安排" in action["body"]
    assert action["body"].endswith("可以吗？")
