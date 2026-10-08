"""Synthetic local-bridge tests. PostgreSQL uses disposable schemas, never live rows."""

import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

spec = importlib.util.spec_from_file_location(
    "local_operations", Path(__file__).with_name("local-operations.py")
)
operations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operations)

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from gigmate.db import (  # noqa: E402
    Account,
    Base,
    LoginSession,
    WahaConnection,
    WahaRecoveryIssue,
    make_engine,
)
from gigmate.errors import BusinessError  # noqa: E402
from gigmate.identity import digest  # noqa: E402
from gigmate.waha_ingress import WebhookBinding  # noqa: E402


class Provider:
    def __init__(self, state="FAILED", fail=False):
        self.state, self.fail, self.calls = state, fail, 0

    def status(self):
        return {"state": self.state}

    def restart_failed_session(self):
        self.calls += 1
        if self.fail:
            raise TimeoutError("synthetic uncertain outcome")
        self.state = "SCAN_QR_CODE"

    def close(self):
        pass


@pytest.fixture
def private_root(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, "ROOT", tmp_path)
    return tmp_path


def test_restart_duplicate_and_active_session_guard(private_root):
    provider, connection, key = Provider(), str(uuid4()), str(uuid4())
    assert operations.restart(provider, connection, key)["duplicate"] is False
    assert operations.restart(provider, connection, key)["duplicate"] is True
    with pytest.raises(BusinessError, match="Refresh"):
        operations.restart(provider, connection, str(uuid4()))
    assert provider.calls == 1


def test_uncertain_restart_survives_process_state_and_never_blindly_retries(
    private_root,
):
    provider, connection, key = Provider(fail=True), str(uuid4()), str(uuid4())
    for attempt in [key, key, str(uuid4())]:
        with pytest.raises(BusinessError) as error:
            operations.restart(provider, connection, attempt)
        assert error.value.code == "WAHA_RESULT_UNKNOWN"
    assert provider.calls == 1
    provider.state = "SCAN_QR_CODE"  # Reconcile from a later provider read.
    assert operations.restart(provider, connection, key)["duplicate"] is True
    assert provider.calls == 1


@pytest.mark.parametrize("state", ["WORKING", "SCAN_QR_CODE", "STARTING"])
def test_restart_never_interrupts_nonfailed_session(private_root, state):
    provider = Provider(state)
    with pytest.raises(BusinessError) as error:
        operations.restart(provider, str(uuid4()), str(uuid4()))
    assert error.value.code == "WAHA_RECOVERY_NOT_REQUIRED"
    assert provider.calls == 0


def test_restart_cooldown(private_root):
    provider, connection = Provider(), str(uuid4())
    operations.restart(provider, connection, str(uuid4()))
    provider.state = "FAILED"
    with pytest.raises(BusinessError) as error:
        operations.restart(provider, connection, str(uuid4()))
    assert error.value.code == "LOCAL_RESTART_COOLDOWN"
    assert provider.calls == 1


@pytest.fixture
def database(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    base = make_engine(url)
    postgres = url.startswith("postgresql")
    schema = "test_gigmate_" + uuid4().hex
    if postgres:
        with base.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = base.execution_options(schema_translate_map={None: schema})
    else:
        engine = base
    factory = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    account, other, connection = (str(uuid4()) for _ in range(3))
    now = datetime.now(UTC)
    binding = WebhookBinding(
        connection, account, "synthetic-instance", "default", "synthetic-secret"
    )
    payload = {"token": "synthetic-session", "csrf": "synthetic-csrf"}
    with factory.begin() as db:
        for identifier in [account, other]:
            db.add(
                Account(
                    id=identifier,
                    username=identifier,
                    password_hash="unused",
                    active=True,
                )
            )
        db.flush()
        db.add(
            LoginSession(
                token_hash=digest(payload["token"]),
                account_id=account,
                csrf_hash=digest(payload["csrf"]),
                expires_at=now + timedelta(hours=1),
            )
        )
        db.add(
            WahaConnection(
                id=connection,
                account_id=account,
                instance_id=binding.instance_id,
                session_id="default",
                enabled=True,
            )
        )
    try:
        yield factory, engine, binding, payload, other
    finally:
        if postgres:
            with base.begin() as db:
                db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def issue(factory, binding, recovered=True):
    identifier, now = str(uuid4()), datetime.now(UTC)
    with factory.begin() as db:
        db.add(
            WahaRecoveryIssue(
                id=identifier,
                connection_id=binding.connection_id,
                code="MONITOR_GAP" if recovered else "PROVIDER_UNAVAILABLE",
                started_at=now,
                last_seen_at=now,
                recovered_at=now if recovered else None,
                occurrences=1,
            )
        )
    return identifier


def execute(factory, binding, payload, operation="review-issues", consent=True):
    with factory.begin() as db:
        return operations.perform(
            db,
            SimpleNamespace(consent_active=consent),
            binding,
            binding.connection_id,
            operation,
            payload,
        )


def test_review_is_explicit_scoped_atomic_idempotent_and_keeps_audit(database):
    factory, _, binding, payload, _ = database
    recovered = issue(factory, binding)
    active = issue(factory, binding, False)
    for extra, code in [
        (
            {"issue_ids": [recovered], "confirmed": False},
            "REVIEW_CONFIRMATION_REQUIRED",
        ),
        (
            {"issue_ids": [recovered, active], "confirmed": True},
            "COMPONENT_STILL_UNAVAILABLE",
        ),
        ({"issue_ids": [recovered, str(uuid4())], "confirmed": True}, "NOT_FOUND"),
    ]:
        with pytest.raises(BusinessError) as error:
            execute(factory, binding, {**payload, **extra})
        assert error.value.code == code
        with factory() as db:
            assert db.get(WahaRecoveryIssue, recovered).acknowledged_at is None
    for _ in range(2):
        assert execute(
            factory, binding, {**payload, "issue_ids": [recovered], "confirmed": True}
        ) == {"reviewed": 1}
    with factory() as db:
        rows = list(db.scalars(select(WahaRecoveryIssue)))
        assert len(rows) == 2
        assert db.get(WahaRecoveryIssue, recovered).resolution == "reviewed_no_import"
        assert db.get(WahaRecoveryIssue, active).acknowledged_at is None


@pytest.mark.parametrize(
    "failure", ["session", "csrf", "expired", "owner", "paused", "consent", "mapping"]
)
def test_operator_revalidates_login_csrf_owner_and_permission(database, failure):
    factory, _, binding, payload, other = database
    value = {**payload, "issue_ids": [issue(factory, binding)], "confirmed": True}
    with factory.begin() as db:
        if failure == "session":
            value["token"] = "wrong"
        elif failure == "csrf":
            value["csrf"] = "wrong"
        elif failure == "expired":
            db.get(LoginSession, digest(payload["token"])).expires_at = datetime.now(
                UTC
            ) - timedelta(seconds=1)
        elif failure == "owner":
            db.get(LoginSession, digest(payload["token"])).account_id = other
        elif failure == "paused":
            db.get(WahaConnection, binding.connection_id).enabled = False
        elif failure == "mapping":
            db.get(
                WahaConnection, binding.connection_id
            ).instance_id = "synthetic-other-instance"
    with pytest.raises(BusinessError) as error:
        execute(factory, binding, value, consent=failure != "consent")
    assert error.value.status in {401, 403, 404}
    with factory() as db:
        assert db.get(WahaRecoveryIssue, value["issue_ids"][0]).acknowledged_at is None


def test_postgres_account_lock_serializes_duplicate_restart(
    database, private_root, monkeypatch
):
    factory, engine, binding, payload, _ = database
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    provider = Provider()
    monkeypatch.setattr("gigmate.waha_client.LocalWahaClient", lambda _config: provider)
    value = {**payload, "key": str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: execute(factory, binding, value, "restart"), range(2))
        )
    assert sorted(result["duplicate"] for result in results) == [False, True]
    assert provider.calls == 1
