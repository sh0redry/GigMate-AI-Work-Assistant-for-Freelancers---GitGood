"""Owned product setup, durable intent and explicit unknown-result reconciliation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_waha_ingress import ACCOUNT, ingress  # noqa: F401

from gigmate import waha_controls as controls
from gigmate.contracts import WahaControlCommand
from gigmate.db import Account, ConversationRow, WahaCandidate, WahaControl
from gigmate.waha_adapter import AdapterError
from gigmate.waha_client import LocalWahaConfig


class FakeProvider:
    calls = None
    unknown = False
    missing = False
    matches = True

    def __init__(self):
        self.calls = []

    def status(self):
        return {"state": "WORKING"}

    def inspect_business_session(self, identifier):
        self.calls.append("inspect")
        if self.missing:
            raise AdapterError("WAHA_RESOURCE_NOT_FOUND")
        return {"state": "WORKING", "business_webhook_matches": self.matches}

    def create_business_session(self, identifier):
        self.calls.append("create")
        if self.unknown:
            raise AdapterError("WAHA_RESULT_UNKNOWN")
        self.missing = False

    def restart_failed_session(self):
        self.calls.append("restart")

    def recent_chats(self, **kwargs):
        return [{"id": "synthetic:peer-new@lid", "name": "Synthetic contact"}]

    def qr(self):
        self.calls.append("qr")
        return b"\x89PNG\r\n\x1a\nsynthetic"

    def close(self):
        pass


@pytest.fixture
def setup(ingress, monkeypatch):  # noqa: F811
    client, factory, engine, headers, binding, conversation = ingress
    config = LocalWahaConfig(
        "http://127.0.0.1:18700", ACCOUNT, "default", "synthetic-key-" + "a" * 40, binding.secret
    )
    monkeypatch.setattr(controls, "settings", lambda row: config)
    monkeypatch.setattr(controls, "configured_binding", lambda: binding)
    provider = FakeProvider()
    monkeypatch.setattr(controls, "client_for", lambda row: provider)
    return client, factory, headers, binding, provider


def path(setup, suffix):
    return f"/api/v1/connectors/{setup[3].connection_id}/{suffix}"


def command(setup, action="inspect", version=0, key="request-1"):
    return setup[0].post(
        path(setup, "operations"),
        json={"action": action, "expected_version": version},
        headers={**setup[2], "Idempotency-Key": key},
    )


def work(setup):
    return controls.run_once(setup[1], make_client=lambda row: setup[4])


def test_queue_commit_duplicate_and_conflict(setup):
    response = command(setup)
    assert response.status_code == 202
    assert response.json()["data"]["state"] == "pending"
    assert not setup[4].calls
    assert command(setup).json()["data"]["id"] == response.json()["data"]["id"]
    assert command(setup, action="connect").status_code == 409
    assert command(setup, key="another").status_code == 409
    assert work(setup)
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaControl)) == 1
        assert db.scalar(select(WahaControl)).state == "succeeded"


def test_csrf_and_cross_account_cannot_operate_or_qr(setup):
    client = setup[0]
    assert (
        client.post(
            path(setup, "operations"),
            json={"action": "inspect", "expected_version": 0},
            headers={"Idempotency-Key": "x"},
        ).status_code
        == 403
    )
    other = client.post(
        "/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"}
    ).json()["data"]["csrf_token"]
    for suffix in ("setup", "chats", "qr"):
        assert client.get(path(setup, suffix)).status_code == 404
    assert (
        client.post(
            path(setup, "operations"),
            json={"action": "inspect", "expected_version": 0},
            headers={"X-CSRF-Token": other, "Idempotency-Key": "x"},
        ).status_code
        == 404
    )
    assert not setup[4].calls


def test_unknown_mutation_not_retried_and_get_only_reconciliation(setup):
    provider = setup[4]
    provider.missing = provider.unknown = True
    operation = command(setup, "connect").json()["data"]["id"]
    assert work(setup)
    assert provider.calls == ["inspect", "create"]
    assert not work(setup)
    assert command(setup, "recover", version=1, key="retry").status_code == 409
    provider.missing, provider.unknown = False, False
    response = setup[0].post(
        path(setup, f"operations/{operation}/reconcile"),
        json={"expected_version": 1},
        headers=setup[2],
    )
    assert response.status_code == 200
    assert work(setup)
    assert provider.calls == ["inspect", "create", "inspect"]
    assert (
        setup[0].get(path(setup, f"operations/{operation}")).json()["data"]["state"] == "succeeded"
    )


def test_connect_existing_callback_is_not_overwritten(setup):
    setup[4].matches = False
    command(setup, "connect")
    work(setup)
    assert setup[4].calls == ["inspect"]
    with setup[1]() as db:
        assert db.scalar(select(WahaControl)).error_code == "WAHA_REMOTE_CONFIGURATION_UNCONFIRMED"


def test_pause_cancel_then_explicit_resume(setup):
    command(setup, "connect")
    assert (
        setup[0]
        .post(path(setup, "pause"), json={"expected_version": 1}, headers=setup[2])
        .status_code
        == 200
    )
    assert not work(setup)
    assert setup[0].get(path(setup, "setup")).json()["data"]["enabled"] is False
    assert command(setup, "connect", version=2, key="new").status_code == 403
    assert (
        setup[0]
        .post(path(setup, "resume"), json={"expected_version": 2}, headers=setup[2])
        .json()["data"]["enabled"]
    )
    assert not setup[4].calls


def test_expired_control_lease_becomes_unknown_without_remote_call(setup):
    operation = command(setup, "connect").json()["data"]["id"]
    with setup[1].begin() as db:
        row = db.get(WahaControl, operation)
        row.state, row.lease_until = "running", datetime.now(UTC) - timedelta(seconds=1)
    assert not work(setup)
    with setup[1]() as db:
        assert db.get(WahaControl, operation).state == "result_unknown"
    assert not setup[4].calls


def test_discover_choices_opaque_select_and_remove(setup):
    command(setup, "discover")
    work(setup)
    response = setup[0].get(path(setup, "chats"))
    assert response.status_code == 200 and "synthetic:peer-new" not in response.text
    option = next(item for item in response.json()["data"] if item["label"] == "Synthetic contact")
    update = setup[0].put(
        path(setup, "chats"),
        json={"expected_version": 1, "selected_ids": [option["id"]], "consent": True},
        headers=setup[2],
    )
    assert update.status_code == 200
    selected_choices = setup[0].get(path(setup, "chats")).json()["data"]
    assert any(
        item["selected"] and item["label"] == "Synthetic contact" and item["id"] != option["id"]
        for item in selected_choices
    )
    with setup[1]() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ConversationRow)
                .where(ConversationRow.allowlisted.is_(True), ConversationRow.account_id == ACCOUNT)
            )
            >= 1
        )
    assert (
        setup[0]
        .put(
            path(setup, "chats"),
            json={"expected_version": 2, "selected_ids": [], "consent": True},
            headers=setup[2],
        )
        .status_code
        == 200
    )
    assert (
        setup[0].get(path(setup, "chats")).json()["data"]
    )  # Candidates remain metadata, not authorization.


@pytest.mark.parametrize("expired", [False, True])
def test_untrusted_or_expired_choices_leave_authorization_unchanged(setup, expired):
    identifier = str(uuid4())
    if expired:
        with setup[1].begin() as db:
            db.add(
                WahaCandidate(
                    id=identifier,
                    connection_id=setup[3].connection_id,
                    provider_chat_id="synthetic:expired@lid",
                    label="expired",
                    expires_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )
    with setup[1]() as db:
        before = db.scalar(select(func.count()).select_from(ConversationRow))
    response = setup[0].put(
        path(setup, "chats"),
        json={"expected_version": 0, "selected_ids": [identifier], "consent": True},
        headers=setup[2],
    )
    assert response.status_code == 422
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(ConversationRow)) == before


def test_qr_private_no_cache_and_paused_rejected(setup):
    response = setup[0].get(path(setup, "qr"))
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert "no-store" in response.headers["cache-control"]
    original = setup[4].qr

    def no_qr():
        raise AdapterError("WAHA_NOT_WAITING_FOR_QR")

    setup[4].qr = no_qr
    assert setup[0].get(path(setup, "qr")).status_code == 409
    setup[4].qr = original
    setup[0].post(path(setup, "pause"), json={"expected_version": 0}, headers=setup[2])
    assert setup[0].get(path(setup, "qr")).status_code == 403


def test_qr_rechecks_pause_before_emitting_pairing_material(setup):
    original = setup[4].qr

    def pause_during_fetch():
        from gigmate.db import WahaConnection

        with setup[1].begin() as db:
            connection = db.get(WahaConnection, setup[3].connection_id)
            connection.enabled = False
            connection.control_version += 1
        return original()

    setup[4].qr = pause_during_fetch
    response = setup[0].get(path(setup, "qr"))
    assert response.status_code == 409 and not response.content.startswith(b"\x89PNG")


def test_stale_owner_cannot_finalize_new_lease(setup):
    operation = command(setup).json()["data"]["id"]
    original = setup[4].status

    def replace_lease():
        with setup[1].begin() as db:
            db.get(WahaControl, operation).lease_token = str(uuid4())
        return original()

    setup[4].status = replace_lease
    work(setup)
    with setup[1]() as db:
        assert db.get(WahaControl, operation).state == "running"


def test_expired_pending_intent_never_dispatched(setup):
    identifier = command(setup, "connect").json()["data"]["id"]
    with setup[1].begin() as db:
        db.get(WahaControl, identifier).created_at = datetime.now(UTC) - timedelta(minutes=3)
    assert work(setup) and not setup[4].calls
    with setup[1]() as db:
        assert db.get(WahaControl, identifier).error_code == "WAHA_CONTROL_REQUEST_EXPIRED"


def test_boolean_consent_not_integer_or_false(setup):
    for consent in (1, False, "true"):
        response = setup[0].put(
            path(setup, "chats"),
            json={"expected_version": 0, "selected_ids": [], "consent": consent},
            headers=setup[2],
        )
        assert response.status_code == 422


def test_postgres_concurrent_queue_single_intent(setup):
    with setup[1]() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("Requires PostgreSQL row locks")

    def submit(_):
        with setup[1].begin() as db:
            account = db.scalar(select(Account).where(Account.id == ACCOUNT).with_for_update())
            row = controls.owned(db, account, setup[3].connection_id, lock=True)
            return controls.enqueue(
                db, row, WahaControlCommand(action="inspect", expected_version=0), "same-key"
            )["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(pool.map(submit, range(4)))
    assert len(set(identifiers)) == 1
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaControl)) == 1
