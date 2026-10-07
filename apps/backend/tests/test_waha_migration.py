"""Upgrade existing replay rows and downgrade only a disposable SQLite database."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def test_versioned_migration_preserves_replay_rows(tmp_path):
    root = Path(__file__).resolve().parents[3]
    url = "sqlite:///" + (tmp_path / "migration-only.db").as_posix()
    environment = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": str(root / "apps/backend/src")}

    def migrate(command, revision):
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "apps/backend/alembic.ini", command, revision],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )

    migrate("upgrade", "0001_replay_foundation")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO accounts (id,username,password_hash,active) VALUES (:id,:name,:hash,:active)"
            ),
            {"id": "synthetic-account", "name": "synthetic", "hash": "synthetic", "active": True},
        )
        db.execute(
            text(
                "INSERT INTO inbox (id,account_id,payload,digest,context_version,received_at) VALUES (:id,:account,:payload,:digest,1,:time)"
            ),
            {
                "id": "synthetic-event",
                "account": "synthetic-account",
                "payload": '{"synthetic":true}',
                "digest": "synthetic",
                "time": "2026-10-02 00:00:00",
            },
        )
        db.execute(
            text(
                "INSERT INTO jobs (id,event_id,account_id,state,attempts,available_at) "
                "VALUES ('synthetic-job','synthetic-event','synthetic-account','pending',0,'2026-10-02 00:00:00')"
            )
        )
    engine.dispose()
    migrate("upgrade", "head")
    engine = create_engine(url)
    assert "waha_connections" in inspect(engine).get_table_names()
    assert "waha_operations" in inspect(engine).get_table_names()
    assert "waha_controls" in inspect(engine).get_table_names()
    assert "waha_candidates" in inspect(engine).get_table_names()
    with engine.connect() as db:
        assert db.execute(text("SELECT payload, connection_id FROM inbox")).one() == (
            '{"synthetic":true}',
            None,
        )
        assert db.execute(text("SELECT state,lease_recoveries,completed_at FROM jobs")).one() == (
            "pending",
            0,
            None,
        )
    engine.dispose()
    migrate("downgrade", "0001_replay_foundation")
    engine = create_engine(url)
    assert "waha_connections" not in inspect(engine).get_table_names()
    assert "waha_operations" not in inspect(engine).get_table_names()
    assert "waha_controls" not in inspect(engine).get_table_names()
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM inbox")).scalar() == 1
    engine.dispose()
    migrate("upgrade", "head")
