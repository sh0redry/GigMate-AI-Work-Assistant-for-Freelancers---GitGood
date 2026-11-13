"""Additive migration on a disposable PostgreSQL schema, preserving old evidence."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from test_waha_migration import migration_database as migration_database


def test_assessment_upgrade_downgrade_preserves_existing_proposal(migration_database):
    if not migration_database.startswith("postgresql"):
        pytest.skip("PostgreSQL migration proof requires the isolated PostgreSQL fixture")
    root = Path(__file__).resolve().parents[3]
    environment = {
        **os.environ,
        "DATABASE_URL": migration_database,
        "PYTHONPATH": str(root / "apps/backend/src"),
    }

    def migrate(command, target=None):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "apps/backend/alembic.ini",
                command,
                *([target] if target else []),
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "Isolated clarification migration failed"

    migrate("upgrade", "0023_agent_drafts")
    engine = create_engine(migration_database)
    account, conversation, event, proposal = [str(uuid4()) for _ in range(4)]
    original = {"synthetic": "existing proposal evidence"}
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO accounts (id,username,password_hash,active) VALUES (:id,'synthetic-migration','synthetic:hash',true)"
            ),
            {"id": account},
        )
        db.execute(
            text(
                "INSERT INTO conversations (id,account_id,context_version,allowlisted) VALUES (:id,:owner,1,true)"
            ),
            {"id": conversation, "owner": account},
        )
        db.execute(
            text(
                "INSERT INTO inbox (id,account_id,payload,digest,context_version,received_at) VALUES (:id,:owner,CAST('{}' AS JSON),'synthetic-digest',1,now())"
            ),
            {"id": event, "owner": account},
        )
        db.execute(
            text(
                "INSERT INTO proposals (id,account_id,conversation_id,event_id,assignment,context_version,proposal,changes,unresolved_questions,model_version,prompt_version,created_at) VALUES (:id,:owner,:conversation,:event,'needs_review',1,CAST(:evidence AS JSON),CAST('[]' AS JSON),CAST('[]' AS JSON),'synthetic:model','synthetic:prompt',now())"
            ),
            {
                "id": proposal,
                "owner": account,
                "conversation": conversation,
                "event": event,
                "evidence": json.dumps(original),
            },
        )
    migrate("upgrade", "head")
    with engine.connect() as db:
        row = db.execute(
            text("SELECT proposal,clarification FROM proposals WHERE id=:id"), {"id": proposal}
        ).one()
        assert row[0] == original and row[1] is None
        assert "clarification" in {c["name"] for c in inspect(db).get_columns("proposals")}
        assert (
            db.execute(
                text("SELECT consent_context_version FROM conversations WHERE id=:id"),
                {"id": conversation},
            ).scalar()
            == 1
        )
    migrate("check")
    migrate("downgrade", "0023_agent_drafts")
    with engine.connect() as db:
        assert (
            db.execute(
                text("SELECT proposal FROM proposals WHERE id=:id"), {"id": proposal}
            ).scalar()
            == original
        )
        assert "clarification" not in {c["name"] for c in inspect(db).get_columns("proposals")}
    migrate("upgrade", "head")
    migrate("check")
    engine.dispose()
