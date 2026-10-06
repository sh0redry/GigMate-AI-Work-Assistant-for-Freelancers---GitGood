"""Run disposable PostgreSQL/API/worker faults with synthetic content only.

Uses exclusively gigmate-waha-recovery and refuses an existing project. The runner
never starts WAHA, fetches history or sends a WhatsApp message. Its synthetic-only
database/volume is removed in finally; live projects and private bindings are untouched.
"""

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from waha_container_config import sync_volumes
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra/waha-recovery.compose.yaml")]
URL = "postgresql+psycopg://gigmate:synthetic-recovery-only@127.0.0.1:54339/gigmate_recovery"
CONNECTION = "00000000-0000-4000-8000-000000000090"
ACCOUNT = "00000000-0000-4000-8000-000000000001"
SECRET = "synthetic-recovery-" + "a" * 64


def command(args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError("FAULT_COMMAND_FAILED")
    return result.stdout


def checkpoint(name):
    print(json.dumps({"checkpoint": name, "passed": True}), flush=True)


def wait_until(check, *, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.5)
    raise RuntimeError("FAULT_WAIT_TIMEOUT")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.parse_args()
    config = json.loads(command([*COMPOSE, "config", "--format", "json"]))
    assert config["name"] == "gigmate-waha-recovery"
    existing = command(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=com.docker.compose.project=gigmate-waha-recovery",
        ]
    )
    if existing.strip():
        raise RuntimeError("EXISTING_FAULT_PROJECT_REQUIRES_MANUAL_CLEANUP")
    volumes = command(["docker", "volume", "ls", "--format", "{{.Name}}"])
    if {
        "gigmate-waha-recovery_recovery-data",
        "gigmate-waha-recovery_recovery-binding",
    } & set(volumes.splitlines()):
        raise RuntimeError("EXISTING_FAULT_VOLUME_REQUIRES_MANUAL_CLEANUP")
    private = ROOT / "local-data/waha-recovery"
    private.mkdir(parents=True, exist_ok=True)
    if (
        private.resolve() != ROOT.resolve() / "local-data/waha-recovery"
        or (private / "binding.json").is_symlink()
    ):
        raise RuntimeError("INVALID_PRIVATE_PATH")
    binding_data = {
        "connection_id": CONNECTION,
        "account_id": ACCOUNT,
        "instance_id": "synthetic-recovery",
        "session_id": "default",
        "secret": SECRET,
    }
    (private / "binding.json").write_text(json.dumps(binding_data), encoding="utf-8")
    os.environ["DATABASE_URL"] = URL
    sys.path.insert(0, str(ROOT / "apps/backend/src"))
    import httpx
    from sqlalchemy import func, select
    from gigmate.db import (
        Session,
        Inbox,
        Job,
        WahaConnection,
        WahaChat,
        ConversationRow,
        WahaRecoveryIssue,
        engine,
    )
    from gigmate.seed import seed
    from gigmate.waha_ingress import WebhookBinding, status_view
    from gigmate.waha_recovery import (
        observe_pipeline,
        record_database_gap,
        acknowledge_issue,
    )

    binding = WebhookBinding(**binding_data)
    checks = []
    created = False
    http = httpx.Client(base_url="http://127.0.0.1:18712", timeout=15, trust_env=False)

    def done(name):
        checks.append(name)
        checkpoint(name)

    def healthy():
        try:
            return http.get("/health").status_code == 200
        except httpx.HTTPError:
            return False

    def observe(ok):
        with Session.begin() as db:
            observe_pipeline(db, binding, api_ok=ok, provider_ok=True)

    def status():
        with Session() as db:
            return status_view(db, db.get(WahaConnection, CONNECTION))

    def event(number):
        return {
            "id": f"synthetic:receipt-{number}",
            "event": "message.any",
            "session": "default",
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
            "payload": {
                "id": f"synthetic:message-{number}",
                "fromMe": False,
                "from": "synthetic:recovery@lid",
                "hasMedia": False,
                "body": "Synthetic recovery test text",
                "ack": 1,
            },
        }

    def post(payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        return http.post(
            f"/api/v1/connectors/waha/{CONNECTION}/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Hmac-Algorithm": "sha512",
                "X-Webhook-Hmac": hmac.new(
                    SECRET.encode(), body, hashlib.sha512
                ).hexdigest(),
            },
        )

    try:
        created = True
        sync_volumes(
            "gigmate-waha-recovery",
            {"recovery-binding": {"binding.json": binding_data}},
        )
        command([*COMPOSE, "up", "--build", "-d", "--wait", "db"])
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "apps/backend/src")}
        migrated = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "apps/backend/alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=40,
        )
        assert migrated.returncode == 0
        seed(Session)
        with Session.begin() as db:
            db.add(
                WahaConnection(
                    id=CONNECTION,
                    account_id=ACCOUNT,
                    instance_id="synthetic-recovery",
                    session_id="default",
                    enabled=True,
                    state="connected",
                    state_received_at=datetime.now(UTC),
                )
            )
            db.add(
                ConversationRow(
                    id="00000000-0000-4000-8000-000000000091",
                    account_id=ACCOUNT,
                    allowlisted=True,
                    context_version=0,
                )
            )
            db.flush()
            db.add(
                WahaChat(
                    id="00000000-0000-4000-8000-000000000092",
                    connection_id=CONNECTION,
                    provider_chat_id="synthetic:recovery@lid",
                    conversation_id="00000000-0000-4000-8000-000000000091",
                )
            )
        command([*COMPOSE, "up", "--build", "-d", "--wait", "api"])
        wait_until(healthy)
        initial = event(1)
        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(pool.map(lambda _: post(initial), range(3)))
        assert all(r.status_code == 200 for r in responses)
        assert sorted(r.json()["data"]["duplicate"] for r in responses) == [
            False,
            True,
            True,
        ]
        assert healthy() and status()["pending_jobs"] == 1
        done("parallel_http_deduplicates_without_stalling")

        observe(True)
        command([*COMPOSE, "stop", "-t", "1", "api"])
        assert not healthy()
        observe(False)
        command([*COMPOSE, "up", "-d", "--wait", "api"])
        wait_until(healthy)
        observe(True)
        assert post(initial).json()["data"]["duplicate"]
        assert status()["accepted"] == 1 and status()["review_required"]
        done("api_restart_preserves_receipt_and_gap_review")

        gap_started = datetime.now(UTC)
        command([*COMPOSE, "stop", "-t", "1", "db"])
        failed = event(2)
        assert http.get("/health").status_code == 503
        assert post(failed).status_code == 503
        done("database_outage_never_returns_durable_success")
        command([*COMPOSE, "up", "-d", "--wait", "db"])
        wait_until(healthy)
        with Session.begin() as db:
            record_database_gap(db, binding, gap_started)
        assert post(failed).status_code == 200
        assert post(failed).json()["data"]["duplicate"]
        with Session() as db:
            assert db.scalar(select(func.count()).select_from(Inbox)) == 2
            assert db.scalar(select(func.count()).select_from(Job)) == 2
        done("database_recovery_retry_commits_once")

        command([*COMPOSE, "up", "--build", "-d", "worker"])
        wait_until(lambda: status()["pending_jobs"] == 0)
        wait_until(lambda: status()["worker_health"]["state"] == "healthy")
        done("worker_processes_persisted_backlog_after_recovery")
        command([*COMPOSE, "stop", "-t", "0", "worker"])
        wait_until(lambda: status()["worker_health"]["state"] == "stale", timeout=45)
        observe(True)
        assert healthy() and not status()["pipeline_ready"]
        done("worker_crash_is_distinct_from_api_health")
        leased = event(3)
        response = post(leased)
        assert response.status_code == 200
        # Explicit persisted lease fixture; do not claim the killed worker owned this job.
        with Session.begin() as db:
            job = db.scalar(
                select(Job).where(Job.event_id == response.json()["data"]["event_id"])
            )
            job.state, job.attempts = "processing", 1
            job.lease_owner = "synthetic-crashed-owner"
            job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        command([*COMPOSE, "up", "-d", "worker"])
        wait_until(
            lambda: status()["processing_jobs"] == 0 and status()["pending_jobs"] == 0
        )
        wait_until(lambda: status()["worker_health"]["state"] == "healthy")
        observe(True)
        assert status()["metrics"]["lease_recoveries"] == 1
        assert status()["metrics"]["retries"] == 1
        assert status()["failed_jobs"] == 0
        done("worker_restart_recovers_synthetic_expired_lease_once")
        assert status()["review_required"]
        with Session.begin() as db:
            issues = list(db.scalars(select(WahaRecoveryIssue)))
            assert {"INGRESS_UNAVAILABLE", "DATABASE_UNAVAILABLE", "WORKER_GAP"} <= {
                i.code for i in issues
            }
            for row in issues:
                if row.recovered_at:
                    acknowledge_issue(db, binding, row.id, "reviewed_no_import")
        assert not status()["review_required"]
        done("manual_review_closes_synthetic_gaps_without_import")
        report = {
            "passed": True,
            "checks": checks,
            "synthetic_only": True,
            "external_sends": 0,
            "lease_fixture": True,
            "database": "PostgreSQL 17.9",
        }
        (private / "result.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report), flush=True)
    finally:
        http.close()
        engine.dispose()
        if created:
            command([*COMPOSE, "down", "--volumes", "--remove-orphans"])


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, AssertionError, OSError, subprocess.SubprocessError):
        raise SystemExit(
            "WAHA_RECOVERY_CHECK_FAILED; inspect the disposable project locally"
        ) from None
