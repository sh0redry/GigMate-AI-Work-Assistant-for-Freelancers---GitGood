"""Trusted, transactional WAHA reception. Caller authenticates before entry.

Provider timestamps order mutations conservatively; gaps cannot be inferred.
No history import, model call, send or claim of external exactly-once delivery.
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import delete, func, select, text

from gigmate.contracts import ConnectorStatus
from gigmate.db import (
    Account,
    ConversationRow,
    Inbox,
    Job,
    MessageRow,
    WahaChat,
    WahaConnection,
    WahaMessage,
)
from gigmate.errors import BusinessError
from gigmate.messaging import ingest
from gigmate.waha_adapter import (
    EVENT_TYPES,
    IDENTITY_NAMESPACE,
    SESSION_STATES,
    AdapterError,
    NormalizationContext,
    ResolvedMessage,
    normalize_event,
    semantic_digest,
)
from gigmate.waha_recovery import operational_view


@dataclass(frozen=True)
class WebhookBinding:
    connection_id: str
    account_id: str
    instance_id: str
    session_id: str
    secret: str = field(repr=False)


def configured_binding():
    """Read private operator configuration, never derive ownership from the body."""
    path = os.environ.get("WAHA_CONNECTOR_CONFIG")
    if not path:
        raise BusinessError(503, "CONNECTOR_DISABLED", "WAHA ingress is not configured")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        result = WebhookBinding(**data)
        UUID(result.connection_id)
        UUID(result.account_id)
        if any(
            not isinstance(v, str) or not 1 <= len(v) <= 128
            for v in (result.instance_id, result.session_id)
        ):
            raise ValueError
        if not isinstance(result.secret, str) or len(result.secret) < 32:
            raise ValueError
        return result
    except (OSError, ValueError, TypeError, KeyError):
        raise BusinessError(
            503, "CONNECTOR_CONFIG_INVALID", "Connector configuration is invalid"
        ) from None


def binding_for(connection_id):
    result = configured_binding()
    if result.connection_id != connection_id:
        raise BusinessError(404, "NOT_FOUND", "Connector not found")
    return result


def fail(code, status=409):
    raise BusinessError(status, code, "WAHA event requires rejection or reconciliation")


def bounded_id(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
        fail("INVALID_PROVIDER_SHAPE", 422)
    return value


def event_identity(binding, raw):
    reference = bounded_id(raw.get("id"))
    return str(
        uuid5(
            IDENTITY_NAMESPACE,
            json.dumps(
                [binding.instance_id, binding.account_id, binding.session_id, reference],
                separators=(",", ":"),
            ),
        )
    )


def stanza_id(reference, peer, outgoing):
    """Pinned serialized ID grammar; never infer or convert a chat identity."""
    prefix = f"{str(outgoing).lower()}_{peer}_"
    if not reference.startswith(prefix):
        return None
    tail = reference[len(prefix) :]
    if not re.fullmatch(r"[A-Za-z0-9]+(?:_[^_]+)?", tail):
        return None
    return tail.split("_", 1)[0]


def receive(db, binding, raw, *, now=None):
    now = now or datetime.now(UTC)
    if db.bind.dialect.name == "postgresql":
        # Bounded waits prevent an abandoned transaction exhausting the HTTP worker pool.
        db.execute(text("SET LOCAL lock_timeout = '3s'"))
        db.execute(text("SET LOCAL statement_timeout = '5s'"))
    # Account first matches business commands and worker lock order.
    account = db.scalar(select(Account).where(Account.id == binding.account_id).with_for_update())
    connection = db.scalar(
        select(WahaConnection).where(WahaConnection.id == binding.connection_id).with_for_update()
    )
    if (
        not connection
        or not account
        or (connection.account_id, connection.instance_id, connection.session_id)
        != (binding.account_id, binding.instance_id, binding.session_id)
    ):
        fail("SESSION_MAPPING_MISMATCH", 403)
    if not account.active or not connection.enabled:
        fail("CONSENT_REVOKED", 403)
    if not isinstance(raw, dict) or raw.get("session") != binding.session_id:
        fail("SESSION_MAPPING_MISMATCH", 403)
    payload, kind, timestamp = raw.get("payload"), raw.get("event"), raw.get("timestamp")
    if not isinstance(payload, dict) or not isinstance(kind, str) or kind not in EVENT_TYPES:
        fail("INVALID_PROVIDER_SHAPE", 422)
    if (
        type(timestamp) is not int
        or timestamp < 0
        or timestamp > int((now + timedelta(minutes=5)).timestamp() * 1000)
    ):
        fail("INVALID_TIMESTAMP", 422)
    if timestamp < int((now - timedelta(days=30)).timestamp() * 1000):
        fail("EVENT_RETENTION_EXPIRED", 422)
    context = NormalizationContext(
        binding.account_id, binding.instance_id, binding.session_id, True, True
    )
    identity = event_identity(binding, raw)
    previous = db.get(Inbox, identity)
    mapping, conversation = None, None
    event_type = EVENT_TYPES[kind]
    if event_type != "session.status":
        details = payload.get("after") if event_type == "message.revoked" else payload
        if not isinstance(details, dict) or type(details.get("fromMe")) is not bool:
            fail("INVALID_PROVIDER_SHAPE", 422)
        peer = details.get("to") if details["fromMe"] else details.get("from")
        if event_type == "message.ack" and peer is None:
            peer = details.get("from")
        peer = bounded_id(peer)
        chat = db.scalar(
            select(WahaChat).where(
                WahaChat.connection_id == connection.id, WahaChat.provider_chat_id == peer
            )
        )
        if not chat:
            fail("CONVERSATION_NOT_ALLOWED", 403)
        conversation = db.scalar(
            select(ConversationRow)
            .where(
                ConversationRow.id == chat.conversation_id,
                ConversationRow.account_id == account.id,
            )
            .with_for_update()
        )
        if not conversation or not conversation.allowlisted:
            fail("CONVERSATION_NOT_ALLOWED", 403)
        target = bounded_id(
            payload.get(
                "editedMessageId"
                if event_type == "message.edited"
                else "revokedMessageId"
                if event_type == "message.revoked"
                else "id"
            )
        )
        mapping = db.scalar(
            select(WahaMessage)
            .where(WahaMessage.chat_id == chat.id, WahaMessage.provider_message_id == target)
            .with_for_update()
        )
        if mapping is None and event_type in {"message.edited", "message.revoked"}:
            candidates = list(
                db.scalars(
                    select(WahaMessage)
                    .join(
                        MessageRow,
                        (MessageRow.id == WahaMessage.message_id)
                        & (MessageRow.revision == WahaMessage.revision),
                    )
                    .where(
                        WahaMessage.chat_id == chat.id,
                        WahaMessage.stanza_id == target,
                        MessageRow.account_id == account.id,
                        MessageRow.conversation_id == conversation.id,
                        MessageRow.data["direction"].as_string()
                        == ("outgoing" if details["fromMe"] else "incoming"),
                        MessageRow.data["source"].as_string() == "app",
                    )
                    .with_for_update(of=WahaMessage)
                )
            )
            if len(candidates) > 1:
                fail("SOURCE_MESSAGE_AMBIGUOUS")
            mapping = candidates[0] if candidates else None
        if not mapping and event_type != "message.created":
            fail("SOURCE_MESSAGE_UNRESOLVED")
        if mapping:
            original = db.get(MessageRow, (mapping.message_id, mapping.revision))
            direction = "outgoing" if details["fromMe"] else "incoming"
            if (
                not original
                or original.data["direction"] != direction
                or original.data["source"] != "app"
            ):
                fail("SOURCE_MAPPING_MISMATCH")
        revision = 1 if event_type == "message.created" else mapping.revision
        if previous:
            if previous.account_id != account.id or previous.connection_id != connection.id:
                fail("IDEMPOTENCY_CONFLICT")
            revision = previous.payload.get("message_revision")
        elif event_type in {"message.edited", "message.revoked"}:
            if timestamp <= mapping.occurred_timestamp:
                fail("SOURCE_ORDER_NEEDS_RECONCILIATION")
            latest = db.get(MessageRow, (mapping.message_id, mapping.revision))
            if latest.data["revoked"]:
                fail("SOURCE_REVOKED")
            revision += 1
        message_id = mapping.message_id if mapping else str(uuid4())
        context = NormalizationContext(
            binding.account_id,
            binding.instance_id,
            binding.session_id,
            True,
            True,
            ResolvedMessage(
                conversation.id,
                peer,
                target,
                mapping.provider_message_id if mapping else target,
                message_id,
                revision,
                True,
                "app",
            ),
        )
        if event_type in {"message.created", "message.edited"} and (
            not isinstance(details.get("body"), str) or len(details["body"]) > 8000
        ):
            fail("TEXT_LIMIT_EXCEEDED", 422)
    try:
        event = normalize_event(raw, context, received_at=now)
    except AdapterError as exc:
        fail(exc.code, 422)
    digest = semantic_digest(event)
    if previous:
        if (
            previous.account_id != account.id
            or previous.connection_id != connection.id
            or previous.digest != digest
        ):
            fail("IDEMPOTENCY_CONFLICT")
        connection.duplicates += 1
        return {
            "event_id": identity,
            "duplicate": True,
            "context_version": previous.context_version,
            "durable_acceptance": True,
        }
    duplicate, context_version = False, conversation.context_version if conversation else 0
    if event_type == "session.status":
        if connection.state_timestamp is None or timestamp > connection.state_timestamp:
            connection.state = event["payload"]["status"]
            connection.state_timestamp, connection.state_received_at = timestamp, now
        else:
            if (
                timestamp == connection.state_timestamp
                and connection.state != event["payload"]["status"]
            ):
                fail("STATE_ORDER_NEEDS_RECONCILIATION")
            connection.stale_events += 1
    elif event_type == "message.ack":
        # ACK never advances content/context or creates an extraction job.
        mapping.delivery_rank = max(mapping.delivery_rank, payload["ack"])
    else:
        result = ingest(db, account, event, trusted_waha=True)
        duplicate, context_version = result["duplicate"], result["context_version"]
        if not duplicate:
            if mapping is None:
                mapping = WahaMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    provider_message_id=target,
                    stanza_id=stanza_id(target, peer, details["fromMe"]),
                    message_id=message_id,
                    revision=revision,
                    occurred_timestamp=timestamp,
                    delivery_rank=0,
                )
                db.add(mapping)
            else:
                mapping.revision, mapping.occurred_timestamp = revision, timestamp
            connection.last_sync_at = now
    inbox = db.get(Inbox, identity)
    if not inbox:
        inbox = Inbox(
            id=identity,
            account_id=account.id,
            payload=event,
            digest=digest,
            received_at=now,
            context_version=context_version,
        )
        db.add(inbox)
    inbox.connection_id = connection.id
    connection.accepted += 1
    if duplicate:
        connection.duplicates += 1
    db.flush()
    return {
        "event_id": identity,
        "duplicate": duplicate,
        "context_version": context_version,
        "durable_acceptance": True,
    }


def utc(value):
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if value else None


def reconcile_state(db, binding, provider_state, *, now=None):
    now = now or datetime.now(UTC)
    account = db.scalar(select(Account).where(Account.id == binding.account_id).with_for_update())
    connection = db.scalar(
        select(WahaConnection).where(WahaConnection.id == binding.connection_id).with_for_update()
    )
    if not account or not account.active or not connection or not connection.enabled:
        fail("CONSENT_REVOKED", 403)
    if (connection.account_id, connection.instance_id, connection.session_id) != (
        binding.account_id,
        binding.instance_id,
        binding.session_id,
    ):
        fail("SESSION_MAPPING_MISMATCH", 403)
    if provider_state not in SESSION_STATES:
        fail("UNSUPPORTED_SESSION_STATE", 422)
    if connection.state_timestamp is not None and connection.state_timestamp > int(
        now.timestamp() * 1000
    ):
        # A callback accepted during the provider lookup must not be overwritten by that older sample.
        return status_view(db, connection)
    connection.state = SESSION_STATES[provider_state]
    connection.state_timestamp = int(now.timestamp() * 1000)
    connection.state_received_at = now
    db.flush()
    return status_view(db, connection, now=now)


def purge_expired(db, connection_id, *, now=None):
    """Remove content/jobs older than 30 days; retain IDs/revisions for reconciliation."""
    now = now or datetime.now(UTC)
    connection = db.get(WahaConnection, connection_id)
    if not connection:
        fail("NOT_FOUND", 404)
    db.scalar(select(Account).where(Account.id == connection.account_id).with_for_update())
    connection = db.scalar(
        select(WahaConnection).where(WahaConnection.id == connection_id).with_for_update()
    )
    cutoff = now - timedelta(days=30)
    old_events = select(Inbox.id).where(
        Inbox.connection_id == connection_id, Inbox.received_at < cutoff
    )
    jobs = db.execute(delete(Job).where(Job.event_id.in_(old_events))).rowcount
    events = db.execute(delete(Inbox).where(Inbox.id.in_(old_events))).rowcount
    message_ids = (
        select(WahaMessage.message_id).join(WahaChat).where(WahaChat.connection_id == connection_id)
    )
    scrubbed = 0
    for message in db.scalars(
        select(MessageRow).where(MessageRow.id.in_(message_ids)).with_for_update()
    ):
        if message.data["occurred_at"] < utc(cutoff) and message.data.get("text") is not None:
            message.data = {**message.data, "text": None}
            scrubbed += 1
    db.flush()
    return {"deleted_receipts": events, "deleted_jobs": jobs, "scrubbed_revisions": scrubbed}


def status_view(db, connection, *, now=None):
    now = now or datetime.now(UTC)
    observed = connection.state_received_at
    # A finite freshness window exposes uncertainty; it is not an uptime guarantee.
    stale = observed is None or (now - observed.replace(tzinfo=UTC)).total_seconds() > 120
    counts = dict(
        db.execute(
            select(Job.state, func.count(Job.id))
            .join(Inbox, Job.event_id == Inbox.id)
            .where(Inbox.connection_id == connection.id)
            .group_by(Job.state)
        ).all()
    )
    return ConnectorStatus(
        id=connection.id,
        connector="waha",
        state=connection.state,
        enabled=connection.enabled,
        live_connected=connection.enabled and connection.state == "connected" and not stale,
        stale=stale,
        observed_at=utc(observed),
        last_sync_at=utc(connection.last_sync_at),
        accepted=connection.accepted,
        duplicates=connection.duplicates,
        stale_events=connection.stale_events,
        pending_jobs=counts.get("pending", 0),
        processing_jobs=counts.get("processing", 0),
        failed_jobs=counts.get("failed", 0),
        **operational_view(db, connection, now=now),
    ).model_dump(mode="json")
