"""方案 §4.6 每日摘要 and rule-based suggestions; every entry points at its record."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from test_create_order import SAID, create
from test_scheduling import next_weekday, put_settings, timed


def summary(client, day):
    response = client.get("/api/v1/daily-summary", params={"date": day.isoformat()})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_summary_groups_today_waiting_and_decisions_with_their_records(signed_in):
    client, _, _, headers = signed_in
    day = next_weekday(5)
    booked = create(client, headers, schedule=timed(day, 10), address="旺角").json()["data"]
    pending = create(client, headers, summary="李先生家居维修").json()["data"]
    data = summary(client, day)
    kinds = {(entry["kind"], entry["work_order_id"]) for entry in data["today"]}
    assert ("appointment", booked["id"]) in kinds
    assert ("task", booked["id"]) in kinds
    titles = [entry["title"] for entry in data["today"]]
    assert "10:00 陈小姐证件照拍摄" in titles
    waiting = {entry["work_order_id"]: entry for entry in data["waiting_for_customer"]}
    assert waiting[pending["id"]]["open_items"] == ["missing_schedule", "missing_address"]
    decide = [entry for entry in data["needs_decision"] if entry["kind"] == "approve_reply"]
    assert pending["id"] in {entry["work_order_id"] for entry in decide}
    assert all(entry["action_id"] for entry in decide)


def test_suggestions_explain_overdue_missing_and_overbooked_days(signed_in):
    client, _, _, headers = signed_in
    assert (
        put_settings(
            client, headers, work_hours={"start": "09:00", "end": "11:00"}, breaks=[]
        ).status_code
        == 200
    )
    day = next_weekday(5)
    first = create(client, headers, schedule=timed(day, 9), address="旺角").json()["data"]
    create(client, headers, schedule=timed(day, 10), address="中环", summary="王小姐化妆")
    past = (datetime.now(UTC) - timedelta(hours=2)).replace(microsecond=0)
    added = client.post(
        f"/api/v1/work-orders/{first['id']}/requirements",
        json={
            "kind": "material",
            "text": "证件尺寸",
            "owner": "customer",
            "due": {
                "kind": "instant",
                "at": past.isoformat().replace("+00:00", "Z"),
                "timezone": "Asia/Hong_Kong",
            },
            "sources": SAID,
            "expected_version": first["version"],
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert added.status_code == 200, added.text
    codes = {entry["code"] for entry in summary(client, day)["suggestions"]}
    assert {"task_overdue", "material_missing", "day_overbooked"} <= codes


def test_summary_date_must_be_a_date(signed_in):
    client, _, _, _ = signed_in
    assert client.get("/api/v1/daily-summary", params={"date": "today"}).status_code == 422
    assert client.get("/api/v1/daily-summary").status_code == 200
