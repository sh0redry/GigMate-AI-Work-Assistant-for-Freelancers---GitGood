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
    [
        "0004_waha_recovery",
        "0005_extraction_evidence",
        "0006_waha_provider_sample",
        "0009_approval_actions",
        "0011_waha_multitype_sending",
        "0012_waha_media_stop",
        "0013_merge_media_send",
        "0013_merge_approval_media",
        "0014_media_approvals",
        "0014_merge_approval_send",
        "0015_d03_approval_heads",
    ],
)
def test_versioned_migration_preserves_replay_rows(migration_database, existing_revision):
    root = Path(__file__).resolve().parents[3]
    assert ScriptDirectory(str(root / "apps/backend/migrations")).get_heads() == [
        "0017_job_assignments"
    ]
    url = migration_database
    environment = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": str(root / "apps/backend/src")}

    def migrate(command, revision=None):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "apps/backend/alembic.ini",
                command,
                *([revision] if revision else []),
            ],
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
        if existing_revision in {
            "0011_waha_multitype_sending",
            "0013_merge_media_send",
            "0014_merge_approval_send",
        }:
            db.execute(
                text(
                    "INSERT INTO waha_send_permissions (connection_id,version,enabled,chat_ids) "
                    "VALUES ('synthetic-connection',9,false,'[]')"
                )
            )
            db.execute(
                text(
                    "INSERT INTO waha_send_request_fences (connection_id,request_key,cancelled_at) "
                    "VALUES ('synthetic-connection','synthetic-cancelled-intent','2026-10-13 00:00:00')"
                )
            )
    engine.dispose()
    migrate("upgrade", "head")
    migrate("check")

    engine = create_engine(url)
    assert "waha_connections" in inspect(engine).get_table_names()
    assert "waha_operations" in inspect(engine).get_table_names()
    assert "waha_controls" in inspect(engine).get_table_names()
    assert "waha_send_permissions" in inspect(engine).get_table_names()
    assert "content_stop_reason" in {
        column["name"] for column in inspect(engine).get_columns("waha_media_jobs")
    }
    assert "waha_candidates" in inspect(engine).get_table_names()
    assert {
        "proposals",
        "model_call_traces",
        "evaluation_runs",
        "evaluation_cases",
        "approval_actions",
        "waha_attachments",
        "waha_media_jobs",
    } <= set(inspect(engine).get_table_names())
    assert {"provider_state", "provider_observed_at"} <= {
        item["name"] for item in inspect(engine).get_columns("waha_connections")
    }
    with engine.connect() as db:
        assert (
            db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0017_job_assignments"
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
        if existing_revision in {
            "0011_waha_multitype_sending",
            "0013_merge_media_send",
            "0014_merge_approval_send",
        }:
            assert db.execute(text("SELECT version,enabled FROM waha_send_permissions")).one() == (
                9,
                False,
            )
            assert (
                db.execute(text("SELECT request_key FROM waha_send_request_fences")).scalar_one()
                == "synthetic-cancelled-intent"
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
        legacy_cases = [
            ("cancel", "result_unknown", "processing", "MEDIA_CANCELLED"),
            ("pause", "result_unknown", "processing", "CONSENT_REVOKED"),
            ("expired", "result_unknown", "processing", "MEDIA_SOURCE_EXPIRED"),
            ("cancelled", "cancelled", "processing", None),
            ("erased", "result_unknown", "reconciling", "MEDIA_PROCESSING_RESULT_UNKNOWN"),
            ("lookup", "pending", "reconciling", None),
            ("fresh", "pending", "processing", None),
        ]
        for suffix, state, stage, error_code in legacy_cases:
            db.execute(
                tables["waha_media_jobs"]
                .insert()
                .values(
                    id="synthetic-" + suffix,
                    attachment_id=asset_id,
                    connection_id=connection_id,
                    request_key="synthetic-" + suffix,
                    command={"synthetic": True},
                    version=0,
                    context_version=0,
                    source_fingerprint="synthetic",
                    state=state,
                    stage=stage,
                    error_code=error_code,
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
        stopped = dict(db.execute(text("SELECT id,content_stop_reason FROM waha_media_jobs")).all())
        assert stopped[job_id] is None
        assert stopped["synthetic-fresh"] is None
        assert stopped["synthetic-cancel"] == "MEDIA_CANCELLED"
        assert stopped["synthetic-pause"] == "CONSENT_REVOKED"
        assert stopped["synthetic-expired"] == "MEDIA_SOURCE_EXPIRED"
        assert stopped["synthetic-cancelled"] == "MEDIA_CANCELLED"
        assert stopped["synthetic-erased"] == "MEDIA_LEGACY_REVIEW_REQUIRED"
        assert stopped["synthetic-lookup"] == "MEDIA_LEGACY_REVIEW_REQUIRED"
    engine.dispose()


@pytest.mark.parametrize(
    "existing_revision",
    [
        "0009_approval_actions",
        "0012_waha_media_stop",
        "0013_merge_approval_media",
        "0013_merge_media_send",
        "0014_merge_approval_send",
        "0015_d03_approval_heads",
    ],
)
def test_merge_revision_joins_approval_and_media_branches(migration_database, existing_revision):
    """A database on either parent branch upgrades to the single merge head and keeps its rows."""
    root = Path(__file__).resolve().parents[3]
    environment = {
        **os.environ,
        "DATABASE_URL": migration_database,
        "PYTHONPATH": str(root / "apps/backend/src"),
    }

    def migrate(revision):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "apps/backend/alembic.ini",
                "upgrade",
                revision,
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )

    migrate(existing_revision)
    engine = create_engine(migration_database)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO accounts (id,username,password_hash,active) "
                "VALUES ('synthetic-account','synthetic','synthetic',true)"
            )
        )
        db.execute(
            text(
                "INSERT INTO conversations (id,account_id,context_version,allowlisted) "
                "VALUES ('synthetic-conversation','synthetic-account',4,true)"
            )
        )
        db.execute(
            text(
                "INSERT INTO work_orders (id,account_id,data) "
                "VALUES ('synthetic-order','synthetic-account',:data)"
            ),
            {"data": json.dumps({"synthetic": True})},
        )
        if existing_revision in {
            "0009_approval_actions",
            "0013_merge_approval_media",
            "0014_merge_approval_send",
            "0015_d03_approval_heads",
        }:
            db.execute(
                text(
                    "INSERT INTO approval_actions "
                    "(id,account_id,work_order_id,conversation_id,trigger,active_key,reason,note,created_at,data) "
                    "VALUES ('synthetic-action','synthetic-account','synthetic-order',"
                    "'synthetic-conversation','schedule_conflict:synthetic','synthetic-order',"
                    "NULL,NULL,'2026-10-13 00:00:00',:data)"
                ),
                {"data": json.dumps({"state": "approved"})},
            )
    engine.dispose()
    migrate("head")

    engine = create_engine(migration_database)
    tables = set(inspect(engine).get_table_names())
    assert {"approval_actions", "waha_media_jobs"} <= tables
    assert "content_stop_reason" in {
        item["name"] for item in inspect(engine).get_columns("waha_media_jobs")
    }
    with engine.connect() as db:
        assert (
            db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0017_job_assignments"
        )
        assert db.execute(text("SELECT context_version FROM conversations")).scalar_one() == 4
        actions = db.execute(text("SELECT id,trigger,active_key FROM approval_actions")).all()
        if existing_revision in {
            "0009_approval_actions",
            "0013_merge_approval_media",
            "0014_merge_approval_send",
            "0015_d03_approval_heads",
        }:
            assert [tuple(row) for row in actions] == [
                ("synthetic-action", "schedule_conflict:synthetic", "synthetic-order")
            ]
            data = db.execute(text("SELECT data FROM approval_actions")).scalar_one()
            assert (json.loads(data) if isinstance(data, str) else data)["state"] == "approved"
        else:
            assert actions == []
    engine.dispose()
