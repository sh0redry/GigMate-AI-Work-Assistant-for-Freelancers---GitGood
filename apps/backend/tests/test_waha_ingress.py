"""Synthetic durable ingress, ownership, ordering, leases and failure tests."""

import asyncio
import copy
import hashlib
import hmac
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from gigmate.db import (
    Account,
    ChangeRow,
    ConversationRow,
    Inbox,
    Job,
    MessageRow,
    WahaChat,
    WahaConnection,
    WahaMessage,
)
from gigmate.errors import BusinessError
from gigmate.waha_adapter import AdapterError
from gigmate.waha_ingress import (
    WebhookBinding,
    purge_expired,
    receive,
    reconcile_state,
    status_view,
)
from gigmate.worker import run_once

ACCOUNT = "00000000-0000-4000-8000-000000000001"


@pytest.fixture
def ingress(signed_in, monkeypatch):
    client, factory, engine, headers = signed_in
    binding = WebhookBinding(
        str(uuid4()), ACCOUNT, "synthetic-instance", "default", "synthetic-" + "a" * 40
    )
    conversation_id = str(uuid4())
    with factory.begin() as db:
        db.add(
            WahaConnection(
                id=binding.connection_id,
                account_id=ACCOUNT,
                instance_id=binding.instance_id,
                session_id="default",
                enabled=True,
            )
        )
        db.add(
            ConversationRow(
                id=conversation_id, account_id=ACCOUNT, allowlisted=True, context_version=0
            )
        )
        db.flush()
        db.add(
            WahaChat(
                id=str(uuid4()),
                connection_id=binding.connection_id,
                provider_chat_id="synthetic:peer@lid",
                conversation_id=conversation_id,
            )
        )
    monkeypatch.setattr(
        "gigmate.api.binding_for",
        lambda identifier: binding if identifier == binding.connection_id else None,
    )
    return client, factory, engine, headers, binding, conversation_id


def raw(kind="message.any", *, event_id="synthetic:event-1", timestamp=None):
    timestamp = timestamp or int(datetime.now(UTC).timestamp() * 1000) - 10000
    payload = {
        "id": "synthetic:original",
        "fromMe": False,
        "from": "synthetic:peer@lid",
        "hasMedia": False,
        "body": "Synthetic test text",
        "ack": 1,
    }
    if kind == "message.edited":
        payload.update(
            id="synthetic:edit-action",
            editedMessageId="synthetic:original",
            body="Synthetic edited text",
        )
    elif kind == "message.revoked":
        payload = {"revokedMessageId": "synthetic:original", "before": None, "after": payload}
    elif kind == "session.status":
        payload = {"name": "default", "status": "WORKING", "private": "must-drop"}
    return {
        "id": event_id,
        "event": kind,
        "session": "default",
        "timestamp": timestamp,
        "payload": payload,
    }


def post(ingress, event, *, signed=True):
    client, _, _, _, binding, _ = ingress
    body = json.dumps(event, separators=(",", ":")).encode()
    signature = hmac.new(binding.secret.encode(), body, hashlib.sha512).hexdigest()
    return client.post(
        f"/api/v1/connectors/waha/{binding.connection_id}/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Hmac-Algorithm": "sha512",
            "X-Webhook-Hmac": signature if signed else "0" * 128,
        },
    )


def count(factory, model):
    with factory() as db:
        query = select(func.count()).select_from(model)
        if model is MessageRow:
            query = query.where(MessageRow.conversation_id.in_(select(WahaChat.conversation_id)))
        return db.scalar(query)


def test_create_duplicate_alias_edit_revoke_persist_without_extra_jobs(ingress):
    _, factory, _, _, binding, conversation_id = ingress
    creation = raw()
    assert post(ingress, creation).json()["data"]["durable_acceptance"] is True
    assert post(ingress, creation).json()["data"]["duplicate"] is True
    alias = {**creation, "id": "synthetic:alias"}
    assert post(ingress, alias).json()["data"]["duplicate"] is True
    edited = raw(
        "message.edited", event_id="synthetic:edit", timestamp=creation["timestamp"] + 1000
    )
    assert post(ingress, edited).status_code == 200
    revoked = raw(
        "message.revoked", event_id="synthetic:revoke", timestamp=creation["timestamp"] + 2000
    )
    assert post(ingress, revoked).status_code == 200
    # Retry old revisions after newer accepted ones: trusted lookup uses the stored receipt revision.
    assert post(ingress, edited).json()["data"]["duplicate"] is True
    assert post(ingress, creation).json()["data"]["duplicate"] is True
    assert count(factory, Inbox) == 4 and count(factory, Job) == 3
    assert count(factory, MessageRow) == 3 and count(factory, WahaMessage) == 1
    with factory() as db:
        assert db.get(ConversationRow, conversation_id).context_version == 3
        mapping = db.scalar(select(WahaMessage))
        assert mapping.revision == 3
        assert db.get(MessageRow, (mapping.message_id, 3)).data["text"] is None
        assert db.scalar(select(Inbox)).connection_id == binding.connection_id


@pytest.mark.parametrize(
    "mutation,status",
    [
        ("signature", 401),
        ("session", 403),
        ("peer", 403),
        ("media", 422),
        ("missing_id", 422),
        ("timestamp", 422),
        ("source", 422),
        ("huge_text", 422),
    ],
)
def test_rejection_writes_no_content_mapping_or_job(ingress, mutation, status):
    event = raw()
    if mutation == "session":
        event["session"] = "synthetic:other"
    if mutation == "peer":
        event["payload"]["from"] = "synthetic:unallowed@lid"
    if mutation == "media":
        event["payload"]["hasMedia"] = True
    if mutation == "missing_id":
        event.pop("id")
    if mutation == "timestamp":
        event["timestamp"] = True
    if mutation == "source":
        event["source"] = "api"
    if mutation == "huge_text":
        event["payload"]["body"] = "x" * 8001
    response = post(ingress, event, signed=mutation != "signature")
    assert response.status_code == status
    for model in (Inbox, Job, MessageRow, WahaMessage):
        assert count(ingress[1], model) == 0
    assert "Synthetic test text" not in response.text


@pytest.mark.parametrize("scope", ["account", "connection", "conversation", "ownership"])
def test_consent_and_cross_account_checks(ingress, scope):
    _, factory, _, _, binding, conversation_id = ingress
    with factory.begin() as db:
        if scope == "account":
            db.get(Account, ACCOUNT).active = False
        if scope == "connection":
            db.get(WahaConnection, binding.connection_id).enabled = False
        if scope == "conversation":
            db.get(ConversationRow, conversation_id).allowlisted = False
        if scope == "ownership":
            db.get(ConversationRow, conversation_id).account_id = db.scalar(
                select(Account).where(Account.username == "other")
            ).id
    assert post(ingress, raw()).status_code == 403
    assert count(factory, Inbox) == 0


def test_conflict_and_out_of_order_mutations_require_reconciliation(ingress):
    creation = raw()
    assert post(ingress, creation).status_code == 200
    changed = copy.deepcopy(creation)
    changed["payload"]["body"] = "conflict"
    assert post(ingress, changed).status_code == 409
    edit = raw("message.edited", event_id="synthetic:edit", timestamp=creation["timestamp"] + 1000)
    assert post(ingress, edit).status_code == 200
    stale = raw("message.edited", event_id="synthetic:late", timestamp=creation["timestamp"] + 500)
    assert post(ingress, stale).json()["error"]["code"] == "SOURCE_ORDER_NEEDS_RECONCILIATION"
    assert count(ingress[1], Job) == 2


def test_unknown_source_edit_and_ack_never_invent_messages(ingress):
    for kind in ("message.edited", "message.revoked", "message.ack"):
        assert post(ingress, raw(kind)).json()["error"]["code"] == "SOURCE_MESSAGE_UNRESOLVED"
    assert count(ingress[1], Inbox) == 0


def test_ack_is_independent_monotonic_and_does_not_advance_context(ingress):
    _, factory, _, _, _, conversation_id = ingress
    assert post(ingress, raw()).status_code == 200
    for rank in (3, 1):
        event = raw("message.ack", event_id=f"synthetic:ack-{rank}")
        event["payload"]["ack"] = rank
        assert post(ingress, event).status_code == 200
    assert count(factory, Job) == 1 and count(factory, MessageRow) == 1
    with factory() as db:
        assert db.scalar(select(WahaMessage)).delivery_rank == 3
        assert db.get(ConversationRow, conversation_id).context_version == 1


def test_session_order_freshness_and_account_scoped_api(ingress):
    client, factory, _, _, binding, _ = ingress
    event = raw("session.status")
    assert post(ingress, event).status_code == 200
    stale = raw("session.status", event_id="synthetic:stale", timestamp=event["timestamp"] - 1000)
    stale["payload"]["status"] = "FAILED"
    assert post(ingress, stale).status_code == 200
    data = client.get("/api/v1/connectors").json()["items"][0]
    assert data["state"] == "connected" and data["live_connected"] and data["stale_events"] == 1
    assert "secret" not in json.dumps(data) and "synthetic:peer" not in json.dumps(data)
    with factory.begin() as db:
        row = db.get(WahaConnection, binding.connection_id)
        row.state_received_at = datetime.now(UTC) - timedelta(minutes=3)
        assert status_view(db, row)["stale"] is True
    assert client.get("/api/v1/connectors").json()["items"][0]["live_connected"] is False
    client.post("/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"})
    assert client.get("/api/v1/connectors").json()["items"] == []
    assert count(factory, Job) == 0


def test_transaction_rollback_and_lost_response_redelivery(ingress):
    _, factory, _, _, binding, _ = ingress
    event = raw()
    with pytest.raises(RuntimeError):
        with factory.begin() as db:
            receive(db, binding, event)
            raise RuntimeError("synthetic lost transaction")
    assert count(factory, WahaMessage) == 0 and count(factory, Job) == 0
    with factory.begin() as db:
        receive(db, binding, event)
    with factory.begin() as db:
        assert receive(db, binding, event)["duplicate"] is True
    assert count(factory, Job) == 1


def test_database_commit_failure_never_returns_success(ingress, monkeypatch):
    _, factory, _, _, _, _ = ingress
    from sqlalchemy import event as sa_event

    def fail_commit(_db):
        raise OperationalError("synthetic statement", {}, Exception("private error"))

    sa_event.listen(factory.class_, "before_commit", fail_commit)
    try:
        response = post(ingress, raw())
        assert response.status_code == 503
        assert "private error" not in response.text
    finally:
        sa_event.remove(factory.class_, "before_commit", fail_commit)
    assert count(factory, Inbox) == 0 and count(factory, WahaMessage) == 0


def test_real_content_worker_never_calls_fictional_extractor(ingress, monkeypatch):
    def forbidden(*_args):
        raise AssertionError("extract must not run")

    monkeypatch.setattr("gigmate.worker.extract", forbidden)
    assert post(ingress, raw()).status_code == 200
    assert run_once(ingress[1])
    assert count(ingress[1], ChangeRow) == 0
    with ingress[1]() as db:
        assert db.scalar(select(Job)).error_code == "EXTRACTION_NEEDS_REVIEW"


def test_worker_checks_connector_revocation_and_reclaims_expired_lease(ingress):
    _, factory, _, _, binding, _ = ingress
    assert post(ingress, raw()).status_code == 200
    with factory.begin() as db:
        job = db.scalar(select(Job))
        job.state, job.lease_owner, job.lease_until = (
            "processing",
            "synthetic:crashed",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        db.get(WahaConnection, binding.connection_id).enabled = False
    assert run_once(factory)
    with factory() as db:
        job = db.scalar(select(Job))
        assert (
            job.state == "cancelled"
            and job.error_code == "CONSENT_REVOKED"
            and job.lease_owner is None
        )


def test_postgres_duplicate_reception_is_serialized(ingress):
    _, factory, engine, _, binding, _ = ingress
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    event = raw()

    def accept(_index):
        with factory.begin() as db:
            return receive(db, binding, event)["duplicate"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, range(2)))
    assert sorted(results) == [False, True]
    assert count(factory, Job) == 1


def test_webhook_database_wait_keeps_same_event_loop_responsive(ingress, monkeypatch):
    import httpx

    from gigmate.api import app

    _, _, _, _, binding, _ = ingress
    started = threading.Event()
    released = threading.Event()
    original = receive

    def delayed_receive(*args):
        started.set()
        assert released.wait(2)
        return original(*args)

    monkeypatch.setattr("gigmate.api.receive", delayed_receive)
    body = json.dumps(raw(), separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Hmac-Algorithm": "sha512",
        "X-Webhook-Hmac": hmac.new(binding.secret.encode(), body, hashlib.sha512).hexdigest(),
    }

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            pending = asyncio.create_task(
                client.post(
                    f"/api/v1/connectors/waha/{binding.connection_id}/events",
                    content=body,
                    headers=headers,
                )
            )
            # A timer also releases a broken synchronous handler so regression fails cleanly.
            timer = threading.Timer(1, released.set)
            timer.start()
            try:
                began = time.monotonic()
                assert await asyncio.to_thread(started.wait, 2)
                health = await asyncio.wait_for(client.get("/health"), timeout=0.5)
                assert health.status_code == 200
                assert time.monotonic() - began < 0.8
            finally:
                released.set()
                timer.cancel()
                response = await pending
            assert response.status_code == 200

    asyncio.run(exercise())


def test_poll_reconciliation_is_owned_and_persistent(ingress):
    _, factory, _, _, binding, _ = ingress
    with factory.begin() as db:
        assert reconcile_state(db, binding, "WORKING")["live_connected"] is True
    with factory() as db:
        assert db.get(WahaConnection, binding.connection_id).state == "connected"
    with factory.begin() as db:
        db.get(Account, ACCOUNT).active = False
    with factory.begin() as db:
        with pytest.raises(BusinessError):
            reconcile_state(db, binding, "WORKING")


def test_poll_does_not_overwrite_notification_received_during_lookup(ingress):
    _, factory, _, _, binding, _ = ingress
    sampled = datetime.now(UTC) - timedelta(seconds=3)
    event = raw(
        "session.status", timestamp=int((sampled + timedelta(seconds=1)).timestamp() * 1000)
    )
    assert post(ingress, event).status_code == 200
    with factory.begin() as db:
        assert reconcile_state(db, binding, "FAILED", now=sampled)["state"] == "connected"


def test_retention_removes_expired_content_without_reintroducing_it(ingress):
    _, factory, _, _, binding, _ = ingress
    event = raw()
    assert post(ingress, event).status_code == 200
    future = datetime.now(UTC) + timedelta(days=31)
    with factory.begin() as db:
        result = purge_expired(db, binding.connection_id, now=future)
        assert result == {"deleted_receipts": 1, "deleted_jobs": 1, "scrubbed_revisions": 1}
    with factory() as db:
        mapping = db.scalar(select(WahaMessage))
        assert db.get(MessageRow, (mapping.message_id, 1)).data["text"] is None
    with factory.begin() as db:
        with pytest.raises(BusinessError, match="WAHA event") as error:
            receive(db, binding, event, now=future)
        assert error.value.code == "EVENT_RETENTION_EXPIRED"


def test_provisioning_merges_scoped_allowlist_and_revokes_removed_chats(ingress):
    from dataclasses import replace

    from scripts.waha_ingress import provision

    from gigmate.waha_client import LocalWahaConfig

    _, factory, _, _, binding, conversation_id = ingress
    config = LocalWahaConfig(
        "http://127.0.0.1:18700",
        ACCOUNT,
        "default",
        "synthetic-" + "b" * 40,
        binding.secret,
        frozenset({"synthetic:second@lid"}),
    )
    with factory.begin() as db:
        assert provision(db, config, binding.instance_id).connection_id == binding.connection_id
    with factory() as db:
        assert db.get(ConversationRow, conversation_id).allowlisted is False
        assert db.scalar(select(func.count()).select_from(WahaChat)) == 2
    with factory.begin() as db:
        provision(db, config, binding.instance_id)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WahaChat)) == 2
    with factory.begin() as db:
        other = db.scalar(select(Account).where(Account.username == "other"))
        with pytest.raises(AdapterError, match="SESSION_OWNERSHIP_CONFLICT"):
            provision(db, replace(config, account_id=other.id), binding.instance_id)


def test_expired_worker_owner_cannot_finish_a_job(ingress, monkeypatch):
    assert post(ingress, raw()).status_code == 200
    base = datetime.now(UTC)
    calls = []

    class Clock:
        @staticmethod
        def now(_tz):
            calls.append(True)
            return base + timedelta(seconds=60 if len(calls) > 1 else 0)

    with monkeypatch.context() as patch:
        patch.setattr("gigmate.worker.datetime", Clock)
        assert run_once(ingress[1])
    with ingress[1].begin() as db:
        job = db.scalar(select(Job))
        assert job.state == "processing"
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    assert run_once(ingress[1])
    with ingress[1]() as db:
        assert db.scalar(select(Job)).state == "completed"


def test_private_configuration_is_disabled_by_default_and_never_echoes_secrets(
    signed_in, monkeypatch, tmp_path
):
    from gigmate.waha_ingress import binding_for

    monkeypatch.delenv("WAHA_CONNECTOR_CONFIG", raising=False)
    client = signed_in[0]
    response = client.post(f"/api/v1/connectors/waha/{uuid4()}/events", json=raw())
    assert response.status_code == 503 and response.json()["error"]["code"] == "CONNECTOR_DISABLED"
    path = tmp_path / "private-binding.json"
    binding = WebhookBinding(
        str(uuid4()), ACCOUNT, "synthetic-instance", "default", "private-" + "b" * 40
    )
    from dataclasses import asdict

    path.write_text(json.dumps(asdict(binding)))
    monkeypatch.setenv("WAHA_CONNECTOR_CONFIG", str(path))
    assert binding_for(binding.connection_id) == binding
    assert binding.secret not in repr(binding)
    with pytest.raises(BusinessError) as wrong:
        binding_for(str(uuid4()))
    assert wrong.value.status == 404
    path.write_text("not-json-private-secret")
    with pytest.raises(BusinessError) as broken:
        binding_for(binding.connection_id)
    assert broken.value.code == "CONNECTOR_CONFIG_INVALID"
    assert "private-secret" not in str(broken.value)


def test_strict_json_and_duplicate_hmac_headers_are_rejected(ingress):
    client, _, _, _, binding, _ = ingress
    path = f"/api/v1/connectors/waha/{binding.connection_id}/events"
    body = b'{"session":"default","session":"other"}'
    signature = hmac.new(binding.secret.encode(), body, hashlib.sha512).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Hmac-Algorithm": "sha512",
        "X-Webhook-Hmac": signature,
    }
    assert client.post(path, content=body, headers=headers).status_code == 422
    duplicated = list(headers.items()) + [("X-Webhook-Hmac", signature)]
    assert client.post(path, content=body, headers=duplicated).status_code == 401
    assert count(ingress[1], Inbox) == 0


def test_edit_cannot_change_original_sender_direction(ingress):
    creation = raw()
    assert post(ingress, creation).status_code == 200
    edit = raw(
        "message.edited",
        event_id="synthetic:forged-direction",
        timestamp=creation["timestamp"] + 1000,
    )
    edit["payload"].update(fromMe=True, to="synthetic:peer@lid")
    response = post(ingress, edit)
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "SOURCE_MAPPING_MISMATCH"
    )
    assert count(ingress[1], Job) == 1 and count(ingress[1], MessageRow) == 1


def test_short_edit_revoke_targets_resolve_canonical_original_and_deduplicate(ingress):
    creation = raw()
    canonical = "false_synthetic:peer@lid_AABB1234"
    creation["payload"]["id"] = canonical
    assert post(ingress, creation).status_code == 200
    edit = raw(
        "message.edited", event_id="synthetic:short-edit", timestamp=creation["timestamp"] + 1000
    )
    edit["payload"]["editedMessageId"] = "AABB1234"
    assert post(ingress, edit).status_code == 200
    revoke = raw(
        "message.revoked", event_id="synthetic:short-revoke", timestamp=creation["timestamp"] + 2000
    )
    revoke["payload"]["revokedMessageId"] = "AABB1234"
    assert post(ingress, revoke).status_code == 200
    assert post(ingress, edit).json()["data"]["duplicate"] is True
    with ingress[1]() as db:
        mapping = db.scalar(select(WahaMessage))
        assert mapping.revision == 3 and mapping.provider_message_id == canonical
        assert mapping.stanza_id == "AABB1234"
        rows = list(db.scalars(select(MessageRow).where(MessageRow.id == mapping.message_id)))
        assert len(rows) == 3 and all(row.provider_message_id == canonical for row in rows)


def test_short_target_is_scoped_to_chat_and_sender_direction(ingress):
    creation = raw()
    creation["payload"]["id"] = "false_synthetic:peer@lid_AABB1234"
    assert post(ingress, creation).status_code == 200
    edit = raw(
        "message.edited",
        event_id="synthetic:wrong-direction",
        timestamp=creation["timestamp"] + 1000,
    )
    edit["payload"].update(editedMessageId="AABB1234", fromMe=True, to="synthetic:peer@lid")
    assert post(ingress, edit).status_code == 409
    assert count(ingress[1], MessageRow) == 1


def test_ambiguous_short_target_is_not_arbitrarily_assigned(ingress):
    creation = raw()
    for participant in ("111@lid", "222@lid"):
        event = copy.deepcopy(creation)
        event["id"] = "synthetic:create-" + participant
        event["payload"]["id"] = "false_synthetic:peer@lid_AABB1234_" + participant
        assert post(ingress, event).status_code == 200
    edit = raw(
        "message.edited", event_id="synthetic:ambiguous", timestamp=creation["timestamp"] + 1000
    )
    edit["payload"]["editedMessageId"] = "AABB1234"
    response = post(ingress, edit)
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "SOURCE_MESSAGE_AMBIGUOUS"
    )
    assert count(ingress[1], MessageRow) == 2
