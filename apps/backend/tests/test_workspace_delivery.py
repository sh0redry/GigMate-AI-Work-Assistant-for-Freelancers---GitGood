"""Delivery reads are owned, allowlisted, read-only and honest about pending work."""

import copy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from gigmate.db import AuditRow, CalendarRow, ConversationRow, Inbox, Job, WorkOrderRow
from gigmate.seed import uid


def test_capabilities_fail_closed_for_unimplemented_commands(environment, signed_in):
    client, _, _, _ = signed_in
    result = client.get("/api/v1/workspace-capabilities")
    assert result.status_code == 200
    assert result.json()["data"] == {
        "calendar_export": True,
        "create_order": True,
        "order_status": True,
        "address_confirmation": True,
        "manual_assignment": True,
        "business_sending": True,
        "automatic_understanding": False,
        "business_loop_reviewed": True,
    }
    client.cookies.clear()
    assert client.get("/api/v1/workspace-capabilities").status_code == 401
    assert client.get("/api/v1/conversations").status_code == 401
    assert client.get("/api/v1/review-items").status_code == 401


def test_conversation_list_is_owned_allowlisted_and_paged(signed_in):
    client, factory, _, _ = signed_in
    new_id = str(uuid4())
    with factory.begin() as db:
        db.add(ConversationRow(id=new_id, account_id=uid(1), context_version=1, allowlisted=True))
    first = client.get("/api/v1/conversations?limit=1").json()
    assert len(first["items"]) == 1
    rows = first["items"]
    cursor = first["next_cursor"]
    while cursor:
        next_page = client.get(
            "/api/v1/conversations", params={"limit": 1, "cursor": cursor}
        ).json()
        rows.extend(next_page["items"])
        cursor = next_page["next_cursor"]
    assert new_id in {row["id"] for row in rows}
    assert uid(2) in {row["id"] for row in rows}
    assert uid(22) not in {row["id"] for row in rows}
    with factory.begin() as db:
        db.get(ConversationRow, uid(2)).allowlisted = False
    assert uid(2) not in [row["id"] for row in client.get("/api/v1/conversations").json()["items"]]
    assert client.get("/api/v1/conversations?cursor=bad").status_code == 422


def calendar_ids(factory):
    with factory() as db:
        return {
            row.account_id: row.id
            for row in db.scalars(
                select(CalendarRow).where(CalendarRow.work_order_id.in_([uid(3), uid(23)]))
            )
        }


def test_calendar_download_owned_readonly_utc_escaped_and_utf8_folded(signed_in):
    client, factory, _, _ = signed_in
    ids = calendar_ids(factory)
    with factory.begin() as db:
        row = db.get(WorkOrderRow, uid(3))
        data = copy.deepcopy(row.data)
        data["summary"] = "客户，摄影;" + "中文🌅" * 45 + "\r\nBEGIN:VALARM"
        data["fields"]["address"] = {
            "value": "九龙，A座;3楼\n门口\\等候",
            "status": "confirmed",
            "sources": data["fields"]["schedule"]["sources"],
            "interpretation": None,
        }
        row.data = data
        audit_count = db.scalar(select(func.count()).select_from(AuditRow))
    path = f"/api/v1/calendar-events/{ids[uid(1)]}.ics"
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert ".ics" in response.headers["content-disposition"]
    raw = response.content
    assert all(len(line) <= 75 for line in raw.split(b"\r\n"))
    unfolded = response.text.replace("\r\n ", "")
    assert "SUMMARY:客户\\，" not in unfolded  # ASCII separators alone need escaping.
    assert "\\;" + ("中文🌅" * 45) in unfolded
    assert "\\nBEGIN:VALARM" in unfolded
    assert "\r\nBEGIN:VALARM\r\n" not in unfolded
    assert "LOCATION:九龙，A座\\;3楼\\n门口\\\\等候" in unfolded
    assert f"UID:{ids[uid(1)]}@gigmate.local\r\n" in unfolded
    assert "DTSTART:" in unfolded and "Z\r\nDTEND:" in unfolded
    assert client.get(path).status_code == 200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditRow)) == audit_count
    assert client.get(f"/api/v1/calendar-events/{ids[uid(99)]}.ics").status_code == 404
    assert client.get(f"/api/v1/calendar-events/{uuid4()}.ics").status_code == 404
    client.cookies.clear()
    assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "case",
    [
        "tentative",
        "date_only",
        "cancelled",
        "completed",
        "future_version",
        "changed_schedule",
        "changed_sources",
    ],
)
def test_calendar_refuses_noncurrent_or_nonformal_events(signed_in, case):
    client, factory, _, _ = signed_in
    event_id = calendar_ids(factory)[uid(1)]
    with factory.begin() as db:
        event = db.get(CalendarRow, event_id)
        order = db.get(WorkOrderRow, uid(3))
        e, o = copy.deepcopy(event.data), copy.deepcopy(order.data)
        if case == "tentative":
            e["tentative"] = True
        elif case == "date_only":
            e["schedule"] = o["fields"]["schedule"]["value"] = {
                "kind": "date_only",
                "date": "2026-11-01",
                "timezone": "Asia/Hong_Kong",
            }
        elif case in {"cancelled", "completed"}:
            o["status"] = case
        elif case == "future_version":
            e["work_order_version"] = o["version"] + 1
        elif case == "changed_sources":
            o["fields"]["schedule"]["sources"] = [
                {"message_id": str(uuid4()), "message_revision": 1}
            ]
        else:
            o["fields"]["schedule"]["value"]["start_at"] = "2026-11-01T00:00:00Z"
        event.data = e
        order.data = o
    response = client.get(f"/api/v1/calendar-events/{event_id}.ics")
    assert response.status_code == 409
    assert response.json()["error"]["code"] in {"VERSION_CONFLICT", "CALENDAR_NOT_EXPORTABLE"}


def test_review_queue_contains_only_owned_authorized_metadata_and_is_readonly(signed_in):
    client, factory, _, _ = signed_in
    now = datetime.now(UTC)
    ids = []
    with factory.begin() as db:
        for account, conversation, reason in [
            (uid(1), uid(2), "ASSIGNMENT_NEEDS_REVIEW"),
            (uid(99), uid(22), "PROCESSING_FAILED"),
            (uid(1), uid(2), "OWN_SEND_ECHO"),
        ]:
            event_id, job_id = str(uuid4()), str(uuid4())
            ids.append(job_id)
            db.add(
                Inbox(
                    id=event_id,
                    account_id=account,
                    payload={
                        "conversation_id": conversation,
                        "payload": {"message_id": uid(5), "text": "synthetic private body"},
                    },
                    digest=event_id,
                    context_version=3,
                    received_at=now,
                )
            )
            db.flush()
            db.add(
                Job(
                    id=job_id,
                    event_id=event_id,
                    account_id=account,
                    state="completed",
                    attempts=1,
                    available_at=now,
                    error_code=reason,
                )
            )
    response = client.get("/api/v1/review-items?limit=1")
    assert response.status_code == 200
    rows = response.json()["items"]
    assert len(rows) == 1
    assert rows[0]["id"] == ids[0]
    assert rows[0]["context_version"] == 3 and rows[0]["current_context_version"] == 4
    assert "private body" not in response.text and "payload" not in response.text
    with factory.begin() as db:
        assert db.get(Job, ids[0]).state == "completed"
        db.get(ConversationRow, uid(2)).allowlisted = False
    assert client.get("/api/v1/review-items").json()["items"] == []


def test_export_preserves_dst_instants_and_omits_unconfirmed_address():
    from gigmate.calendar_export import export_event

    schedule = {
        "kind": "timed",
        "start_at": "2026-11-01T05:30:00Z",
        "end_at": "2026-11-01T06:30:00Z",
        "timezone": "America/New_York",
    }
    event = {
        "id": str(uuid4()),
        "work_order_version": 4,
        "tentative": False,
        "schedule": schedule,
        "sources": [],
    }
    order = {
        "version": 4,
        "status": "confirmed",
        "summary": "Synthetic DST appointment",
        "updated_at": "2026-10-16T00:00:00Z",
        "fields": {
            "schedule": {"status": "confirmed", "value": schedule, "sources": []},
            "address": {"status": "proposed", "value": "Unverified location"},
        },
    }
    result = export_event(event, order).decode()
    assert "DTSTART:20261101T053000Z\r\nDTEND:20261101T063000Z" in result
    assert "America/New_York" in result
    assert "LOCATION" not in result and "Unverified" not in result
