"""Operator-only local provisioning/reconciliation. Never prints connector secrets."""

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend/src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from gigmate.db import (  # noqa: E402
    Account,
    ConversationRow,
    Session,
    WahaChat,
    WahaConnection,
    WahaRecoveryIssue,
)  # noqa: E402
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
from scripts.waha_container_config import sync_private_config  # noqa: E402
from gigmate.waha_recovery import (  # noqa: E402
    observe_pipeline,
    acknowledge_issue,
    issue_view,
    record_database_gap,
)  # noqa: E402
import httpx  # noqa: E402


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
    row.control_version += 1
    existing = {
        chat.provider_chat_id: chat
        for chat in db.scalars(select(WahaChat).where(WahaChat.connection_id == row.id))
    }
    for peer, chat in existing.items():
        conversation = db.get(ConversationRow, chat.conversation_id)
        if conversation.account_id != account.id:
            raise AdapterError("CONVERSATION_OWNERSHIP_CONFLICT")
        allowed = peer in config.allowlisted_chats
        if conversation.allowlisted != allowed:
            conversation.allowlisted = allowed
            conversation.context_version += 1
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
    private = private_directory()
    path = private / "bindings" / "ingress.json"
    if not path.resolve().is_relative_to(private.resolve()):
        raise AdapterError("PRIVATE_PATH_REQUIRED")
    return path


def save_binding(binding):
    target = binding_path()
    if target.is_symlink():
        raise AdapterError("PRIVATE_PATH_REQUIRED")
    target.parent.mkdir(parents=True, exist_ok=True)
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
        path = binding_path()
        if not path.exists():
            path = (
                private_directory() / "ingress.json"
            )  # Previous local setup, read-only migration fallback.
        binding = WebhookBinding(**json.loads(path.read_text(encoding="utf-8")))
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


def monitor_once(
    config,
    binding,
    *,
    api_url="http://127.0.0.1:18702",
    factory=Session,
    container=False,
):
    sampled_at = datetime.now(UTC)
    # Only fixed local service URLs are used; never accept a remote user-supplied URL.
    if api_url not in {"http://127.0.0.1:18702", "http://ingress:8000"}:
        raise AdapterError("LOCAL_API_REQUIRED")
    try:
        with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as http:
            response = http.get(api_url + "/health")
            api_ok = (
                response.status_code == 200 and response.json().get("status") == "ok"
            )
    except (httpx.HTTPError, ValueError, AttributeError):
        api_ok = False
    client = (
        LocalWahaClient(config, docker_service=True)
        if container
        else LocalWahaClient(config)
    )
    state = None
    try:
        state = client.status()["state"]
    except AdapterError:
        pass
    finally:
        client.close()
    with factory.begin() as db:
        observe_pipeline(
            db, binding, api_ok=api_ok, provider_ok=state == "WORKING", now=sampled_at
        )
        if state is not None:
            connection = db.get(WahaConnection, binding.connection_id)
            if connection.enabled:
                reconcile_state(db, binding, state, now=sampled_at)
        return status_view(db, db.get(WahaConnection, binding.connection_id))


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
    for name in (
        "status",
        "reconcile",
        "pause",
        "purge",
        "configure-live",
        "issues",
        "diagnose",
        "migrate-binding",
        "sync-container-config",
    ):
        commands.add_parser(name)
    review = commands.add_parser(
        "ack-issue", help="Record manual review; never imports messages"
    )
    review.add_argument("--id", required=True)
    review.add_argument(
        "--resolution", required=True, choices=["reviewed_no_import", "needs_followup"]
    )
    watch = commands.add_parser(
        "watch", help="Poll trusted connection state every 30 seconds"
    )
    watch.add_argument(
        "--container",
        action="store_true",
        help="Use fixed private Compose service endpoints",
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
            "binding_file": "local-data/waha-a02/bindings/ingress.json",
        }
    else:
        binding = local_binding(config)
        if args.command == "watch":
            pending_database_at = None
            while True:
                try:
                    result = monitor_once(
                        config,
                        binding,
                        api_url="http://ingress:8000"
                        if args.container
                        else "http://127.0.0.1:18702",
                        container=args.container,
                    )
                    if pending_database_at:
                        with Session.begin() as db:
                            record_database_gap(db, binding, pending_database_at)
                        pending_database_at = None
                        result["review_required"] = True
                    print(
                        json.dumps(
                            {
                                "monitor": "reconciled",
                                "state": result["state"],
                                "pipeline_ready": result["pipeline_ready"],
                                "review_required": result["review_required"],
                            }
                        ),
                        flush=True,
                    )
                except SQLAlchemyError:
                    pending_database_at = pending_database_at or datetime.now(UTC)
                    print(
                        json.dumps(
                            {"monitor": "unavailable", "code": "DATABASE_UNAVAILABLE"}
                        ),
                        flush=True,
                    )
                except (
                    AdapterError,
                    BusinessError,
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
        elif args.command == "diagnose":
            result = monitor_once(config, binding)
        elif args.command == "ack-issue":
            with Session.begin() as db:
                result = acknowledge_issue(db, binding, args.id, args.resolution)
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
                    row.control_version += 1
                    result = {"paused": True}
                elif args.command == "migrate-binding":
                    save_binding(binding)
                    result = {
                        "binding_migrated": True,
                        "binding_file": "local-data/waha-a02/bindings/ingress.json",
                    }
                elif args.command == "purge":
                    result = purge_expired(db, row.id)
                elif args.command == "issues":
                    result = {
                        "issues": [
                            issue_view(issue)
                            for issue in db.scalars(
                                select(WahaRecoveryIssue)
                                .where(WahaRecoveryIssue.connection_id == row.id)
                                .order_by(WahaRecoveryIssue.started_at)
                            )
                        ]
                    }
                elif args.command == "sync-container-config":
                    try:
                        result = sync_private_config(config, binding)
                    except RuntimeError:
                        raise AdapterError("CONTAINER_CONFIG_SYNC_FAILED") from None
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
