"""Opt-in D development bridge. Reuses unchanged A operations; never sends messages."""

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps/backend/src"))


def uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("INVALID_ID")
    return value


def write_record(path, value):
    if path.is_symlink():
        raise ValueError("PRIVATE_PATH_REQUIRED")
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        json.dump(value, file)
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def restart(client, connection_id, key):
    """Persist dispatch uncertainty across Vite/Python restarts; never auto-resend."""
    from gigmate.errors import BusinessError

    key = uuid(key)
    directory = ROOT / "local-data/d01-operations"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.resolve().is_relative_to(
        ROOT / "local-data"
    ):
        raise ValueError("PRIVATE_PATH_REQUIRED")
    path = directory / f"restart-{uuid(connection_id)}.json"
    if path.is_symlink():
        raise ValueError("PRIVATE_PATH_REQUIRED")
    previous = json.loads(path.read_text()) if path.exists() else None
    state = client.status()["state"]
    if previous and previous["state"] in {"submitting", "unknown"}:
        if state not in {"STARTING", "SCAN_QR_CODE", "WORKING"}:
            raise BusinessError(
                409, "WAHA_RESULT_UNKNOWN", "Reconcile before another restart"
            )
        previous["state"] = "submitted"
        write_record(path, previous)
    if previous and previous["key"] == key:
        return {"restart_requested": True, "duplicate": True}
    if state not in {"FAILED", "STOPPED"}:
        raise BusinessError(
            409, "WAHA_RECOVERY_NOT_REQUIRED", "Refresh the current session"
        )
    if (
        previous
        and (datetime.now(UTC) - datetime.fromisoformat(previous["at"])).total_seconds()
        < 30
    ):
        raise BusinessError(
            409, "LOCAL_RESTART_COOLDOWN", "Wait and refresh before restarting"
        )
    record = {
        "key": uuid(key),
        "state": "submitting",
        "at": datetime.now(UTC).isoformat(),
    }
    write_record(path, record)
    try:
        # This existing method checks FAILED/STOPPED again immediately before dispatch.
        client.restart_failed_session()
    except Exception:
        record["state"] = "unknown"
        write_record(path, record)
        raise BusinessError(
            409, "WAHA_RESULT_UNKNOWN", "Refresh; do not blindly resend"
        ) from None
    record["state"] = "submitted"
    write_record(path, record)
    return {"restart_requested": True, "duplicate": False}


def review(db, binding, issue_ids, confirmed):
    from sqlalchemy import select

    from gigmate.db import WahaRecoveryIssue
    from gigmate.errors import BusinessError
    from gigmate.waha_recovery import acknowledge_issue

    if (
        confirmed is not True
        or not isinstance(issue_ids, list)
        or not 1 <= len(issue_ids) <= 100
    ):
        raise BusinessError(
            422, "REVIEW_CONFIRMATION_REQUIRED", "Review the selected intervals"
        )
    ids = [uuid(value) for value in issue_ids]
    if len(set(ids)) != len(ids):
        raise BusinessError(422, "INVALID_REVIEW_SELECTION", "Duplicate issue")
    rows = list(
        db.scalars(
            select(WahaRecoveryIssue)
            .where(
                WahaRecoveryIssue.connection_id == binding.connection_id,
                WahaRecoveryIssue.id.in_(ids),
            )
            .order_by(WahaRecoveryIssue.id)
            .with_for_update()
        )
    )
    if len(rows) != len(ids):
        raise BusinessError(
            404, "NOT_FOUND", "Issue does not belong to this connection"
        )
    if any(row.recovered_at is None for row in rows):
        raise BusinessError(
            409, "COMPONENT_STILL_UNAVAILABLE", "Restore before clearing review"
        )
    for row in rows:
        acknowledge_issue(db, binding, row.id, "reviewed_no_import")
    return {"reviewed": len(rows)}


def perform(db, config, binding, connection_id, operation, payload):
    from gigmate.db import WahaConnection
    from gigmate.errors import BusinessError
    from gigmate.identity import authenticate
    from gigmate.waha_client import LocalWahaClient
    from sqlalchemy import select

    uuid(connection_id)
    if not isinstance(payload, dict):
        raise ValueError("INVALID_LOCAL_OPERATION")
    if binding.connection_id != connection_id:
        raise BusinessError(404, "LOCAL_BINDING_MISMATCH", "Unknown local connection")
    # The existing account lock serializes concurrent commands, including logout.
    account = authenticate(db, payload.get("token"), payload.get("csrf"), mutation=True)
    # A logout may have completed while waiting for the account lock. Re-read the
    # login under that lock rather than trusting the earlier identity-map entry.
    db.expire_all()
    account = authenticate(db, payload.get("token"), payload.get("csrf"), mutation=True)
    row = db.scalar(
        select(WahaConnection)
        .where(
            WahaConnection.id == connection_id,
            WahaConnection.account_id == account.id,
        )
        .with_for_update()
    )
    if not row or account.id != binding.account_id:
        raise BusinessError(404, "LOCAL_BINDING_MISMATCH", "Connection owner mismatch")
    if (row.instance_id, row.session_id) != (binding.instance_id, binding.session_id):
        raise BusinessError(
            403, "LOCAL_BINDING_MISMATCH", "Connection mapping mismatch"
        )
    if not row.enabled or not config.consent_active:
        raise BusinessError(403, "CONSENT_REVOKED", "Receiving permission is paused")
    if operation == "restart":
        client = LocalWahaClient(config)
        try:
            return restart(client, connection_id, payload.get("key"))
        finally:
            client.close()
    if operation == "review-issues":
        return review(db, binding, payload.get("issue_ids"), payload.get("confirmed"))
    raise BusinessError(404, "LOCAL_PAIRING_NOT_FOUND", "Unknown operation")


def main():
    # Do not accept credentials in argv or print private exception messages.
    from scripts.waha_team import PROFILE, environment

    if not PROFILE.exists():
        raise ValueError("LOCAL_CONFIG_INVALID_OR_MISSING")
    os.environ["DATABASE_URL"] = environment()["DATABASE_URL"]
    from gigmate.db import Session
    from scripts.waha_ingress import local_binding
    from scripts.waha_local import load_config

    connection_id, operation = sys.argv[1:]
    payload = json.loads(sys.stdin.read(8193))
    config = load_config()
    binding = local_binding(config)
    with Session.begin() as db:
        result = perform(db, config, binding, connection_id, operation, payload)
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except ImportError:
        print(
            json.dumps(
                {"error": {"code": "LOCAL_PAIRING_DEPENDENCIES_MISSING", "status": 503}}
            )
        )
        sys.exit(1)
    except Exception as error:
        code = getattr(error, "code", "LOCAL_PAIRING_UNAVAILABLE")
        status = getattr(error, "status", 503)
        if isinstance(error, (ValueError, KeyError, TypeError)):
            code, status = "INVALID_LOCAL_OPERATION", 422
        print(json.dumps({"error": {"code": code, "status": status}}))
        sys.exit(1)
