"""Current-source export and actual list-before-confirm regression paths."""

import copy
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_create_order import confirm, create, future, propose

from gigmate.db import CalendarRow, ConversationOrder, ConversationRow, MessageRow, WorkOrderRow
from gigmate.messaging import fixture
from gigmate.seed import uid


def calendar(factory, order_id=uid(3)):
    with factory() as db:
        return db.scalar(select(CalendarRow.id).where(CalendarRow.work_order_id == order_id))


@pytest.mark.parametrize("field", ["schedule", "address"])
@pytest.mark.parametrize("event_type", ["message.edited", "message.revoked"])
def test_export_rechecks_actual_ingested_source_without_mutating_history(
    signed_in, field, event_type
):
    client, factory, _, headers = signed_in
    mid = uid(5)
    if field == "address":
        mid = str(uuid4())
        with factory.begin() as db:
            source = db.get(MessageRow, (uid(5), 1))
            data = {**source.data, "id": mid, "provider_message_id": "synthetic:export-address"}
            db.add(
                MessageRow(
                    id=mid,
                    revision=1,
                    account_id=uid(1),
                    conversation_id=uid(2),
                    provider_message_id=data["provider_message_id"],
                    data=data,
                )
            )
            order = db.get(WorkOrderRow, uid(3))
            saved = copy.deepcopy(order.data)
            saved["fields"]["address"] = {
                "status": "confirmed",
                "value": "Synthetic venue",
                "sources": [{"message_id": mid, "message_revision": 1}],
                "interpretation": None,
            }
            order.data = saved
    path = f"/api/v1/calendar-events/{calendar(factory)}.ics"
    assert client.get(path).status_code == 200
    with factory() as db:
        source = db.get(MessageRow, (mid, 1))
        provider_id = source.provider_message_id
    event = fixture("message-edited" if event_type.endswith("edited") else "message-revoked")
    event.update(
        event_id=str(uuid4()),
        event_type=event_type,
        message_revision=2,
        provider_message_id=provider_id,
    )
    event["payload"] = {"message_id": mid}
    if event_type.endswith("edited"):
        event["payload"]["text"] = "Synthetic changed source; review required."
    ingested = client.post(
        "/api/v1/replay/events", json=event, headers={**headers, "Idempotency-Key": str(uuid4())}
    )
    assert ingested.status_code == 202, ingested.text
    with factory() as db:
        before_order = copy.deepcopy(db.get(WorkOrderRow, uid(3)).data)
        before_event = copy.deepcopy(db.get(CalendarRow, calendar(factory)).data)
    refused = client.get(path)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "APPROVAL_STALE"
    with factory() as db:
        assert db.get(WorkOrderRow, uid(3)).data == before_order
        assert db.get(CalendarRow, calendar(factory)).data == before_event


@pytest.mark.parametrize("case", ["missing", "foreign", "unlinked", "paused", "outgoing", "empty"])
def test_export_requires_owned_linked_allowlisted_current_incoming_sources(signed_in, case):
    client, factory, _, _ = signed_in
    event_id = calendar(factory)
    with factory.begin() as db:
        order = db.get(WorkOrderRow, uid(3))
        saved = copy.deepcopy(order.data)
        refs = saved["fields"]["schedule"]["sources"]
        if case == "missing":
            refs[0]["message_id"] = str(uuid4())
        elif case == "foreign":
            refs[0]["message_id"] = uid(25)
        elif case == "unlinked":
            db.delete(db.get(ConversationOrder, (uid(2), uid(3))))
        elif case == "paused":
            db.get(ConversationRow, uid(2)).allowlisted = False
        elif case == "outgoing":
            row = db.get(MessageRow, (uid(5), 1))
            row.data = {**row.data, "direction": "outgoing"}
        else:
            refs.clear()
        order.data = saved
        row = db.get(CalendarRow, event_id)
        row.data = {**row.data, "sources": refs}
    response = client.get(f"/api/v1/calendar-events/{event_id}.ics")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "APPROVAL_STALE"


@pytest.mark.parametrize("kind", ["address", "date_only", "timed"])
def test_actual_change_list_loads_before_review_and_confirmation(signed_in, kind):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=61), address="Synthetic venue").json()[
        "data"
    ]
    value = "Synthetic new venue" if kind == "address" else future(days=62)
    if kind == "date_only":
        value = {"kind": "date_only", "date": value["start_at"][:10], "timezone": "Asia/Hong_Kong"}
    field = "address" if kind == "address" else "schedule"
    change_id, context, version = propose(factory, order["id"], field, value)
    path = f"/api/v1/work-orders/{order['id']}"
    # This is the same HTTP read sequence required by workspace-api.load().
    for route in (
        path,
        path + "/changes",
        "/api/v1/calendar-events",
        "/api/v1/tasks",
        "/api/v1/conversations/" + uid(2),
    ):
        response = client.get(route)
        assert response.status_code == 200, (route, response.text)
    changes = client.get(path + "/changes").json()["items"]
    reviewed = next(item for item in changes if item["id"] == change_id)
    assert reviewed["new_value"] == value and reviewed["conflict_ids"] == []
    response = confirm(
        client, headers, order["id"], change_id, version, context, calendar=field == "schedule"
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["fields"][field]["value"] == value
    assert client.get(path + "/changes").status_code == 200
