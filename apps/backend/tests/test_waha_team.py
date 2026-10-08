"""Team isolation, private output and real acceptance metadata checks."""

import json
from types import SimpleNamespace

import pytest
from scripts import waha_team as team


def events():
    return [
        dict(
            event_type=kind,
            revision=str(rev),
            sample_group=1,
            job_state="completed",
            attempts=1,
            revoked="true" if rev == 3 else "false",
            identity_matches=True,
            latest_revision=3,
        )
        for rev, kind in enumerate(("message.created", "message.edited", "message.revoked"), 1)
    ]


def test_complete_mutation_and_ack():
    rows = events()
    rows.append(dict(event_type="message.ack", sample_group=2))
    result = team.summarize(rows)
    assert result["mutation_sequence_verified"] and result["verified_groups"] == [1]
    assert result["content_read"] is False


@pytest.mark.parametrize(
    "case", ["missing", "identity", "processing", "not_revoked", "different_group"]
)
def test_incomplete_or_wrong_sequence(case):
    rows = events()
    if case == "missing":
        rows.pop(1)
    elif case == "identity":
        rows[1]["identity_matches"] = False
    elif case == "processing":
        rows[-1]["job_state"] = "processing"
    elif case == "not_revoked":
        rows[-1]["revoked"] = "false"
    else:
        rows[-1]["sample_group"] = 2
    assert not team.summarize(rows)["mutation_sequence_verified"]


def test_evidence_range_never_silently_truncated():
    with pytest.raises(team.TeamError, match="RANGE_TOO_LARGE"):
        team.summarize(events() * 34)


def test_profile_is_bound_to_clone_and_rejects_env_override(tmp_path, monkeypatch):
    root = tmp_path / "clone"
    private = root / "local-data/waha-a02"
    private.mkdir(parents=True)
    profile = private / "team.json"
    profile.write_text(json.dumps({"workspace": str(root.resolve()), "database": team.DATABASE}))
    monkeypatch.setattr(team, "ROOT", root)
    monkeypatch.setattr(team, "PROFILE", profile)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert team.environment()["DATABASE_URL"] == team.DATABASE
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://secret:secret@localhost/other")
    with pytest.raises(team.TeamError, match="DATABASE_ENV_CONFLICT"):
        team.environment()
    monkeypatch.delenv("DATABASE_URL")
    profile.write_text(json.dumps({"workspace": "another-clone", "database": team.DATABASE}))
    with pytest.raises(team.TeamError, match="WORKSPACE_MISMATCH"):
        team.environment()


def test_existing_private_setup_not_overwritten(tmp_path, monkeypatch):
    private = tmp_path / "local-data/waha-a02"
    private.mkdir(parents=True)
    config = private / "config.json"
    config.write_text("private-existing-config")
    monkeypatch.setattr(team, "ROOT", tmp_path)
    monkeypatch.setattr(team, "PRIVATE", private)
    with pytest.raises(team.TeamError, match="EXISTING_SETUP_PRESERVED"):
        team.initialize()
    assert config.read_text() == "private-existing-config"


def test_existing_docker_resources_block_init(tmp_path, monkeypatch):
    monkeypatch.setattr(team, "ROOT", tmp_path)
    monkeypatch.setattr(team, "PRIVATE", tmp_path / "local-data/waha-a02")
    monkeypatch.setattr(team, "run", lambda args: "existing-container")
    with pytest.raises(team.TeamError, match="EXISTING_DOCKER_SETUP"):
        team.initialize()
    assert not team.PRIVATE.exists()


def test_dependency_errors_do_not_echo_secrets(monkeypatch):
    monkeypatch.setattr(
        team.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1, stdout="secret", stderr="private-password-and-message"
        ),
    )
    with pytest.raises(team.TeamError) as exc:
        team.run(["docker", "info"])
    assert "private-password" not in str(exc.value)
    assert "secret" not in str(exc.value)


def test_clean_bootstrap_and_restart_preserves_pause(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from uuid import uuid4

    from scripts import waha_ingress, waha_local
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import sessionmaker

    from gigmate.db import Account, Base, ConversationRow, Job, WahaConnection, WahaControl

    private = tmp_path / "local-data/waha-a02"
    monkeypatch.setattr(team, "ROOT", tmp_path)
    monkeypatch.setattr(team, "PRIVATE", private)
    monkeypatch.setattr(team, "PROFILE", private / "team.json")
    monkeypatch.setattr(waha_local, "private_directory", lambda: private)
    monkeypatch.setattr(waha_ingress, "private_directory", lambda: private)

    class FreePort:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def bind(self, address):
            pass

    monkeypatch.setattr(team.socket, "socket", FreePort)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    calls = []

    def run(args, env=None):
        calls.append(args)
        if "{{.Architecture}}" in args:
            return "x86_64"
        return ""

    monkeypatch.setattr(team, "run", run)
    assert team.initialize()["initialized"]
    config = waha_local.load_config()
    assert not config.allowlisted_chats
    assert len(config.webhook_secret) >= 32
    env = team.environment()
    monkeypatch.setenv("DATABASE_URL", env["DATABASE_URL"])
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr("gigmate.db.Session", factory)
    synced = []
    monkeypatch.setattr(
        "scripts.waha_container_config.sync_private_config",
        lambda cfg, binding: synced.append(binding),
    )
    assert team.startup(env)["services_started"]
    with factory.begin() as db:
        assert db.scalar(select(func.count()).select_from(Account)) == 1
        assert db.scalar(select(func.count()).select_from(ConversationRow)) == 0
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        connection = db.scalar(select(WahaConnection))
        connection.enabled = False
        connection_id = connection.id
    journal = tmp_path / "local-data/d01-operations" / ("restart-" + connection_id + ".json")
    journal.parent.mkdir()
    old_key = str(uuid4())
    journal.write_text(
        json.dumps({"key": old_key, "state": "unknown", "at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    team.startup(env)
    with factory.begin() as db:
        assert db.scalar(select(WahaConnection)).enabled is False
        assert db.scalar(select(func.count()).select_from(Account)) == 1
        operation = db.scalar(select(WahaControl))
        assert operation.state == "result_unknown" and operation.active_key == connection_id
        assert operation.request_key == "legacy-restart:" + old_key
    migrated = json.loads(journal.read_text(encoding="utf-8"))
    assert migrated["state"] == "migrated" and migrated["legacy_state"] == "unknown"
    assert migrated["key"] == old_key
    assert team.migrate_legacy_restart(synced[-1]) == {
        "legacy_imported": False,
        "reconciliation_required": False,
    }
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WahaControl)) == 1
    assert len(synced) == 2
    assert any("alembic" in args for args in calls)
    assert not any("create_session" in args for args in calls)
    before = (private / "bindings/ingress.json").read_bytes()
    monkeypatch.setattr(waha_ingress, "private_directory", lambda: tmp_path / "wrong-private")
    with pytest.raises(team.TeamError, match="PRIVATE_BINDING_PATH_MISMATCH"):
        team.startup(env)
    assert (private / "bindings/ingress.json").read_bytes() == before
    engine.dispose()


@pytest.mark.parametrize("architecture", ["amd64", "x86_64", "arm64", "aarch64"])
def test_compose_chooses_daemon_architecture_not_host_python(monkeypatch, architecture):
    monkeypatch.setattr(team, "run", lambda args: architecture)
    args = team.compose("up", "-d")
    arm = any("waha-arm64.compose.yaml" in item for item in args)
    assert arm is (architecture in {"arm64", "aarch64"})
    assert args[-2:] == ["up", "-d"]


def test_unknown_daemon_architecture_fails_clearly(monkeypatch):
    monkeypatch.setattr(team, "run", lambda args: "unknown")
    with pytest.raises(team.TeamError, match="UNSUPPORTED_DOCKER_ARCHITECTURE"):
        team.compose("up")
