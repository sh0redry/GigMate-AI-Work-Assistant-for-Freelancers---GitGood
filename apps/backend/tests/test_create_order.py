"""Role C P0: merchant creates a work order from a conversation; nothing is guessed."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from gigmate.db import (
    ActionRow,
    AuditRow,
    CalendarRow,
    ChangeRow,
    ConversationOrder,
    ConversationRow,
    TaskRow,
    WorkOrderRow,
)
from gigmate.messaging import fixture
from gigmate.seed import uid
from gigmate.worker import run_once

CONVERSATION = uid(2)
EXISTING = uid(3)


def future(days=3, hour=7):
    start = (datetime.now(UTC) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return {
        "kind": "timed",
        "start_at": start.isoformat().replace("+00:00", "Z"),
        "end_at": (start + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "timezone": "Asia/Hong_Kong",
    }


SAID = [{"message_id": uid(5), "message_revision": 1}]


def create(client, headers, key=None, **fields):
    body = {
        "conversation_id": CONVERSATION,
        "summary": "陈小姐证件照拍摄",
        "confirm_additional_order": True,
        **fields,
    }
    # By default, point each value at the seeded customer message that said it.
    if "schedule" in fields and "schedule_sources" not in fields:
        body["schedule_sources"] = SAID
    if "address" in fields and "address_sources" not in fields:
        body["address_sources"] = SAID
    return client.post(
        "/api/v1/work-orders",
        json=body,
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def rows(factory, model, order_id):
    with factory() as db:
        return list(db.scalars(select(model).where(model.work_order_id == order_id)))


def test_timed_order_is_confirmed_with_calendar_and_task(signed_in):
    client, factory, _, headers = signed_in
    schedule = future()
    response = create(client, headers, schedule=schedule, address="中环某大厦 12 楼")
    assert response.status_code == 201, response.text
    order = response.json()["data"]
    assert order["status"] == "confirmed"
    assert order["version"] == 1
    assert order["fields"]["schedule"]["status"] == "confirmed"
    assert order["fields"]["address"]["value"] == "中环某大厦 12 楼"
    calendar = rows(factory, CalendarRow, order["id"])
    assert len(calendar) == 1 and calendar[0].data["tentative"] is False
    tasks = rows(factory, TaskRow, order["id"])
    assert len(tasks) == 1
    assert tasks[0].data["title"].endswith("的陈小姐证件照拍摄")
    assert " 准备 " in tasks[0].data["title"]
    listed = client.get("/api/v1/work-orders").json()["items"]
    assert order["id"] in {item["id"] for item in listed}


def test_missing_values_stay_missing(signed_in):
    client, factory, _, headers = signed_in
    response = create(client, headers)
    assert response.status_code == 201, response.text
    order = response.json()["data"]
    assert order["status"] == "pending_confirmation"
    assert order["fields"]["schedule"] == {
        "value": None,
        "status": "missing",
        "sources": [],
        "interpretation": None,
    }
    assert order["fields"]["address"]["status"] == "missing"
    assert rows(factory, CalendarRow, order["id"]) == []
    assert rows(factory, TaskRow, order["id"]) == []


def test_date_only_is_tentative_and_never_blocks(signed_in):
    client, factory, _, headers = signed_in
    day = (datetime.now(UTC) + timedelta(days=5)).date().isoformat()
    response = create(
        client, headers, schedule={"kind": "date_only", "date": day, "timezone": "Asia/Hong_Kong"}
    )
    assert response.status_code == 201, response.text
    order = response.json()["data"]
    assert order["status"] == "pending_confirmation"
    assert order["fields"]["schedule"]["status"] == "proposed"
    calendar = rows(factory, CalendarRow, order["id"])
    assert len(calendar) == 1 and calendar[0].data["tentative"] is True
    assert rows(factory, TaskRow, order["id"]) == []


def test_open_order_requires_explicit_new_job(signed_in):
    client, _, _, headers = signed_in
    response = create(client, headers, confirm_additional_order=False)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "OPEN_ORDER_EXISTS"
    assert error["details"]["work_order_ids"] == [EXISTING]
    assert create(client, headers, confirm_additional_order=True).status_code == 201


def test_conflict_and_past_time_are_rejected(signed_in):
    client, factory, _, headers = signed_in
    first = create(client, headers, schedule=future(days=4))
    assert first.status_code == 201
    clash = create(client, headers, schedule=future(days=4))
    assert clash.status_code == 409
    assert clash.json()["error"]["details"]["work_order_ids"] == [first.json()["data"]["id"]]
    past = create(client, headers, schedule=future(days=-1))
    assert past.status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WorkOrderRow)) == 4


def test_cancelled_order_frees_its_time(signed_in):
    client, factory, _, headers = signed_in
    schedule = future(days=6)
    first = create(client, headers, schedule=schedule).json()["data"]
    with factory.begin() as db:
        row = db.get(WorkOrderRow, first["id"])
        row.data = {**row.data, "status": "cancelled"}
    assert create(client, headers, schedule=schedule).status_code == 201


def test_same_key_returns_same_order(signed_in):
    client, factory, _, headers = signed_in
    key = str(uuid4())
    first = create(client, headers, key=key)
    second = create(client, headers, key=key)
    assert first.status_code == second.status_code == 201
    assert first.json()["data"] == second.json()["data"]
    changed = create(client, headers, key=key, summary="另一单")
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    with factory() as db:
        operations = [row.data["operation"] for row in db.scalars(select(AuditRow))]
    assert operations.count("create_work_order") == 1


def test_paused_or_foreign_conversation_is_refused(signed_in):
    client, factory, _, headers = signed_in
    assert create(client, headers, conversation_id=uid(22)).status_code == 404
    with factory.begin() as db:
        db.get(ConversationRow, CONVERSATION).allowlisted = False
    response = create(client, headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CONSENT_REVOKED"


def test_summary_must_describe_the_job(signed_in):
    client, _, _, headers = signed_in
    assert create(client, headers, summary="").status_code == 422
    assert create(client, headers, summary="   ").status_code == 422
    assert create(client, headers, summary="x" * 121).status_code == 422


def relink_replay_conversation(factory):
    """Point the replay conversation at the newest order only (the seed order is closed)."""
    with factory.begin() as db:
        db.execute(
            ConversationOrder.__table__.delete().where(ConversationOrder.work_order_id == EXISTING)
        )
        db.get(WorkOrderRow, EXISTING).data = {
            **db.get(WorkOrderRow, EXISTING).data,
            "status": "cancelled",
        }


def propose_address(factory, order_id, text, customer="confirmed"):
    """A customer proposal for the address, as role B's extraction would store it."""
    return propose(factory, order_id, "address", text, customer)


def propose(factory, order_id, field, value, customer="confirmed"):
    """A customer proposal for one key field, as role B's extraction would store it."""
    change_id = str(uuid4())
    with factory.begin() as db:
        order = db.get(WorkOrderRow, order_id)
        conversation = db.get(ConversationRow, CONVERSATION)
        db.add(
            ChangeRow(
                id=change_id,
                account_id=order.account_id,
                work_order_id=order_id,
                conversation_id=CONVERSATION,
                context_version=conversation.context_version,
                data={
                    "id": change_id,
                    "account_id": order.account_id,
                    "work_order_id": order_id,
                    "field": field,
                    "old_value": None,
                    "new_value": value,
                    "status": "proposed",
                    "customer_confirmation": customer,
                    "proposer": "customer",
                    "sources": SAID,
                    "base_work_order_version": order.data["version"],
                },
            )
        )
        return change_id, conversation.context_version, order.data["version"]


def confirm(client, headers, order_id, change_id, version, context, calendar=True):
    return client.post(
        f"/api/v1/work-orders/{order_id}/changes/{change_id}/confirm",
        json={
            "expected_version": version,
            "expected_context_version": context,
            "apply_calendar_update": calendar,
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )


def test_time_without_address_stays_pending_but_blocks_the_slot(signed_in):
    client, factory, _, headers = signed_in
    schedule = future(days=7)
    order = create(client, headers, schedule=schedule).json()["data"]
    assert order["status"] == "pending_confirmation"
    calendar = rows(factory, CalendarRow, order["id"])
    assert len(calendar) == 1 and calendar[0].data["tentative"] is False
    # No preparation task until both time and address are confirmed.
    assert rows(factory, TaskRow, order["id"]) == []
    assert create(client, headers, schedule=schedule).status_code == 409


def test_order_confirms_only_when_time_and_address_are_both_confirmed(signed_in):
    client, factory, _, headers = signed_in
    created = create(client, headers).json()["data"]
    relink_replay_conversation(factory)
    replay = client.post(
        "/api/v1/replay",
        json={"scenario": "available"},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert replay.status_code == 202
    assert run_once(factory)
    path = f"/api/v1/work-orders/{created['id']}"
    change = next(row for row in client.get(path + "/changes").json()["items"])
    timed = confirm(client, headers, created["id"], change["id"], 1, change["context_version"])
    assert timed.status_code == 200, timed.text
    order = timed.json()["data"]
    # Time confirmed, address still missing: still pending, slot blocked, no task yet.
    assert order["status"] == "pending_confirmation"
    assert len(rows(factory, CalendarRow, created["id"])) == 1
    assert rows(factory, TaskRow, created["id"]) == []
    change_id, context, version = propose_address(factory, created["id"], " 中环某大厦 12 楼 ")
    done = confirm(client, headers, created["id"], change_id, version, context, calendar=False)
    assert done.status_code == 200, done.text
    order = done.json()["data"]
    assert order["status"] == "confirmed"
    assert order["fields"]["address"]["value"] == "中环某大厦 12 楼"
    [task] = rows(factory, TaskRow, created["id"])
    assert task.data["title"].endswith("的陈小姐证件照拍摄")


def test_address_alone_does_not_confirm(signed_in):
    client, factory, _, headers = signed_in
    created = create(client, headers).json()["data"]
    change_id, context, version = propose_address(factory, created["id"], "旺角")
    first = confirm(client, headers, created["id"], change_id, version, context, calendar=False)
    assert first.json()["data"]["status"] == "pending_confirmation"
    assert rows(factory, TaskRow, created["id"]) == []


def test_empty_address_proposal_is_refused(signed_in):
    client, factory, _, headers = signed_in
    created = create(client, headers).json()["data"]
    change_id, context, version = propose_address(factory, created["id"], "   ")
    response = confirm(client, headers, created["id"], change_id, version, context)
    assert response.status_code == 422


def test_existing_confirmed_order_keeps_working(signed_in):
    """Seed orders confirmed before this rule (address missing) are not demoted."""
    client, factory, _, headers = signed_in
    with factory() as db:
        assert db.get(WorkOrderRow, EXISTING).data["status"] == "confirmed"


def test_each_value_must_point_at_the_message_that_said_it(signed_in):
    client, factory, _, headers = signed_in
    missing = create(client, headers, schedule=future(), schedule_sources=[])
    assert missing.status_code == 422
    orphan = create(client, headers, address_sources=SAID)
    assert orphan.status_code == 422
    foreign = create(
        client,
        headers,
        address="中环",
        address_sources=[{"message_id": str(uuid4()), "message_revision": 1}],
    )
    assert foreign.status_code == 404
    stale = create(
        client,
        headers,
        address="中环",
        address_sources=[{"message_id": uid(5), "message_revision": 2}],
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "APPROVAL_STALE"
    ok = create(client, headers, address="中环", address_sources=SAID)
    assert ok.json()["data"]["fields"]["address"]["sources"] == SAID


# --- contracts/api-v1.md section 3: open items, customer confirmation, follow-up drafts


def drafts(client, order_id, state="pending_approval"):
    items = client.get("/api/v1/actions", params={"state": state}).json()["items"]
    return [item for item in items if item["work_order_id"] == order_id]


def test_pending_order_gets_one_draft_asking_only_open_items(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=8)).json()["data"]
    [draft] = drafts(client, order["id"])
    assert draft["trigger"] == "open_items"
    assert draft["open_items"] == ["missing_address"]
    assert draft["body"] == "你好，想跟你确认一下：见面地址是？"
    assert draft["bound_work_order_version"] == order["version"]
    assert draft["sources"] == SAID


def test_fully_confirmed_order_gets_no_draft(signed_in):
    client, _, _, headers = signed_in
    order = create(client, headers, schedule=future(days=8), address="旺角").json()["data"]
    assert drafts(client, order["id"]) == []


def test_empty_order_asks_for_time_and_address(signed_in):
    client, _, _, headers = signed_in
    order = create(client, headers).json()["data"]
    [draft] = drafts(client, order["id"])
    assert draft["open_items"] == ["missing_schedule", "missing_address"]
    assert draft["body"] == "你好，想跟你确认一下：哪天几点方便？见面地址是？"
    # No value was given, so the draft points at the conversation's newest message.
    assert len(draft["sources"]) == 1


def test_date_only_is_echoed_for_checking(signed_in):
    client, _, _, headers = signed_in
    day = (datetime.now(UTC) + timedelta(days=5)).date()
    order = create(
        client,
        headers,
        schedule={"kind": "date_only", "date": day.isoformat(), "timezone": "Asia/Hong_Kong"},
    ).json()["data"]
    [draft] = drafts(client, order["id"])
    assert draft["open_items"] == ["verify_schedule", "missing_time", "missing_address"]
    assert draft["body"] == f"你好，想跟你确认一下：你说的是 {day:%m/%d} 吗？几点方便？见面地址是？"


def test_value_the_customer_has_not_confirmed_stays_open(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=9)).json()["data"]
    change_id, context, version = propose_address(factory, order["id"], "旺角", customer="pending")
    accepted = confirm(client, headers, order["id"], change_id, version, context, calendar=False)
    assert accepted.status_code == 200, accepted.text
    data = accepted.json()["data"]
    assert data["status"] == "pending_confirmation"
    assert data["fields"]["address"] == {
        "value": "旺角",
        "status": "proposed",
        "sources": SAID,
        "interpretation": "Merchant accepted this address; waiting for the customer to confirm it",
    }
    assert rows(factory, TaskRow, order["id"]) == []
    [draft] = drafts(client, order["id"])
    assert draft["open_items"] == ["verify_address"]
    assert draft["body"] == "你好，想跟你确认一下：地址是「旺角」对吗？"
    # The customer replies 对 → an ordinary proposal, now customer-confirmed.
    change_id, context, version = propose_address(factory, order["id"], "旺角")
    done = confirm(client, headers, order["id"], change_id, version, context, calendar=False)
    assert done.json()["data"]["status"] == "confirmed"
    assert drafts(client, order["id"]) == []
    with factory() as db:
        old = db.get(ActionRow, draft["id"])
        assert (old.data["state"], old.reason) == ("cancelled", "resolved")
    assert len(rows(factory, TaskRow, order["id"])) == 1


def test_confirmed_order_reopens_when_a_key_item_awaits_the_customer(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(days=9), address="中环").json()["data"]
    assert len(rows(factory, TaskRow, order["id"])) == 1
    change_id, context, version = propose_address(factory, order["id"], "旺角", customer="pending")
    reopened = confirm(client, headers, order["id"], change_id, version, context, calendar=False)
    assert reopened.json()["data"]["status"] == "pending_confirmation"
    [task] = rows(factory, TaskRow, order["id"])
    assert task.data["state"] == "cancelled"
    assert [d["open_items"] for d in drafts(client, order["id"])] == [["verify_address"]]


def test_date_only_time_can_be_accepted_and_stays_tentative(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, address="旺角").json()["data"]
    day = (datetime.now(UTC) + timedelta(days=6)).date()
    value = {"kind": "date_only", "date": day.isoformat(), "timezone": "Asia/Hong_Kong"}
    change_id, context, version = propose(factory, order["id"], "schedule", value)
    response = confirm(client, headers, order["id"], change_id, version, context)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "pending_confirmation"
    [calendar] = rows(factory, CalendarRow, order["id"])
    assert calendar.data["tentative"] is True
    [draft] = drafts(client, order["id"])
    assert draft["open_items"] == ["missing_time"]
    assert draft["body"] == f"你好，想跟你确认一下：{day:%m/%d} 几点方便？"


def thanks():
    event = fixture("message-reschedule")
    event.update(
        event_id=str(uuid4()),
        provider_message_id=f"synthetic:{uuid4()}",
        occurred_at="2026-10-01T02:05:00Z",
        received_at="2026-10-01T02:05:01Z",
    )
    event["payload"] = {"message_id": str(uuid4()), "text": "谢谢"}
    return event


def test_reissue_asks_only_what_is_still_open(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers).json()["data"]
    [draft] = drafts(client, order["id"])
    response = client.post(
        "/api/v1/replay/events",
        json=thanks(),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    run_once(factory)
    assert drafts(client, order["id"]) == []
    old = client.get(f"/api/v1/actions/{draft['id']}").json()["data"]
    assert (old["closed_reason"], old["reissuable"]) == ("superseded", True)
    context = client.get(f"/api/v1/conversations/{CONVERSATION}").json()["data"]
    again = client.post(
        f"/api/v1/actions/{draft['id']}/reissue",
        json={"expected_context_version": context["context_version"]},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert again.status_code == 201, again.text
    assert again.json()["data"]["open_items"] == ["missing_schedule", "missing_address"]
    assert again.json()["data"]["bound_context_version"] == context["context_version"]
    # Meanwhile the merchant confirmed the address the customer gave earlier.
    change_id, context, version = propose_address(factory, order["id"], "旺角")
    confirm(client, headers, order["id"], change_id, version, context, calendar=False)
    [asked] = drafts(client, order["id"])
    assert asked["open_items"] == ["missing_schedule"]
    assert asked["body"] == "你好，想跟你确认一下：哪天几点方便？"


def expire_draft(factory, draft):
    from gigmate.approvals import snapshot_hash

    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    with factory.begin() as db:
        row = db.get(ActionRow, draft["id"])
        data = {**row.data, "expires_at": past}
        data["snapshot_hash"] = snapshot_hash(data)
        row.data = data


def test_open_item_question_can_be_reissued_in_repeated_rounds(signed_in):
    client, factory, _, headers = signed_in
    day = (datetime.now(UTC) + timedelta(days=5)).date().isoformat()
    order = create(
        client,
        headers,
        schedule={"kind": "date_only", "date": day, "timezone": "Asia/Hong_Kong"},
    ).json()["data"]
    [draft] = drafts(client, order["id"])
    context = draft["bound_context_version"]
    for _ in range(2):
        expire_draft(factory, draft)
        response = client.post(
            f"/api/v1/actions/{draft['id']}/reissue",
            json={"expected_context_version": context},
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 201, response.text
        draft = response.json()["data"]
        assert draft["open_items"] == ["verify_schedule", "missing_time", "missing_address"]
    with factory() as db:
        # Longest trigger shape still fits the 128-character column.
        assert max(len(row.trigger) for row in db.scalars(select(ActionRow))) <= 128
