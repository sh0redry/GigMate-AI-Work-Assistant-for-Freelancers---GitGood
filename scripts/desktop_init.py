"""Desktop-only fresh account provisioning. Receives secrets on stdin, never logs them."""

import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    settings = json.load(sys.stdin)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "apps/backend/alembic.ini",
            "upgrade",
            "head",
        ],
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("DESKTOP_DATABASE_MIGRATION_FAILED")
    from gigmate.db import Account, Session, WahaConnection
    from gigmate.identity import password_hash

    account_id = "00000000-0000-4000-8000-000000000001"
    with Session.begin() as db:
        account = db.get(Account, account_id)
        if account is None:
            password = settings.get("password")
            if not isinstance(password, str) or not 12 <= len(password) <= 128:
                raise RuntimeError("DESKTOP_INITIAL_PASSWORD_REQUIRED")
            db.add(
                Account(
                    id=account_id,
                    username=settings["username"],
                    password_hash=password_hash(password),
                    active=True,
                )
            )
            db.flush()
        if db.get(WahaConnection, settings["connectionId"]) is None:
            db.add(
                WahaConnection(
                    id=settings["connectionId"],
                    account_id=account_id,
                    instance_id="desktop-waha-webjs",
                    session_id="default",
                    enabled=True,
                )
            )
    root = Path("/run/desktop-config")
    root.mkdir(parents=True, exist_ok=True)
    model_root = Path("/run/desktop-model")
    model_root.mkdir(parents=True, exist_ok=True)
    config = {
        "base_url": "http://127.0.0.1:18700",
        "account_id": account_id,
        "session": "default",
        "api_key": settings["wahaKey"],
        "webhook_secret": settings["webhookSecret"],
        "allowlisted_chats": [],
        "consent_active": True,
    }
    binding = {
        "connection_id": settings["connectionId"],
        "account_id": account_id,
        "instance_id": "desktop-waha-webjs",
        "session_id": "default",
        "secret": settings["webhookSecret"],
    }
    for relative, value in (
        ("config.json", config),
        ("bindings/ingress.json", binding),
        ("ingress.json", binding),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(value if isinstance(value, str) else json.dumps(value))
    # Upgrade old desktop profiles without leaving a readable model key in the
    # monitor's configuration volume. Only the initializer/API/worker mount this.
    model_file = model_root / "model.key"
    fd = os.open(model_file, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(settings.get("modelKey", ""))
    (root / "model.key").unlink(missing_ok=True)
    print("DESKTOP_ACCOUNT_AND_PRIVATE_CONFIG_READY")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Schema errors can contain business values; Docker/operator logs must not.
        print("DESKTOP_INITIALIZATION_FAILED", file=sys.stderr)
        raise SystemExit(1) from None
