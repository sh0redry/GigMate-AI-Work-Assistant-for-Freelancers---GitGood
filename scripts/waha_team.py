"""Developer-owned WAHA startup and content-free live acceptance. Never sends messages."""

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "local-data/waha-a02"
PROFILE = PRIVATE / "team.json"
CHECKPOINT = PRIVATE / "acceptance-checkpoint.json"
DATABASE = (
    "postgresql+psycopg://gigmate:local-team-only@127.0.0.1:54349/gigmate_waha_team"
)
INTERNAL_DATABASE = DATABASE.replace("127.0.0.1", "host.docker.internal")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps/backend/src"))


class TeamError(Exception):
    pass


def private_path(path):
    if path.is_symlink() or not path.resolve().is_relative_to(
        ROOT.resolve() / "local-data"
    ):
        raise TeamError("PRIVATE_PATH_REQUIRED")
    return path


def run(args, env=None):
    try:
        result = subprocess.run(
            args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300
        )
    except (OSError, subprocess.SubprocessError):
        raise TeamError("DEPENDENCY_OR_COMMAND_UNAVAILABLE") from None
    if result.returncode:
        # Never expose Docker/provider stderr or database connection strings.
        raise TeamError("LOCAL_COMMAND_FAILED_CHECK_DOCTOR")
    return result.stdout


def compose(*args):
    architecture = (
        run(["docker", "info", "--format", "{{.Architecture}}"]).strip().lower()
    )
    if architecture not in {"amd64", "x86_64", "arm64", "aarch64"}:
        raise TeamError("UNSUPPORTED_DOCKER_ARCHITECTURE")
    command = [
        "docker",
        "compose",
        "--env-file",
        str(PRIVATE / ".env"),
        "-f",
        str(ROOT / "infra/waha.compose.yaml"),
        "-f",
        str(ROOT / "infra/waha-ingress.compose.yaml"),
    ]
    if architecture in {"arm64", "aarch64"}:
        command.extend(["-f", str(ROOT / "infra/waha-arm64.compose.yaml")])
    if os.environ.get("WAHA_MEDIA_ENABLED") == "true":
        command.extend(["-f", str(ROOT / "infra/waha-media.compose.yaml")])
    return [*command, *args]


def environment():
    env = os.environ.copy()
    if PROFILE.exists():
        profile = json.loads(private_path(PROFILE).read_text(encoding="utf-8"))
        if profile != {"workspace": str(ROOT.resolve()), "database": DATABASE}:
            raise TeamError("TEAM_PROFILE_WORKSPACE_MISMATCH")
        if env.get("DATABASE_URL") not in (None, DATABASE):
            raise TeamError("DATABASE_ENV_CONFLICT")
        env["DATABASE_URL"] = DATABASE
        env["WAHA_DATABASE_URL"] = INTERNAL_DATABASE
    elif (PRIVATE / "database.json").exists():
        saved = json.loads(
            private_path(PRIVATE / "database.json").read_text(encoding="utf-8")
        )
        if saved.get("workspace") != str(ROOT.resolve()):
            raise TeamError("DATABASE_PROFILE_WORKSPACE_MISMATCH")
        if env.get("DATABASE_URL") not in (None, saved.get("database_url")):
            raise TeamError("DATABASE_ENV_CONFLICT")
        env["DATABASE_URL"] = saved["database_url"]
    if not env.get("DATABASE_URL", "").startswith("postgresql+psycopg://"):
        raise TeamError("SET_POSTGRES_DATABASE_URL_OR_TEAM_INIT")
    from sqlalchemy.engine import make_url

    url = make_url(env["DATABASE_URL"])
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise TeamError("LOCAL_DATABASE_REQUIRED")
    env["PYTHONPATH"] = str(ROOT / "apps/backend/src")
    return env


def remember_database(env):
    """Explicitly remember a verified legacy installation URL, never infer a database."""
    if PROFILE.exists():
        raise TeamError("TEAM_PROFILE_ALREADY_MANAGES_DATABASE")
    from sqlalchemy import create_engine, text
    from scripts.waha_ingress import local_binding
    from scripts.waha_local import load_config

    binding = local_binding(load_config())
    with create_engine(
        env["DATABASE_URL"], connect_args={"connect_timeout": 3}
    ).connect() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        if not db.execute(
            text("SELECT id FROM waha_connections WHERE id=:cid AND account_id=:aid"),
            {"cid": binding.connection_id, "aid": binding.account_id},
        ).scalar():
            raise TeamError("BINDING_DATABASE_MISMATCH")
    target = private_path(PRIVATE / "database.json")
    import tempfile

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=PRIVATE, delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(
                {"workspace": str(ROOT.resolve()), "database_url": env["DATABASE_URL"]},
                file,
            )
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return {"database_profile_saved": True, "credentials_printed": False}


def initialize():
    private_path(PRIVATE)
    if any((PRIVATE / name).exists() for name in ("config.json", ".env", "team.json")):
        raise TeamError("EXISTING_SETUP_PRESERVED_USE_EXISTING_RUNBOOK")
    # Fixed names/ports intentionally allow one installation per machine.
    projects = run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=com.docker.compose.project=gigmate-waha-a02",
        ]
    )
    team = run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=com.docker.compose.project=gigmate-waha-team",
        ]
    )
    volumes = run(["docker", "volume", "ls", "--format", "{{.Name}}"])
    if (
        projects.strip()
        or team.strip()
        or any(
            name.startswith(("gigmate-waha-a02_", "gigmate-waha-team_"))
            for name in volumes.splitlines()
        )
    ):
        raise TeamError("EXISTING_DOCKER_SETUP_DO_NOT_OVERWRITE")
    for port in (54349, 18700, 18701, 18702):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise TeamError("LOCAL_PORT_IN_USE") from None
    from scripts.waha_local import initialize as init_config

    init_config()
    private_path(PROFILE).write_text(
        json.dumps({"workspace": str(ROOT.resolve()), "database": DATABASE}),
        encoding="utf-8",
    )
    return {"initialized": True, "secrets_printed": False, "scan_required": True}


def startup(env):
    if not PROFILE.exists():
        raise TeamError("TEAM_INIT_REQUIRED_EXISTING_SETUP_PRESERVED")
    run(["docker", "info", "--format", "{{.ServerVersion}}"])
    run(
        [
            "docker",
            "compose",
            "-f",
            str(ROOT / "infra/waha-team.compose.yaml"),
            "up",
            "-d",
            "--wait",
            "db",
        ]
    )
    run(
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
    os.environ["DATABASE_URL"] = env["DATABASE_URL"]
    from gigmate.db import Account, Session
    from gigmate.identity import password_hash

    with Session.begin() as db:
        if db.get(Account, "00000000-0000-4000-8000-000000000001") is None:
            db.add(
                Account(
                    id="00000000-0000-4000-8000-000000000001",
                    username="merchant",
                    password_hash=password_hash("demo-only-change-me"),
                    active=True,
                )
            )
    # No replay conversations/orders seeded; new connections start with empty allowlists.
    from scripts.waha_ingress import (
        binding_path,
        local_binding,
        provision,
        save_binding,
    )
    from scripts.waha_local import load_config
    from scripts.waha_container_config import sync_private_config

    if binding_path().resolve() != (PRIVATE / "bindings/ingress.json").resolve():
        raise TeamError("PRIVATE_BINDING_PATH_MISMATCH")
    config = load_config()
    if (PRIVATE / "bindings/ingress.json").exists():
        binding = local_binding(config)
        from sqlalchemy import select
        from gigmate.db import WahaConnection

        with Session.begin() as db:
            if (
                db.scalar(
                    select(WahaConnection.id).where(
                        WahaConnection.id == binding.connection_id,
                        WahaConnection.account_id == binding.account_id,
                    )
                )
                is None
            ):
                raise TeamError("BINDING_DATABASE_MISMATCH")
        # Restart must not resume a paused connection or change its allowlist.
    else:
        with Session.begin() as db:
            binding = provision(db, config, "local-waha-webjs")
        save_binding(binding)
    migrate_legacy_restart(binding)
    sync_private_config(config, binding)
    run(
        compose(
            "up",
            "--build",
            "-d",
            "--wait",
            "waha",
            "ingress",
            "ingress-worker",
            "ingress-monitor",
        ),
        env,
    )
    return {
        "services_started": True,
        "scan_or_status_next": True,
        "sending_enabled": False,
    }


def migrate_legacy_restart(binding):
    """Preserve bridge uncertainty before enabling the canonical controller."""
    path = (
        ROOT
        / "local-data/d01-operations"
        / ("restart-" + binding.connection_id + ".json")
    )
    if not path.exists():
        return {"legacy_imported": False}
    private_path(path)
    original = path.read_bytes()
    record = json.loads(original.decode("utf-8"))
    from gigmate.db import Session, Account
    from gigmate import waha_controls
    from types import SimpleNamespace
    from sqlalchemy import select

    with Session.begin() as db:
        account = db.scalar(
            select(Account).where(Account.id == binding.account_id).with_for_update()
        )
        if not account or not account.active:
            raise TeamError("LEGACY_OWNER_UNAVAILABLE")
        row = waha_controls.owned(
            db, SimpleNamespace(id=binding.account_id), binding.connection_id, lock=True
        )
        identifier = waha_controls.import_legacy_restart(db, row, record)
    if identifier:
        if path.read_bytes() != original:
            raise TeamError("LEGACY_RECORD_CHANGED_REVIEW_REQUIRED")
        import tempfile

        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False
            ) as file:
                json.dump(
                    {
                        **record,
                        "legacy_state": record["state"],
                        "state": "migrated",
                        "operation_id": identifier,
                    },
                    file,
                )
                file.flush()
                os.fsync(file.fileno())
                temporary = Path(file.name)
            os.replace(temporary, path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    return {
        "legacy_imported": bool(identifier),
        "reconciliation_required": bool(identifier),
    }


def doctor(env):
    checks = {}
    try:
        run(["docker", "info", "--format", "{{.ServerVersion}}"])
        checks["docker"] = "healthy"
    except TeamError:
        checks["docker"] = "unavailable_or_access_denied_check_docker_desktop"
    from sqlalchemy import create_engine, text
    from alembic.script import ScriptDirectory

    try:
        with create_engine(
            env["DATABASE_URL"], connect_args={"connect_timeout": 3}
        ).connect() as db:
            version = db.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            head = ScriptDirectory(
                str(ROOT / "apps/backend/migrations")
            ).get_current_head()
            checks["database"] = "healthy" if version == head else "migration_required"
    except Exception:
        checks["database"] = "unavailable_or_migration_required"
    try:
        from scripts.waha_ingress import local_binding
        from scripts.waha_local import load_config

        local_binding(load_config())
        checks["binding"] = "valid_host_configuration"
    except Exception:
        checks["binding"] = "configure_or_provision_required"
    import httpx

    for name, url in (("api", "http://127.0.0.1:18702/health"),):
        try:
            with httpx.Client(
                timeout=3, trust_env=False, follow_redirects=False
            ) as client:
                checks[name] = (
                    "healthy"
                    if client.get(url).status_code == 200
                    else "unavailable_check_binding"
                )
        except httpx.HTTPError:
            checks[name] = "unavailable_start_services"
    return {
        "checks": checks,
        "next": "run ingress diagnose for provider/worker/monitor readiness",
    }


def evidence(env, checkpoint=False):
    os.environ["DATABASE_URL"] = env["DATABASE_URL"]
    from sqlalchemy import create_engine, text
    from scripts.waha_ingress import local_binding
    from scripts.waha_local import load_config

    binding = local_binding(load_config())
    with create_engine(
        env["DATABASE_URL"], connect_args={"connect_timeout": 3}
    ).connect() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        owned = db.execute(
            text("SELECT id FROM waha_connections WHERE id=:cid AND account_id=:aid"),
            {"cid": binding.connection_id, "aid": binding.account_id},
        ).scalar()
        if not owned:
            raise TeamError("BINDING_DATABASE_MISMATCH")
        if checkpoint:
            # Server clock avoids assuming host/provider clock synchronization.
            at = db.execute(text("SELECT clock_timestamp()")).scalar().isoformat()
            private_path(CHECKPOINT).write_text(
                json.dumps({"connection_id": owned, "since": at}), encoding="utf-8"
            )
            return {
                "checkpoint_saved": True,
                "since": at,
                "next": "send, edit, revoke ONE new allowed text; then verify",
            }
        mark = json.loads(private_path(CHECKPOINT).read_text(encoding="utf-8"))
        if mark["connection_id"] != owned:
            raise TeamError("CHECKPOINT_CONNECTION_MISMATCH")
        datetime.fromisoformat(mark["since"]).astimezone(UTC)
        rows = db.execute(
            text("""
            SELECT i.payload->>'event_type' AS event_type, i.payload->>'message_revision' AS revision,
            dense_rank() OVER (ORDER BY i.payload->'payload'->>'message_id') AS sample_group,
            j.state AS job_state, j.attempts, m.data->>'revoked' AS revoked,
            (m.provider_message_id=w.provider_message_id) AS identity_matches,
            w.revision AS latest_revision
            FROM inbox i LEFT JOIN jobs j ON j.event_id=i.id
            LEFT JOIN message_revisions m ON m.id=i.payload->'payload'->>'message_id'
              AND m.revision=(i.payload->>'message_revision')::integer
            LEFT JOIN waha_messages w ON w.message_id=m.id
            WHERE i.connection_id=:cid AND i.account_id=:aid AND i.received_at>:since
            ORDER BY i.received_at LIMIT 101
        """),
            {"cid": owned, "aid": binding.account_id, "since": mark["since"]},
        ).mappings()
        return summarize([dict(row) for row in rows])


def summarize(rows):
    if len(rows) > 100:
        raise TeamError("CHECKPOINT_RANGE_TOO_LARGE_RETEST_WITH_NEW_CHECKPOINT")
    groups = {}
    for row in rows:
        if row["event_type"] in {
            "message.created",
            "message.edited",
            "message.revoked",
        }:
            groups.setdefault(row["sample_group"], []).append(row)
    verified = []
    for number, events in groups.items():
        if (
            [e["event_type"] for e in events]
            == ["message.created", "message.edited", "message.revoked"]
            and [int(e["revision"]) for e in events] == [1, 2, 3]
            and all(
                e["identity_matches"] and e["job_state"] == "completed" for e in events
            )
            and events[-1]["revoked"] == "true"
            and events[-1]["latest_revision"] == 3
        ):
            verified.append(number)
    return {
        "mutation_sequence_verified": bool(verified),
        "verified_groups": verified,
        "event_count": len(rows),
        "safe_events": rows,
        "content_read": False,
        "note": "Job completion is not AI extraction or external sending; incidents require separate review",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "init",
            "up",
            "doctor",
            "checkpoint",
            "verify",
            "run",
            "stop",
            "import-legacy",
            "remember-database",
        ],
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == "init":
        result = initialize()
    else:
        env = environment()
        if args.command == "up":
            result = startup(env)
        elif args.command == "doctor":
            result = doctor(env)
        elif args.command == "remember-database":
            result = remember_database(env)
        elif args.command == "import-legacy":
            os.environ["DATABASE_URL"] = env["DATABASE_URL"]
            from scripts.waha_local import load_config
            from scripts.waha_ingress import local_binding

            result = migrate_legacy_restart(local_binding(load_config()))
        elif args.command in {"checkpoint", "verify"}:
            result = evidence(env, checkpoint=args.command == "checkpoint")
        elif args.command == "stop":
            if not PROFILE.exists():
                raise TeamError("TEAM_PROFILE_REQUIRED")
            run(compose("stop"), env)
            run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(ROOT / "infra/waha-team.compose.yaml"),
                    "stop",
                ],
                env,
            )
            result = {"stopped": True, "volumes_preserved": True}
        else:
            if len(args.args) < 2 or args.args[0] not in {"local", "ingress", "smoke"}:
                raise TeamError("USE_RUN_LOCAL_OR_INGRESS_COMMAND_OR_SMOKE_HTTP")
            target = {
                "local": "waha_local.py",
                "ingress": "waha_ingress.py",
                "smoke": "smoke_waha_ingress.py",
            }[args.args[0]]
            call = [
                sys.executable,
                str(ROOT / "scripts" / target),
                *([] if args.args[0] == "smoke" else args.args[1:]),
            ]
            # Local selection requires an interactive terminal; provider scripts sanitize errors.
            return subprocess.call(call, cwd=ROOT, env=env)
    print(json.dumps(result))
    if args.command == "verify" and not result["mutation_sequence_verified"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        code = (
            str(exc)
            if isinstance(exc, TeamError)
            else "USE_PROJECT_VENV_INSTALL_BACKEND_LOCK"
            if isinstance(exc, ImportError)
            else "TEAM_OPERATION_FAILED_CHECK_DOCTOR"
        )
        print(json.dumps({"error": code}), file=sys.stderr)
        raise SystemExit(1) from None
