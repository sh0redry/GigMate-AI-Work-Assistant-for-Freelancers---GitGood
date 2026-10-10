"""Disposable PostgreSQL + actual HTTP API/worker, synthetic provider, no WhatsApp account."""

import argparse
import base64
import json
import hashlib
import hmac
import os
import socket
import subprocess
import sys
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "gigmate-waha-setup-check"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra/waha-setup-check.compose.yaml")]
URL = "postgresql+psycopg://gigmate:synthetic-setup-only@127.0.0.1:16432/gigmate_setup"
ACCOUNT = "00000000-0000-4000-8000-000000000001"
CONNECTION = "00000000-0000-4000-8000-000000000070"
SECRET = "synthetic-setup-secret-" + "a" * 64
KEY = "synthetic-setup-api-" + "b" * 64
state = {"session": None, "writes": 0}
stop_requested = threading.Event()


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, value, code=200, png=False):
        data = value if png else json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "image/png" if png else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("X-Api-Key") != KEY:
            return self.answer({}, 401)
        if self.path == "/api/server/version":
            return self.answer({"version": "2026.9.1", "engine": "WEBJS"})
        if self.path.startswith("/api/sessions/default"):
            return self.answer(state["session"] or {}, 200 if state["session"] else 404)
        if self.path.startswith("/api/default/auth/qr"):
            return self.answer(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aA4sAAAAASUVORK5CYII="
                ),
                png=True,
            )
        if self.path.startswith("/api/default/chats"):
            return self.answer(
                [{"id": "synthetic:peer-new@lid", "name": "Synthetic participant"}]
            )
        self.answer({}, 404)

    def do_POST(self):
        if self.headers.get("X-Api-Key") != KEY:
            return self.answer({}, 401)
        if self.path == "/__test/shutdown":
            stop_requested.set()
            return self.answer({"synthetic_shutdown": True})
        if self.path == "/__test/state":
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            status = body.get("state")
            if status not in {"WORKING", "SCAN_QR_CODE", "STOPPED", "FAILED"}:
                return self.answer({}, 422)
            state["session"]["status"] = status
            state["session"]["engine"] = (
                None if status == "STOPPED" else {"engine": "WEBJS"}
            )
            return self.answer({"synthetic_state": status})
        if self.path == "/api/sessions/default/restart":
            state["writes"] += 1
            state["session"]["status"] = "SCAN_QR_CODE"
            state["session"]["engine"] = {"engine": "WEBJS"}
            return self.answer({"name": "default"})
        if self.path != "/api/sessions":
            return self.answer({}, 404)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        state["writes"] += 1
        state["session"] = {
            **body,
            "status": "SCAN_QR_CODE",
            "engine": {"engine": "WEBJS"},
        }
        self.answer(state["session"])


def command(args, env=None):
    result = subprocess.run(
        args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180
    )
    if result.returncode:
        if "pytest" in args:
            # Synthetic test diagnostics stay in ignored local-data, not console traces.
            (ROOT / "local-data/waha-setup-check/pytest-failure.txt").write_text(
                result.stdout + result.stderr, encoding="utf-8"
            )
            for line in result.stdout.splitlines():
                if line.startswith(("FAILED ", "ERROR ")):
                    print(line.split(" - ")[0], flush=True)
        raise RuntimeError("SETUP_CHECK_COMMAND_FAILED")
    return result.stdout


def wait(check):
    until = time.monotonic() + 50
    while time.monotonic() < until:
        try:
            if check():
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("SETUP_CHECK_WAIT_TIMEOUT")


def checkpoint(name):
    print(json.dumps({"checkpoint": name, "passed": True}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument(
        "--frontend",
        action="store_true",
        help="Serve synthetic-only browser acceptance on 18803 for thirty minutes",
    )
    parser.add_argument(
        "--suite", action="store_true", help="Also run full PostgreSQL suite"
    )
    args = parser.parse_args()
    if command(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=com.docker.compose.project=" + PROJECT,
        ]
    ).strip():
        raise RuntimeError("EXISTING_SETUP_CHECK_PROJECT_PRESERVED")
    if (
        PROJECT + "_setup-data"
        in command(["docker", "volume", "ls", "--format", "{{.Name}}"]).splitlines()
    ):
        raise RuntimeError("EXISTING_SETUP_CHECK_VOLUME_PRESERVED")
    for port in (16432, 18800, 18802):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    private = ROOT / "local-data/waha-setup-check"
    if private.resolve() != ROOT.resolve() / "local-data/waha-setup-check":
        raise RuntimeError("PRIVATE_PATH_REQUIRED")
    private.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "binding.json"):
        if (private / name).is_symlink():
            raise RuntimeError("PRIVATE_PATH_REQUIRED")
    config = dict(
        base_url="http://127.0.0.1:18800",
        account_id=ACCOUNT,
        session="default",
        api_key=KEY,
        webhook_secret=SECRET,
        allowlisted_chats=[],
        consent_active=True,
    )
    binding = dict(
        connection_id=CONNECTION,
        account_id=ACCOUNT,
        instance_id="synthetic-setup",
        session_id="default",
        secret=SECRET,
    )
    (private / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (private / "binding.json").write_text(json.dumps(binding), encoding="utf-8")
    env = {
        **os.environ,
        "DATABASE_URL": URL,
        "PYTHONPATH": str(ROOT / "apps/backend/src"),
        "WAHA_CONTROL_CONFIG": str(private / "config.json"),
        "WAHA_CONNECTOR_CONFIG": str(private / "binding.json"),
        "WAHA_CONTROL_INTERNAL": "false",
        "TRUSTED_ORIGINS": "http://127.0.0.1:18803,http://localhost:18803",
    }
    processes, server = [], None
    try:
        command([*COMPOSE, "up", "-d", "--wait", "db"])
        command(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "apps/backend/alembic.ini",
                "upgrade",
                "head",
            ],
            env,
        )
        os.environ["DATABASE_URL"] = URL
        sys.path.insert(0, str(ROOT / "apps/backend/src"))
        from gigmate.db import Account, Session, WahaConnection
        from gigmate.identity import password_hash

        with Session.begin() as db:
            for identifier, username in (
                (ACCOUNT, "merchant"),
                ("00000000-0000-4000-8000-000000000099", "other"),
            ):
                db.add(
                    Account(
                        id=identifier,
                        username=username,
                        password_hash=password_hash("demo-only-change-me"),
                        active=True,
                    )
                )
            db.flush()
            db.add(
                WahaConnection(
                    id=CONNECTION,
                    account_id=ACCOUNT,
                    instance_id="synthetic-setup",
                    session_id="default",
                    enabled=True,
                )
            )
        server = ThreadingHTTPServer(("127.0.0.1", 18800), Provider)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        for module_args in (
            (
                "uvicorn",
                "gigmate.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18802",
                "--no-access-log",
                "--log-level",
                "error",
            ),
            ("gigmate.worker",),
        ):
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-m", *module_args],
                    cwd=ROOT,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        import httpx

        with httpx.Client(
            base_url="http://127.0.0.1:18802", trust_env=False, timeout=10
        ) as client:
            wait(lambda: client.get("/health").status_code == 200)
            csrf = client.post(
                "/api/v1/auth/login",
                json={"username": "merchant", "password": "demo-only-change-me"},
            ).json()["data"]["csrf_token"]
            headers = {"X-CSRF-Token": csrf}
            base = f"/api/v1/connectors/{CONNECTION}"

            def setup():
                return client.get(base + "/setup").json()["data"]

            def action(kind, key):
                body = {"action": kind, "expected_version": setup()["control_version"]}
                response = client.post(
                    base + "/operations",
                    json=body,
                    headers={**headers, "Idempotency-Key": key},
                )
                assert response.status_code == 202
                identifier = response.json()["data"]["id"]
                wait(
                    lambda: (
                        client.get(base + "/operations/" + identifier).json()["data"][
                            "state"
                        ]
                        == "succeeded"
                    )
                )
                return body, identifier

            original, identifier = action("connect", "new-session")
            repeat = client.post(
                base + "/operations",
                json=original,
                headers={**headers, "Idempotency-Key": "new-session"},
            )
            assert repeat.json()["data"]["id"] == identifier and state["writes"] == 1
            checkpoint("durable_connect_idempotence")
            qr = client.get(base + "/qr")
            assert qr.status_code == 200 and "no-store" in qr.headers["cache-control"]
            checkpoint("owned_qr_no_cache")
            state["session"]["status"] = "WORKING"
            action("discover", "recent-contacts")
            choices = client.get(base + "/chats")
            assert "synthetic:peer-new" not in choices.text
            selection = {
                "expected_version": setup()["control_version"],
                "selected_ids": [choices.json()["data"][0]["id"]],
                "consent": True,
            }
            assert (
                client.put(base + "/chats", json=selection, headers=headers).status_code
                == 200
            )
            assert (
                client.put(base + "/chats", json=selection, headers=headers).status_code
                == 409
            )
            checkpoint("opaque_chat_selection_versioning")
            # Real HTTP reception and separate worker route into B's evidence seam.
            from sqlalchemy import select, func
            from gigmate.db import Job, Proposal, ModelCallTrace, ChangeRow

            def signed_message(event_id):
                body = json.dumps(
                    {
                        "id": event_id,
                        "event": "message.any",
                        "session": "default",
                        "timestamp": int(time.time() * 1000),
                        "payload": {
                            "id": event_id + ":message",
                            "fromMe": False,
                            "from": "synthetic:peer-new@lid",
                            "hasMedia": False,
                            "body": "Synthetic integration text requiring review",
                            "ack": 1,
                        },
                    },
                    separators=(",", ":"),
                ).encode()
                return client.post(
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

            receipt = signed_message("synthetic:http-extraction")
            assert receipt.status_code == 200
            event_id = receipt.json()["data"]["event_id"]

            def evidence_completed():
                with Session() as db:
                    job = db.scalar(select(Job).where(Job.event_id == event_id))
                    return job is not None and job.state == "completed"

            wait(evidence_completed)
            with Session() as db:
                assert (
                    db.scalar(select(Job).where(Job.event_id == event_id)).error_code
                    == "EXTRACTION_NEEDS_REVIEW"
                )
                proposal = db.scalar(
                    select(Proposal).where(Proposal.event_id == event_id)
                )
                assert proposal.assignment == "needs_review" and proposal.changes == []
                assert (
                    db.scalar(
                        select(func.count())
                        .select_from(ModelCallTrace)
                        .where(ModelCallTrace.proposal_id == proposal.id)
                    )
                    == 1
                )
                assert db.scalar(select(func.count()).select_from(ChangeRow)) == 0
            checkpoint("signed_live_origin_evidence_without_business_write")
            paused = client.post(
                base + "/pause",
                json={"expected_version": setup()["control_version"]},
                headers=headers,
            )
            assert paused.status_code == 200 and not setup()["enabled"]
            assert client.get(base + "/qr").status_code == 403
            denied = signed_message("synthetic:http-paused")
            assert (
                denied.status_code == 403
                and denied.json()["error"]["code"] == "CONSENT_REVOKED"
            )
            with Session() as db:
                assert db.scalar(select(func.count()).select_from(Proposal)) == 1
            assert (
                client.post(
                    base + "/resume",
                    json={"expected_version": setup()["control_version"]},
                    headers=headers,
                ).status_code
                == 200
            )
            checkpoint("pause_explicit_resume")
            processes[1].terminate()
            processes[1].wait(timeout=10)
            pending = client.post(
                base + "/operations",
                json={
                    "action": "inspect",
                    "expected_version": setup()["control_version"],
                },
                headers={**headers, "Idempotency-Key": "restart-pending"},
            )
            identifier = pending.json()["data"]["id"]
            processes[1] = subprocess.Popen(
                [sys.executable, "-m", "gigmate.worker"],
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            wait(
                lambda: (
                    client.get(base + "/operations/" + identifier).json()["data"][
                        "state"
                    ]
                    == "succeeded"
                )
            )
            checkpoint("worker_restart_preserves_intent")
            client.post(
                "/api/v1/auth/login",
                json={"username": "other", "password": "demo-only-change-me"},
            )
            assert client.get(base + "/qr").status_code == 404
            assert client.get(base + "/setup").status_code == 404
            checkpoint("account_isolation")
        result = command(
            [
                sys.executable,
                "scripts/run_evaluation.py",
                "--manifest",
                "contracts/evaluation/manifest.json",
                "--database-url",
                URL,
                "--provider",
                "deterministic",
            ],
            env,
        )
        report = json.loads(result)
        assert report["case_count"] == 7 and report["failed"] == 0
        checkpoint("evaluation_cli_persisted_seven_synthetic_cases")
        if args.suite:
            test_env = {**env, "TEST_DATABASE_URL": URL}
            for name in (
                "WAHA_CONTROL_CONFIG",
                "WAHA_CONNECTOR_CONFIG",
                "WAHA_CONTROL_INTERNAL",
            ):
                test_env.pop(name, None)
            result = command(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "apps/backend/tests",
                    "-q",
                    "--basetemp=local-data/pytest-setup-isolated-pg",
                ],
                test_env,
            )
            print(result[-1100:], flush=True)
        if args.frontend:
            processes.append(
                subprocess.Popen(
                    [
                        shutil.which("node"),
                        str(ROOT / "apps/web/node_modules/vite/bin/vite.js"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "18803",
                        "--strictPort",
                    ],
                    cwd=ROOT / "apps/web",
                    env={**env, "GIGMATE_API_URL": "http://127.0.0.1:18802", "CI": "1"},
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
            checkpoint("synthetic_frontend_serving_18803")
            until = time.monotonic() + 1800
            while time.monotonic() < until and not stop_requested.is_set():
                time.sleep(1)
        command(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "apps/backend/alembic.ini",
                "check",
            ],
            env,
        )
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        if server:
            server.shutdown()
            server.server_close()
        command([*COMPOSE, "down", "-v"])
        checkpoint("only_disposable_resources_cleaned")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "SETUP_CHECK_FAILED; inspect the last safe checkpoint"
        ) from None
