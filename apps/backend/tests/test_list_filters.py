"""Contract inventory filters: orders by status, tasks by order, calendar by time window."""

from datetime import UTC, datetime, timedelta

from test_create_order import create, future


def iso(moment):
    return moment.isoformat().replace("+00:00", "Z")


def test_orders_filter_by_status(signed_in):
    client, _, _, headers = signed_in
    pending = create(client, headers).json()["data"]
    confirmed = create(client, headers, schedule=future(days=4), address="旺角").json()["data"]
    shown = client.get("/api/v1/work-orders", params={"status": "pending_confirmation"}).json()
    ids = {item["id"] for item in shown["items"]}
    assert pending["id"] in ids and confirmed["id"] not in ids
    assert client.get("/api/v1/work-orders", params={"status": "nonsense"}).status_code == 422


def test_tasks_filter_by_work_order(signed_in):
    client, _, _, headers = signed_in
    order = create(client, headers, schedule=future(days=4), address="旺角").json()["data"]
    items = client.get("/api/v1/tasks", params={"work_order_id": order["id"]}).json()["items"]
    assert len(items) == 1 and items[0]["work_order_id"] == order["id"]
    assert len(client.get("/api/v1/tasks", params={"limit": 100}).json()["items"]) > 1


def test_calendar_filters_by_overlapping_window(signed_in):
    client, _, _, headers = signed_in
    order = create(client, headers, schedule=future(days=10)).json()["data"]
    start = datetime.fromisoformat(
        order["fields"]["schedule"]["value"]["start_at"].replace("Z", "+00:00")
    )
    day = (datetime.now(UTC) + timedelta(days=12)).date().isoformat()
    create(
        client, headers, schedule={"kind": "date_only", "date": day, "timezone": "Asia/Hong_Kong"}
    )
    window = {
        "start": iso(start - timedelta(minutes=30)),
        "end": iso(start + timedelta(minutes=30)),
    }
    items = client.get("/api/v1/calendar-events", params=window).json()["items"]
    assert [item["work_order_id"] for item in items] == [order["id"]]
    later = {"start": iso(start + timedelta(days=1)), "end": iso(start + timedelta(days=3))}
    items = client.get("/api/v1/calendar-events", params=later).json()["items"]
    assert len(items) == 1 and items[0]["tentative"] is True
    bad = client.get("/api/v1/calendar-events", params={"start": "tomorrow"})
    assert bad.status_code == 422
    reversed_window = {"start": window["end"], "end": window["start"]}
    assert client.get("/api/v1/calendar-events", params=reversed_window).status_code == 422
