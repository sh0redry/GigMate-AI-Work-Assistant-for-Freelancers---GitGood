"""Preserve data through both migration branches; downgrade disposable databases only."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


@pytest.fixture
def migration_database(tmp_path):
    postgres = os.environ.get("TEST_DATABASE_URL")
    if not postgres:
        yield "sqlite:///" + (tmp_path / "migration-only.db").as_posix()
        return
    assert postgres.startswith("postgresql+psycopg://")
    schema = "test_migration_" + uuid4().hex
    base = create_engine(postgres)
    with base.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield (
            make_url(postgres)
            .update_query_dict({"options": "-csearch_path=" + schema})
            .render_as_string(hide_password=False)
        )
    finally:
        with base.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


@pytest.mark.parametrize(
    "existing_revision",
    ["0004_waha_recovery", "0005_extraction_evidence", "0006_waha_provider_sample"],
)
def test_versioned_migration_preserves_replay_rows(migration_database, existing_revision):
    root = Path(__file__).resolve().parents[3]
    assert ScriptDirectory(str(root / "apps/backend/migrations")).get_heads() == [
        "0010_waha_media_evidence"
    ]
    url = migration_database
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
    migrate("upgrade", existing_revision)
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO waha_connections "
                "(id,account_id,instance_id,session_id,enabled,state,accepted,duplicates,stale_events) "
                "VALUES ('synthetic-connection','synthetic-account','synthetic-instance','default',false,'disconnected',3,1,0)"
            )
        )
        if existing_revision == "0006_waha_provider_sample":
            db.execute(
                text("UPDATE waha_connections SET control_version=7, provider_state='STOPPED'")
            )
        if existing_revision == "0005_extraction_evidence":
            db.execute(
                text(
                    "INSERT INTO evaluation_runs "
                    "(id,account_id,started_at,finished_at,provider_name,model_version,prompt_version,case_count,passed,failed,manifest_path) "
                    "VALUES ('synthetic-evaluation','synthetic-account','2026-10-09 00:00:00','2026-10-09 00:00:01','deterministic','synthetic','v1',1,1,0,'synthetic-manifest')"
                )
            )
    engine.dispose()
    migrate("upgrade", "head")

    engine = create_engine(url)
    assert "waha_connections" in inspect(engine).get_table_names()
    assert "waha_operations" in inspect(engine).get_table_names()
    assert "waha_controls" in inspect(engine).get_table_names()
    assert "waha_candidates" in inspect(engine).get_table_names()
    assert {"proposals", "model_call_traces", "evaluation_runs", "evaluation_cases"} <= set(
        inspect(engine).get_table_names()
    )
    assert {"provider_state", "provider_observed_at"} <= {
        item["name"] for item in inspect(engine).get_columns("waha_connections")
    }
    with engine.connect() as db:
        assert (
            db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0010_waha_media_evidence"
        )
        assert db.execute(text("SELECT accepted,duplicates,state FROM waha_connections")).one() == (
            3,
            1,
            "disconnected",
        )
        if existing_revision == "0006_waha_provider_sample":
            assert db.execute(
                text("SELECT control_version,provider_state FROM waha_connections")
            ).one() == (7, "STOPPED")
        if existing_revision == "0005_extraction_evidence":
            assert db.execute(text("SELECT id,passed FROM evaluation_runs")).one() == (
                "synthetic-evaluation",
                1,
            )
        payload, connection_id = db.execute(text("SELECT payload, connection_id FROM inbox")).one()
        # PostgreSQL returns JSON objects; SQLite text queries return JSON text.
        assert (json.loads(payload) if isinstance(payload, str) else payload) == {"synthetic": True}
        assert connection_id is None
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


def test_media_evidence_upgrade_does_not_invent_old_sending_times(migration_database):
    from datetime import UTC, datetime

    from sqlalchemy import MetaData, Table, select
    from sqlalchemy.orm import sessionmaker

    from gigmate.db import Account, ConversationRow, WahaChat, WahaConnection
    from gigmate.seed import seed

    root = Path(__file__).resolve().parents[3]
    environment = {
        **os.environ,
        "DATABASE_URL": migration_database,
        "PYTHONPATH": str(root / "apps/backend/src"),
    }

    def migrate(target):
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "apps/backend/alembic.ini", "upgrade", target],
            cwd=root,
            env=environment,
            capture_output=True,
            check=True,
        )

    migrate("0009_waha_media_ingestion")
    engine = create_engine(migration_database)
    factory = sessionmaker(engine)
    seed(factory)
    connection_id, chat_id, snapshot_id, asset_id, job_id = [str(uuid4()) for _ in range(5)]
    with factory.begin() as db:
        account = db.scalar(select(Account).where(Account.username == "merchant"))
        conversation = db.scalar(
            select(ConversationRow).where(ConversationRow.account_id == account.id)
        )
        account_id = account.id
        db.add(
            WahaConnection(
                id=connection_id,
                account_id=account.id,
                instance_id="synthetic-migration",
                session_id="default",
            )
        )
        db.flush()
        db.add(
            WahaChat(
                id=chat_id,
                connection_id=connection_id,
                conversation_id=conversation.id,
                provider_chat_id="synthetic:peer@lid",
            )
        )
    metadata = MetaData()
    tables = {
        name: Table(name, metadata, autoload_with=engine)
        for name in ["waha_snapshots", "waha_attachments", "waha_media_jobs"]
    }
    at = datetime(2026, 10, 10, tzinfo=UTC)
    with engine.begin() as db:
        db.execute(
            tables["waha_snapshots"]
            .insert()
            .values(
                id=snapshot_id,
                chat_id=chat_id,
                provider_message_id="synthetic:media",
                source="live",
                occurred_at=at,
                observed_at=at,
                revoked=False,
                data={"kind": "image"},
            )
        )
        db.execute(
            tables["waha_attachments"]
            .insert()
            .values(
                id=asset_id,
                snapshot_id=snapshot_id,
                connection_id=connection_id,
                account_id=account_id,
                source_fingerprint="synthetic",
                version=1,
                state="downloaded",
                created_at=at,
                expires_at=at,
            )
        )
        db.execute(
            tables["waha_media_jobs"]
            .insert()
            .values(
                id=job_id,
                attachment_id=asset_id,
                connection_id=connection_id,
                request_key="synthetic-old",
                command={"synthetic": True},
                version=0,
                context_version=0,
                source_fingerprint="synthetic",
                state="succeeded",
                stage="download",
                attempts=1,
                created_at=at,
                updated_at=at,
            )
        )
    engine.dispose()
    migrate("head")
    engine = create_engine(migration_database)
    with engine.connect() as db:
        assert (
            db.execute(
                text("SELECT message_sent_at FROM waha_snapshots WHERE id=:id"), {"id": snapshot_id}
            ).scalar_one()
            is None
        )
        assert (
            db.execute(
                text("SELECT input_context FROM waha_media_jobs WHERE id=:id"), {"id": job_id}
            ).scalar_one()
            is None
        )
        assert (
            db.execute(
                text("SELECT state FROM waha_media_jobs WHERE id=:id"), {"id": job_id}
            ).scalar_one()
            == "succeeded"
        )
    engine.dispose()
