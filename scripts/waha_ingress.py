"""Operator-only local provisioning/reconciliation. Never prints connector secrets."""

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import replace
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend/src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from gigmate.db import Account, ConversationRow, Session, WahaChat, WahaConnection  # noqa: E402
from gigmate.errors import BusinessError  # noqa: E402
from gigmate.waha_adapter import IDENTITY_NAMESPACE, AdapterError  # noqa: E402
from gigmate.waha_client import LocalWahaClient  # noqa: E402
from gigmate.waha_ingress import (  # noqa: E402
    WebhookBinding,
    purge_expired,
    reconcile_state,
    status_view,
)
from scripts.waha_local import load_config, private_directory  # noqa: E402


def provision(db, config, instance):
    if not config.consent_active:
        raise AdapterError("CONSENT_REVOKED")
    if not instance or len(instance) > 128:
        raise AdapterError("INVALID_INSTANCE")
    account = db.scalar(
        select(Account).where(Account.id == config.account_id).with_for_update()
    )
    if not account or not account.active:
        raise AdapterError("TRUSTED_ACCOUNT_REQUIRED")
    row = db.scalar(
        select(WahaConnection)
        .where(
            WahaConnection.instance_id == instance,
            WahaConnection.session_id == config.session,
        )
        .with_for_update()
    )
    if row and row.account_id != account.id:
        raise AdapterError("SESSION_OWNERSHIP_CONFLICT")
    if row is None:
        row = WahaConnection(
            id=str(
                uuid5(
                    IDENTITY_NAMESPACE,
                    json.dumps(
                        ["connection", instance, config.session], separators=(",", ":")
                    ),
                )
            ),
            account_id=account.id,
            instance_id=instance,
            session_id=config.session,
            enabled=True,
        )
        db.add(row)
        db.flush()
    row.enabled = True
    existing = {
        chat.provider_chat_id: chat
        for chat in db.scalars(select(WahaChat).where(WahaChat.connection_id == row.id))
    }
    for peer, chat in existing.items():
        conversation = db.get(ConversationRow, chat.conversation_id)
        if conversation.account_id != account.id:
            raise AdapterError("CONVERSATION_OWNERSHIP_CONFLICT")
        conversation.allowlisted = peer in config.allowlisted_chats
    for peer in sorted(config.allowlisted_chats - existing.keys()):
        if not 1 <= len(peer) <= 256 or any(ord(char) < 32 for char in peer):
            raise AdapterError("INVALID_CHAT_ID")
        conversation_id = str(
            uuid5(IDENTITY_NAMESPACE, json.dumps([row.id, peer], separators=(",", ":")))
        )
        db.add(
            ConversationRow(
                id=conversation_id,
                account_id=account.id,
                allowlisted=True,
                context_version=0,
            )
        )
        db.flush()
        db.add(
            WahaChat(
                id=str(uuid5(IDENTITY_NAMESPACE, "chat:" + conversation_id)),
                connection_id=row.id,
                provider_chat_id=peer,
                conversation_id=conversation_id,
            )
        )
    db.flush()
    return WebhookBinding(
        row.id, account.id, instance, config.session, config.webhook_secret
    )


def binding_path():
    return private_directory() / "ingress.json"


def save_binding(binding):
    target = binding_path()
    if target.is_symlink():
        raise AdapterError("PRIVATE_PATH_REQUIRED")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(asdict(binding), file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def local_binding(config):
    try:
        binding = WebhookBinding(
            **json.loads(binding_path().read_text(encoding="utf-8"))
        )
    except (OSError, TypeError, ValueError):
        raise AdapterError("PROVISION_FIRST") from None
    if (binding.account_id, binding.session_id, binding.secret) != (
        config.account_id,
        config.session,
        config.webhook_secret,
    ):
        raise AdapterError("LOCAL_BINDING_MISMATCH")
    return binding


def reconcile_once(config, binding, factory=Session):
    sampled_at = datetime.now(UTC)
    client = LocalWahaClient(config)
    try:
        state = client.status()["state"]
    finally:
        client.close()
    with factory.begin() as db:
        return reconcile_state(db, binding, state, now=sampled_at)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Private WAHA durable-ingress operations"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser(
        "provision",
        help="Sync the explicitly selected chat allowlist into the database",
    )
    setup.add_argument("--instance", default="local-waha-webjs")
    for name in ("status", "reconcile", "pause", "purge", "configure-live"):
        commands.add_parser(name)
    watch = commands.add_parser(
        "watch", help="Poll trusted connection state every 30 seconds"
    )
    watch.add_argument(
        "--container", action="store_true", help="Share WAHA network namespace"
    )
    args = parser.parse_args(argv)
    config = load_config()
    if args.command == "provision":
        with Session.begin() as db:
            binding = provision(db, config, args.instance)
        # An interrupted file write leaves ingress disabled, not a false acknowledgement.
        save_binding(binding)
        result = {
            "provisioned": True,
            "connection_id": binding.connection_id,
            "allowlisted_count": len(config.allowlisted_chats),
            "binding_file": "local-data/waha-a02/ingress.json",
        }
    else:
        binding = local_binding(config)
        if args.command == "watch":
            if args.container:
                config = replace(config, base_url="http://127.0.0.1:3000")
            while True:
                try:
                    result = reconcile_once(config, binding)
                    print(
                        json.dumps({"monitor": "reconciled", "state": result["state"]}),
                        flush=True,
                    )
                except (
                    AdapterError,
                    BusinessError,
                    SQLAlchemyError,
                    OSError,
                    ValueError,
                ):
                    print(json.dumps({"monitor": "unavailable"}), flush=True)
                time.sleep(30)
        if args.command == "configure-live":
            client = LocalWahaClient(config)
            try:
                result = client.configure_business_webhook(binding.connection_id)
            finally:
                client.close()
        elif args.command == "reconcile":
            result = reconcile_once(config, binding)
        else:
            with Session.begin() as db:
                row = db.scalar(
                    select(WahaConnection).where(
                        WahaConnection.id == binding.connection_id,
                        WahaConnection.account_id == binding.account_id,
                    )
                )
                if not row:
                    raise AdapterError("TRUSTED_ACCOUNT_REQUIRED")
                if args.command == "pause":
                    row.enabled = False
                    result = {"paused": True}
                elif args.command == "purge":
                    result = purge_expired(db, row.id)
                else:
                    result = status_view(db, row)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AdapterError, BusinessError) as exc:
        raise SystemExit(exc.code) from None
    except (SQLAlchemyError, OSError, ValueError):
        raise SystemExit("LOCAL_INGRESS_OPERATION_FAILED") from None
