"""Single owned local WAHA session control. Durable intent, no blind remote retries."""

import hmac
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4, uuid5

from sqlalchemy import delete, select, text

from gigmate.db import (
    Account,
    ConversationRow,
    Session,
    WahaCandidate,
    WahaChat,
    WahaConnection,
    WahaControl,
)
from gigmate.errors import BusinessError
from gigmate.waha_adapter import IDENTITY_NAMESPACE, AdapterError
from gigmate.waha_client import LocalWahaClient, LocalWahaConfig
from gigmate.waha_ingress import configured_binding
from gigmate.waha_recovery import stamp


def fail(code, status=409):
    raise BusinessError(status, code, "WAHA setup requires correction or reconciliation")


def settings(connection):
    path = os.environ.get("WAHA_CONTROL_CONFIG")
    if not path:
        fail("WAHA_CONTROL_DISABLED", 503)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data["allowlisted_chats"] = frozenset(data.get("allowlisted_chats", []))
        config = LocalWahaConfig(**data)
        binding = configured_binding()
    except (OSError, TypeError, ValueError, AdapterError):
        fail("WAHA_CONTROL_CONFIG_INVALID", 503)
    if (
        binding.connection_id != connection.id
        or binding.account_id != connection.account_id
        or binding.instance_id != connection.instance_id
        or binding.session_id != connection.session_id
        or config.account_id != connection.account_id
        or config.session != connection.session_id
        or not hmac.compare_digest(config.webhook_secret, binding.secret)
        or not config.consent_active
    ):
        fail("WAHA_CONTROL_CONFIG_INVALID", 503)
    return config


def owned(db, account, identifier, *, lock=False):
    query = select(WahaConnection).where(
        WahaConnection.id == identifier, WahaConnection.account_id == account.id
    )
    if lock:
        query = query.with_for_update()
    row = db.scalar(query)
    if not row:
        fail("NOT_FOUND", 404)
    return row


def version(row, expected):
    if row.control_version != expected:
        fail("WAHA_SETUP_VERSION_CONFLICT")


def operation_view(op):
    return dict(
        id=op.id,
        connection_id=op.connection_id,
        action=op.action,
        state=op.state,
        control_version=op.version,
        error_code=op.error_code,
        provider_state=op.result.get("provider_state"),
        provider_observed_at=op.result.get("provider_observed_at"),
    )


def setup_view(db, row):
    active = db.scalar(select(WahaControl).where(WahaControl.active_key == row.id))
    latest = db.scalar(
        select(WahaControl)
        .where(WahaControl.connection_id == row.id, WahaControl.state == "succeeded")
        .order_by(WahaControl.created_at.desc())
    )
    try:
        settings(row)
        available = True
    except BusinessError:
        available = False
    result = latest.result if latest else {}
    last = db.scalar(
        select(WahaControl)
        .where(WahaControl.connection_id == row.id)
        .order_by(WahaControl.created_at.desc())
    )
    observed = result.get("provider_observed_at")
    stale = observed is None or datetime.now(UTC) - datetime.fromisoformat(
        observed.replace("Z", "+00:00")
    ) > timedelta(seconds=120)
    return dict(
        connection_id=row.id,
        control_version=row.control_version,
        enabled=row.enabled,
        available=available,
        provider_state=result.get("provider_state"),
        provider_observed_at=result.get("provider_observed_at"),
        active_operation_id=active.id if active else None,
        last_operation_id=last.id if last else None,
        provider_sample_stale=stale,
    )


def enqueue(db, row, command, key):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key):
        fail("INVALID_IDEMPOTENCY_KEY", 422)
    previous = db.scalar(
        select(WahaControl).where(
            WahaControl.connection_id == row.id, WahaControl.request_key == key
        )
    )
    if previous:
        if previous.action != command.action or previous.version != command.expected_version + 1:
            fail("IDEMPOTENCY_CONFLICT")
        return operation_view(previous)
    version(row, command.expected_version)
    settings(row)
    if not row.enabled and command.action != "inspect":
        fail("CONNECTOR_PAUSED", 403)
    if db.scalar(select(WahaControl.id).where(WahaControl.active_key == row.id)):
        fail("WAHA_OPERATION_NEEDS_RECONCILIATION")
    row.control_version += 1
    op = WahaControl(
        id=str(uuid4()),
        connection_id=row.id,
        account_id=row.account_id,
        request_key=key,
        action=command.action,
        version=row.control_version,
        state="pending",
        active_key=row.id,
        created_at=datetime.now(UTC),
        result={},
    )
    db.add(op)
    db.flush()
    return operation_view(op)


def pause_resume(db, row, command, enabled):
    version(row, command.expected_version)
    if enabled:
        settings(row)
    row.enabled = enabled
    row.control_version += 1
    if not enabled:
        for op in db.scalars(
            select(WahaControl).where(WahaControl.active_key == row.id).with_for_update()
        ):
            if op.state in {"pending", "checking"}:
                op.state, op.active_key = "cancelled", None
                op.error_code = "CONNECTOR_PAUSED"
    db.flush()
    return setup_view(db, row)


def choices(db, row):
    result = []
    selected_peers = set()
    now = datetime.now(UTC)
    candidates = list(
        db.scalars(
            select(WahaCandidate).where(
                WahaCandidate.connection_id == row.id, WahaCandidate.expires_at > now
            )
        )
    )
    labels = {item.provider_chat_id: item.label for item in candidates}
    for chat in db.scalars(select(WahaChat).where(WahaChat.connection_id == row.id)):
        conv = db.get(ConversationRow, chat.conversation_id)
        if conv.allowlisted:
            selected_peers.add(chat.provider_chat_id)
            result.append(
                dict(
                    id=chat.id,
                    label=labels.get(chat.provider_chat_id) or "Authorized conversation",
                    selected=True,
                    expires_at=None,
                )
            )
    for item in candidates:
        if item.provider_chat_id in selected_peers:
            continue
        result.append(
            dict(id=item.id, label=item.label, selected=False, expires_at=stamp(item.expires_at))
        )
    return result


def select_chats(db, row, command):
    version(row, command.expected_version)
    settings(row)
    if len(set(command.selected_ids)) != len(command.selected_ids):
        fail("DUPLICATE_CHAT_SELECTION", 422)
    now = datetime.now(UTC)
    existing = {
        item.id: item
        for item in db.scalars(select(WahaChat).where(WahaChat.connection_id == row.id))
    }
    candidates = {
        item.id: item
        for item in db.scalars(
            select(WahaCandidate).where(
                WahaCandidate.connection_id == row.id, WahaCandidate.expires_at > now
            )
        )
    }
    selected = set()
    for identifier in command.selected_ids:
        item = existing.get(identifier) or candidates.get(identifier)
        if not item:
            fail("CHAT_CHOICE_EXPIRED_OR_UNAVAILABLE", 422)
        selected.add(item.provider_chat_id)
    peers = {item.provider_chat_id: item for item in existing.values()}
    for peer, chat in peers.items():
        conv = db.get(ConversationRow, chat.conversation_id)
        if conv.account_id != row.account_id:
            fail("CONVERSATION_OWNERSHIP_CONFLICT", 403)
        allow = peer in selected
        if conv.allowlisted != allow:
            conv.allowlisted = allow
            conv.context_version += 1  # Old proposals remain stale even after reauthorization.
    for peer in selected - peers.keys():
        identifier = str(
            uuid5(IDENTITY_NAMESPACE, json.dumps([row.id, peer], separators=(",", ":")))
        )
        db.add(
            ConversationRow(
                id=identifier, account_id=row.account_id, allowlisted=True, context_version=0
            )
        )
        db.flush()
        db.add(
            WahaChat(
                id=str(uuid5(IDENTITY_NAMESPACE, "chat:" + identifier)),
                connection_id=row.id,
                provider_chat_id=peer,
                conversation_id=identifier,
            )
        )
    row.control_version += 1
    db.flush()
    return setup_view(db, row)


def reconcile(db, row, identifier, command):
    version(row, command.expected_version)
    op = db.scalar(
        select(WahaControl)
        .where(WahaControl.id == identifier, WahaControl.connection_id == row.id)
        .with_for_update()
    )
    if not op:
        fail("NOT_FOUND", 404)
    if op.state != "result_unknown":
        fail("WAHA_RECONCILIATION_NOT_REQUIRED")
    settings(row)
    op.state, op.error_code = "checking", None
    row.control_version += 1
    return operation_view(op)


def client_for(row):
    return LocalWahaClient(
        settings(row), docker_service=os.environ.get("WAHA_CONTROL_INTERNAL") == "true"
    )


def provider_action(client, binding, action, checking):
    if checking:
        if action in {"connect", "recover"}:
            result = client.inspect_business_session(binding.connection_id)
            if not result["business_webhook_matches"]:
                fail("WAHA_REMOTE_CONFIGURATION_UNCONFIRMED")
            if action == "recover" and result["state"] in {"FAILED", "STOPPED"}:
                fail("WAHA_RECOVERY_UNCONFIRMED")
            return result, []
        # Failed read-only discovery can be repeated under a new explicit request.
        if action == "discover":
            fail("WAHA_DISCOVERY_REISSUE_REQUIRED")
    if action == "connect":
        try:
            result = client.inspect_business_session(binding.connection_id)
        except AdapterError as exc:
            if exc.code != "WAHA_RESOURCE_NOT_FOUND":
                raise
            client.create_business_session(binding.connection_id)
            return client.inspect_business_session(binding.connection_id), []
        if not result["business_webhook_matches"]:
            # No implicit takeover of an existing probe/other callback.
            fail("WAHA_REMOTE_CONFIGURATION_UNCONFIRMED")
        return result, []
    if action == "recover":
        result = client.inspect_business_session(binding.connection_id)
        if not result["business_webhook_matches"]:
            fail("WAHA_REMOTE_CONFIGURATION_UNCONFIRMED")
        if result["state"] in {"FAILED", "STOPPED"}:
            client.restart_failed_session()
        return client.inspect_business_session(binding.connection_id), []
    if action == "discover":
        return client.status(), client.recent_chats(limit=100)
    return client.status(), []


def run_once(factory=Session, *, make_client=client_for):
    now = datetime.now(UTC)
    with factory.begin() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '3s'"))
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
        candidate = db.scalar(
            select(WahaControl)
            .where(WahaControl.active_key.is_not(None))
            .order_by(WahaControl.created_at)
            .limit(1)
        )
        if not candidate:
            return False
        account = db.scalar(
            select(Account).where(Account.id == candidate.account_id).with_for_update()
        )
        row = db.scalar(
            select(WahaConnection)
            .where(WahaConnection.id == candidate.connection_id)
            .with_for_update()
        )
        op = db.scalar(
            select(WahaControl)
            .where(WahaControl.id == candidate.id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if not op or op.active_key is None:
            return False
        if op.state == "running":
            if op.lease_until and op.lease_until.replace(tzinfo=UTC) <= now:
                op.state, op.error_code = "result_unknown", "WAHA_CONTROL_INTERRUPTED"
            return False
        if op.state == "result_unknown":
            return False
        if op.state == "pending" and op.created_at.replace(tzinfo=UTC) < now - timedelta(minutes=2):
            op.state, op.active_key, op.error_code = (
                "cancelled",
                None,
                "WAHA_CONTROL_REQUEST_EXPIRED",
            )
            return True
        checking = op.state == "checking"
        if (
            not account.active
            or (not row.enabled and op.action != "inspect" and not checking)
            or (not checking and row.control_version != op.version)
        ):
            op.state, op.active_key, op.error_code = "cancelled", None, "WAHA_SETUP_CHANGED"
            return True
        token = str(uuid4())
        op.state, op.lease_until, op.lease_token = "running", now + timedelta(seconds=120), token
        identifier, account_id, connection_id, action = op.id, op.account_id, row.id, op.action
        # Resolve config only after ownership checks; commit the lease before network I/O.
        try:
            client = make_client(row)
            binding = configured_binding()
        except (BusinessError, AdapterError):
            op.state, op.active_key, op.error_code = "failed", None, "WAHA_CONTROL_CONFIG_INVALID"
            return True
    result, discovered, error = {}, [], None
    try:
        observed, discovered = provider_action(client, binding, action, checking)
        result = {
            "provider_state": observed["state"],
            "provider_observed_at": stamp(datetime.now(UTC)),
        }
    except (AdapterError, BusinessError) as exc:
        error = exc.code
    except Exception:
        error = "WAHA_CONTROL_FAILED"
    finally:
        client.close()
    with factory.begin() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '3s'"))
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
        db.scalar(select(Account).where(Account.id == account_id).with_for_update())
        row = db.scalar(
            select(WahaConnection).where(WahaConnection.id == connection_id).with_for_update()
        )
        op = db.get(WahaControl, identifier)
        if op.state != "running" or op.lease_token != token:
            return True  # An expired owner must not finalize a later reconciliation.
        if error:
            op.state = "result_unknown" if action in {"connect", "recover"} else "failed"
            op.error_code = error
        elif not checking and row.control_version != op.version:
            op.state, op.error_code = "result_unknown", "WAHA_SETUP_CHANGED"
        else:
            op.state, op.result, op.error_code = "succeeded", result, None
            if action == "discover":
                db.execute(delete(WahaCandidate).where(WahaCandidate.connection_id == row.id))
                for chat in discovered:
                    db.add(
                        WahaCandidate(
                            id=str(uuid4()),
                            connection_id=row.id,
                            provider_chat_id=chat["id"],
                            label=chat["name"],
                            expires_at=datetime.now(UTC) + timedelta(minutes=10),
                        )
                    )
        if op.state != "result_unknown":
            op.active_key = None
        op.lease_until = None
        op.lease_token = None
    return True
