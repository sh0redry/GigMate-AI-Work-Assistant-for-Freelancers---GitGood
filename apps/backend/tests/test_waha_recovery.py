"""Safe metadata, outage windows, review isolation and bounded recovery."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from test_waha_ingress import ACCOUNT, ingress, post, raw  # noqa: F401

from gigmate.db import (
    Account,
    Inbox,
    Job,
    ServiceHeartbeat,
    WahaConnection,
    WahaOperation,
    WahaRecoveryIssue,
)
from gigmate.errors import BusinessError
from gigmate.waha_ingress import status_view
from gigmate.waha_recovery import (
    acknowledge_issue,
    observe_pipeline,
    record_database_gap,
    record_rejection,
    worker_heartbeat,
)
from gigmate.worker import heartbeat, run_once


@pytest.fixture
def recovery(ingress, monkeypatch):  # noqa: F811
    monkeypatch.setattr("gigmate.api.Session", ingress[1])
    return ingress


def view(recovery, now=None):
    _, factory, _, _, binding, _ = recovery
    with factory() as db:
        return status_view(db, db.get(WahaConnection, binding.connection_id), now=now)


def healthy(recovery, now):
    _, factory, _, _, binding, _ = recovery
    with factory.begin() as db:
        connection = db.get(WahaConnection, binding.connection_id)
        connection.state, connection.state_received_at = "connected", now
        worker_heartbeat(db, now=now)
        observe_pipeline(db, binding, api_ok=True, provider_ok=True, now=now)


def test_whatsapp_connected_does_not_imply_pipeline_ready(recovery):
    now = datetime.now(UTC)
    healthy(recovery, now)
    assert view(recovery, now)["pipeline_ready"]
    _, factory, _, _, binding, _ = recovery
    with factory.begin() as db:
        observe_pipeline(
            db, binding, api_ok=False, provider_ok=True, now=now + timedelta(seconds=1)
        )
    status = view(recovery, now + timedelta(seconds=1))
    assert status["live_connected"]
    assert not status["pipeline_ready"]
    assert status["api_health"]["state"] == "unavailable"
    assert status["review_required"]


@pytest.mark.parametrize(
    "component", ["api_health", "provider_health", "monitor_health", "worker_health"]
)
def test_component_samples_expire(recovery, component):
    now = datetime.now(UTC)
    healthy(recovery, now)
    status = view(recovery, now + timedelta(seconds=121))
    assert status[component]["state"] == "stale"
    assert not status["pipeline_ready"]


def test_missing_samples_are_unknown(recovery):
    status = view(recovery)
    assert status["api_health"]["state"] == "unknown"
    assert status["worker_health"]["state"] == "unknown"
    assert not status["pipeline_ready"]


def test_recovery_keeps_gap_visible_until_explicit_review(recovery):
    now = datetime.now(UTC)
    healthy(recovery, now)
    _, factory, _, _, binding, _ = recovery
    with factory.begin() as db:
        observe_pipeline(
            db, binding, api_ok=False, provider_ok=True, now=now + timedelta(seconds=1)
        )
        observe_pipeline(
            db, binding, api_ok=False, provider_ok=True, now=now + timedelta(seconds=2)
        )
        issue_id = db.scalar(select(WahaRecoveryIssue.id))
        with pytest.raises(BusinessError, match="Restore"):
            acknowledge_issue(db, binding, issue_id, "reviewed_no_import")
    with factory.begin() as db:
        worker_heartbeat(db, now=now + timedelta(seconds=3))
        observe_pipeline(db, binding, api_ok=True, provider_ok=True, now=now + timedelta(seconds=3))
    assert view(recovery, now + timedelta(seconds=3))["review_required"]
    with factory.begin() as db:
        result = acknowledge_issue(db, binding, issue_id, "reviewed_no_import")
        assert result["occurrences"] == 2
        assert result["recovered_at"] is not None
        assert acknowledge_issue(db, binding, issue_id, "reviewed_no_import") == result
    assert not view(recovery, now + timedelta(seconds=3))["review_required"]


def test_followup_outcome_keeps_review_flag_until_final_review(recovery):
    _, factory, _, _, binding, _ = recovery
    with factory.begin() as db:
        record_rejection(db, binding, "SOURCE_MESSAGE_UNRESOLVED")
        issue_id = db.scalar(select(WahaRecoveryIssue.id))
        acknowledge_issue(db, binding, issue_id, "needs_followup")
    assert view(recovery)["review_required"]
    with factory.begin() as db:
        assert acknowledge_issue(db, binding, issue_id, "reviewed_no_import")["acknowledged_at"]
        with pytest.raises(BusinessError) as exc:
            acknowledge_issue(db, binding, issue_id, "needs_followup")
        assert exc.value.code == "REVIEW_ALREADY_RECORDED"
    assert not view(recovery)["review_required"]


def test_monitor_gap_and_worker_crash_are_recovered_but_not_silently_closed(recovery):
    now = datetime.now(UTC)
    healthy(recovery, now)
    _, factory, _, _, binding, _ = recovery
    with factory.begin() as db:
        observe_pipeline(
            db, binding, api_ok=True, provider_ok=True, now=now + timedelta(seconds=121)
        )
    with factory() as db:
        issues = {r.code: r for r in db.scalars(select(WahaRecoveryIssue))}
        assert issues["MONITOR_GAP"].recovered_at is not None
        assert issues["WORKER_GAP"].recovered_at is None
    with factory.begin() as db:
        worker_heartbeat(db, now=now + timedelta(seconds=122))
        observe_pipeline(
            db, binding, api_ok=True, provider_ok=True, now=now + timedelta(seconds=122)
        )
    assert view(recovery, now + timedelta(seconds=122))["unresolved_issues"] == 2


def test_late_monitor_and_worker_samples_do_not_regress(recovery):
    now = datetime.now(UTC)
    healthy(recovery, now)
    _, factory, _, _, binding, _ = recovery
    with factory.begin() as db:
        worker_heartbeat(db, now=now - timedelta(seconds=10))
        observe_pipeline(
            db, binding, api_ok=False, provider_ok=False, now=now - timedelta(seconds=10)
        )
    assert view(recovery, now)["pipeline_ready"]
    assert not view(recovery, now)["review_required"]


def test_database_gap_recorded_after_recovery_without_content(recovery):
    _, factory, _, _, binding, _ = recovery
    started = datetime.now(UTC) - timedelta(seconds=12)
    with factory.begin() as db:
        record_database_gap(db, binding, started)
        record_rejection(db, binding, "SENSITIVE_PROVIDER_VALUE_should_never_persist")
    with factory() as db:
        issue = db.scalar(select(WahaRecoveryIssue))
        assert issue.code == "DATABASE_UNAVAILABLE"
        assert issue.recovered_at is not None
        assert issue.started_at.replace(tzinfo=UTC) == started
        assert (
            db.get(WahaOperation, binding.connection_id).last_error_code == "INVALID_PROVIDER_SHAPE"
        )
        assert db.scalar(select(func.count()).select_from(Inbox)) == 0


def test_signed_source_rejection_rolls_back_content_but_counts_safe_error(recovery):
    event = raw("message.edited")
    response = post(recovery, event)
    assert response.status_code == 409
    status = view(recovery)
    assert status["accepted"] == 0
    assert status["metrics"]["rejected"] == 1
    assert status["metrics"]["last_error_code"] == "SOURCE_MESSAGE_UNRESOLVED"
    assert status["unresolved_issues"] == 1
    _, factory, _, _, _, _ = recovery
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Inbox)) == 0


def test_unauthenticated_payload_does_not_create_diagnostics(recovery):
    assert post(recovery, raw(), signed=False).status_code == 401
    assert view(recovery)["metrics"]["rejected"] == 0
    assert not view(recovery)["review_required"]


def test_issues_endpoint_is_owned_and_contains_no_provider_identifiers(recovery):
    client, factory, _, _, binding, _ = recovery
    with factory.begin() as db:
        record_rejection(db, binding, "SOURCE_MESSAGE_UNRESOLVED")
    path = f"/api/v1/connectors/{binding.connection_id}/recovery-issues"
    response = client.get(path)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert "synthetic:peer" not in response.text
    assert binding.secret not in response.text
    client.post("/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"})
    assert client.get(path).status_code == 404
    client.cookies.clear()
    assert client.get(path).status_code == 401


def test_failed_original_retry_after_source_arrives_is_accepted_once(recovery):
    event = raw("message.edited")
    assert post(recovery, event).status_code == 409
    created = raw(event_id="synthetic:create-before-retry", timestamp=event["timestamp"] - 1000)
    assert post(recovery, created).status_code == 200
    assert post(recovery, event).status_code == 200
    assert post(recovery, event).json()["data"]["duplicate"]
    assert view(recovery)["metrics"]["rejected"] == 1
    assert view(recovery)[
        "review_required"
    ]  # Successful retry does not prove all missed notifications recovered.


def test_terminal_processing_has_measured_latency(recovery):
    assert post(recovery, raw()).status_code == 200
    assert run_once(recovery[1])
    status = view(recovery)
    assert status["metrics"]["timed_jobs"] == 1
    assert status["metrics"]["average_processing_ms"] >= 0
    assert status["metrics"]["average_completion_latency_ms"] >= 0
    assert status["metrics"]["oldest_pending_seconds"] is None


def test_crashed_worker_lease_recovered_once_and_bounded(recovery):
    post(recovery, raw())
    _, factory, _, _, _, _ = recovery
    with factory.begin() as db:
        job = db.scalar(select(Job))
        job.state, job.attempts = "processing", 1
        job.lease_owner, job.lease_until = (
            "synthetic:crashed",
            datetime.now(UTC) - timedelta(seconds=1),
        )
    assert run_once(factory)
    metrics = view(recovery)["metrics"]
    assert metrics["lease_recoveries"] == 1
    assert metrics["retries"] == 1
    assert not run_once(factory)


def test_repeated_worker_crashes_exhaust_retry_budget(recovery):
    post(recovery, raw())
    _, factory, _, _, _, _ = recovery
    with factory.begin() as db:
        job = db.scalar(select(Job))
        job.state, job.attempts = "processing", 3
        job.lease_owner, job.lease_until = (
            "synthetic:crashed",
            datetime.now(UTC) - timedelta(seconds=1),
        )
    assert run_once(factory)
    with factory() as db:
        job = db.scalar(select(Job))
        assert job.state == "failed" and job.error_code == "RETRY_EXHAUSTED"
        assert job.attempts == 3 and job.lease_owner is None
    assert not run_once(factory)


def test_database_lock_timeout_returns_failure_not_durable_success(recovery):
    _, factory, engine, _, _, _ = recovery
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL lock timeout")
    with factory.begin() as locked:
        locked.scalar(select(Account).where(Account.id == ACCOUNT).with_for_update())
        began = time.monotonic()
        response = post(recovery, raw())
        assert response.status_code == 503
        assert time.monotonic() - began < 9
    assert view(recovery)["accepted"] == 0


def test_postgres_parallel_http_receipts_share_one_event_loop(recovery):
    _, _, engine, _, binding, _ = recovery
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL reception row locks")
    import hashlib
    import hmac

    from gigmate.api import app

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
            responses = await asyncio.wait_for(
                asyncio.gather(
                    *[
                        client.post(
                            f"/api/v1/connectors/waha/{binding.connection_id}/events",
                            content=body,
                            headers=headers,
                        )
                        for _ in range(3)
                    ]
                ),
                timeout=10,
            )
        assert all(r.status_code == 200 for r in responses)
        assert sorted(r.json()["data"]["duplicate"] for r in responses) == [False, True, True]

    asyncio.run(exercise())
    assert view(recovery)["accepted"] == 1
    assert view(recovery)["duplicates"] == 2


def test_worker_heartbeat_survives_restart_and_exposes_staleness(recovery):
    _, factory, _, _, _, _ = recovery
    assert heartbeat(factory)
    assert view(recovery)["worker_health"]["state"] == "healthy"
    with factory.begin() as db:
        db.get(ServiceHeartbeat, "worker").observed_at = datetime.now(UTC) - timedelta(seconds=31)
    assert view(recovery)["worker_health"]["state"] == "stale"
    assert heartbeat(factory)
    assert view(recovery)["worker_health"]["state"] == "healthy"


def test_postgres_rejection_counter_and_issue_are_serialized(recovery):
    _, factory, engine, _, binding, _ = recovery
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL account locks")

    def reject(_index):
        with factory.begin() as db:
            record_rejection(db, binding, "SOURCE_MESSAGE_UNRESOLVED")

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(reject, range(3)))
    assert view(recovery)["metrics"]["rejected"] == 3
    with factory() as db:
        issues = list(db.scalars(select(WahaRecoveryIssue)))
        assert len(issues) == 1 and issues[0].occurrences == 3


@pytest.mark.parametrize(
    "api_ok,provider_state", [(False, "WORKING"), (True, None), (True, "FAILED"), (True, "WORKING")]
)
def test_operator_monitor_samples_api_and_provider_independently(
    recovery, monkeypatch, api_ok, provider_state
):
    from dataclasses import replace

    from scripts import waha_ingress as operator

    from gigmate.waha_adapter import AdapterError
    from gigmate.waha_client import LocalWahaConfig

    _, factory, _, _, binding, _ = recovery
    now = datetime.now(UTC)
    healthy(recovery, now - timedelta(seconds=1))
    config = LocalWahaConfig(
        "http://127.0.0.1:18700",
        binding.account_id,
        "default",
        "synthetic-" + "k" * 40,
        binding.secret,
    )

    class FakeHttp:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            assert url == "http://127.0.0.1:18702/health"
            return httpx.Response(200 if api_ok else 503, json={"status": "ok"})

    class FakeProvider:
        def __init__(self, cfg):
            assert cfg == config

        def status(self):
            if provider_state is None:
                raise AdapterError("WAHA_UNAVAILABLE")
            return {"state": provider_state}

        def close(self):
            pass

    monkeypatch.setattr(operator.httpx, "Client", FakeHttp)
    monkeypatch.setattr(operator, "LocalWahaClient", FakeProvider)
    result = operator.monitor_once(config, binding, factory=factory)
    assert result["api_health"]["state"] == ("healthy" if api_ok else "unavailable")
    assert result["provider_health"]["state"] == (
        "healthy" if provider_state == "WORKING" else "unavailable"
    )
    assert result["pipeline_ready"] == (api_ok and provider_state == "WORKING")
    assert result["review_required"] == (not api_ok or provider_state != "WORKING")
    with pytest.raises(AdapterError):
        operator.monitor_once(
            replace(config), binding, api_url="http://untrusted.invalid", factory=factory
        )


def test_login_session_commits_before_cookie_is_sent(recovery):
    from http.cookies import SimpleCookie

    from gigmate.api import app
    from gigmate.db import LoginSession
    from gigmate.identity import digest

    _, factory, _, _, _, _ = recovery
    observed = []

    async def wrapped(scope, receive, send):
        async def inspect_send(message):
            if message["type"] == "http.response.start":
                cookie = SimpleCookie()
                for name, value in message["headers"]:
                    if name.lower() == b"set-cookie":
                        cookie.load(value.decode())
                if "gigmate_session" in cookie:
                    with factory() as db:
                        observed.append(
                            db.get(LoginSession, digest(cookie["gigmate_session"].value))
                            is not None
                        )
            await send(message)

        await app(scope, receive, inspect_send)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=wrapped), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "merchant", "password": "demo-only-change-me"},
            )
            assert response.status_code == 200

    asyncio.run(exercise())
    assert observed == [True]


def test_waha_health_rejects_unreadable_binding_even_when_database_is_healthy(
    recovery, monkeypatch
):
    from gigmate import api

    monkeypatch.setenv("WAHA_CONNECTOR_CONFIG", "synthetic-unreadable-binding")

    def unavailable():
        raise BusinessError(503, "CONNECTOR_CONFIG_INVALID", "Connector configuration is invalid")

    monkeypatch.setattr(api, "configured_binding", unavailable)
    response = recovery[0].get("/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CONNECTOR_CONFIG_INVALID"


def test_waha_health_checks_binding_ownership_and_preserves_replay(recovery, monkeypatch):
    from dataclasses import replace

    from gigmate import api

    monkeypatch.setenv("WAHA_CONNECTOR_CONFIG", "synthetic-binding")
    binding = recovery[4]
    monkeypatch.setattr(api, "configured_binding", lambda: binding)
    assert recovery[0].get("/health").status_code == 200
    monkeypatch.setattr(
        api,
        "configured_binding",
        lambda: replace(binding, account_id="00000000-0000-4000-8000-000000000002"),
    )
    assert recovery[0].get("/health").status_code == 503
    monkeypatch.delenv("WAHA_CONNECTOR_CONFIG")
    assert recovery[0].get("/health").status_code == 200


def test_private_binding_directory_allows_atomic_replacement_and_legacy_read(
    recovery, monkeypatch, tmp_path
):
    from dataclasses import asdict

    from scripts import waha_ingress as operator

    from gigmate.waha_client import LocalWahaConfig

    monkeypatch.setattr(operator, "private_directory", lambda: tmp_path)
    binding = recovery[4]
    (tmp_path / "ingress.json").write_text(json.dumps(asdict(binding)), encoding="utf-8")
    config = LocalWahaConfig(
        "http://127.0.0.1:18700",
        binding.account_id,
        "default",
        "synthetic-" + "k" * 40,
        binding.secret,
    )
    assert operator.local_binding(config) == binding

    operator.save_binding(binding)
    assert operator.binding_path() == tmp_path / "bindings" / "ingress.json"
    assert operator.local_binding(config) == binding
    operator.save_binding(binding)
    assert operator.local_binding(config) == binding


@pytest.mark.parametrize(
    "project,bundles",
    [
        ("unrelated-project", {"waha-monitor-config": {"config.json": {}}}),
        ("gigmate-waha-a02", {"waha_sessions": {"config.json": {}}}),
        ("gigmate-waha-a02", {"waha-monitor-config": {"../secret.json": {}}}),
        ("gigmate-waha-a02", {"waha-ingress-bindings": {"config.json": {}}}),
    ],
)
def test_container_sync_refuses_unrelated_volumes_or_paths(project, bundles):
    from scripts.waha_container_config import sync_volumes

    with pytest.raises(RuntimeError, match="INVALID_CONFIG_VOLUME_TARGET"):
        sync_volumes(project, bundles, run=lambda *a, **kw: pytest.fail("must not run Docker"))


def test_private_container_sync_uses_stdin_not_argv(recovery):
    from types import SimpleNamespace

    from scripts.waha_container_config import sync_private_config

    from gigmate.waha_client import LocalWahaConfig

    binding = recovery[4]
    config = LocalWahaConfig(
        "http://127.0.0.1:18700",
        binding.account_id,
        "default",
        "synthetic-" + "k" * 40,
        binding.secret,
    )
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    assert sync_private_config(config, binding, run=run)["container_config_synced"]
    command, kwargs = calls[-1]
    assert binding.secret not in str(command) and config.api_key not in str(command)
    assert command[command.index("--network") + 1] == "none"
    payload = json.loads(kwargs["input"])
    assert payload["waha-ingress-bindings"]["ingress.json"]["secret"] == binding.secret
    assert payload["waha-monitor-config"]["config.json"]["api_key"] == config.api_key


def test_container_sync_failure_never_returns_private_stderr(recovery):
    from types import SimpleNamespace

    from scripts.waha_container_config import sync_volumes

    secret = recovery[4].secret
    with pytest.raises(RuntimeError) as exc:
        sync_volumes(
            "gigmate-waha-a02",
            {"waha-ingress-bindings": {"ingress.json": {"secret": secret}}},
            run=lambda *a, **kw: SimpleNamespace(returncode=1, stderr=secret),
        )
    assert str(exc.value) == "CONTAINER_CONFIG_SYNC_FAILED"
