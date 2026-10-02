"""Offline A-01 normalization. No HTTP, database, credentials or execution.

The caller must authenticate the source and resolve ownership/message revisions
before calling this boundary. Synthetic tests cannot establish live capability.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from uuid import UUID, uuid5

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[4]
IDENTITY_NAMESPACE = UUID("fdb1ce79-d372-48e3-b04a-60ef8c1f2687")
PROFILE = "synthetic_waha_a01_v1"
EVENT_TYPES = {
    "message": "message.created",
    "message.any": "message.created",
    "message.edited": "message.edited",
    "message.revoked": "message.revoked",
    "message.ack": "message.ack",
    "session.status": "session.status",
}
SESSION_STATES = {
    "WORKING": "connected",
    "STARTING": "connecting",
    "SCAN_QR_CODE": "connecting",
    "PASSKEY_REQUIRED": "connecting",
    "PASSKEY_CONFIRMATION_REQUIRED": "connecting",
    "STOPPED": "disconnected",
    "FAILED": "failed",
}
# PENDING is not proof of remote submission; ERROR cannot fit a success state.
ACK_STATES = {0: "unknown", 1: "sent", 2: "delivered", 3: "read", 4: "read"}
ACK_NAMES = {-1: "ERROR", 0: "PENDING", 1: "SERVER", 2: "DEVICE", 3: "READ", 4: "PLAYED"}


class AdapterError(ValueError):
    """Stable safe code only; never embed raw provider content in exceptions."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedMessage:
    """Trusted server-side lookup, not webhook/body-supplied permissions.

    provider_reference matches the raw target reference; provider_message_id is
    the canonical original provider message identity. Revision comes from the
    durable resolver, not receipt order. This module never allocates revisions.
    """

    conversation_id: str
    provider_chat_id: str
    provider_reference: str
    provider_message_id: str
    message_id: str
    revision: int
    allowlisted: bool
    source: str


@dataclass(frozen=True)
class NormalizationContext:
    account_id: str
    instance_id: str
    session_id: str
    source_verified: bool
    consent_active: bool
    message: ResolvedMessage | None = None


def _object(value):
    if not isinstance(value, dict):
        raise AdapterError("INVALID_PROVIDER_SHAPE")
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise AdapterError("INVALID_PROVIDER_SHAPE")
    return value


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise AdapterError("INVALID_TRUSTED_MAPPING") from None
    return value


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AdapterError("INVALID_TIMESTAMP")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _occurred_at(value):
    # The tested profile uses envelope milliseconds, not payload seconds.
    if type(value) is not int or value < 0:
        raise AdapterError("INVALID_TIMESTAMP")
    try:
        return _utc(datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=value))
    except (OverflowError, ValueError):
        raise AdapterError("INVALID_TIMESTAMP") from None


@cache
def _validator():
    registry = Registry()
    for relative in ("domain/models.schema.json", "events/message-event.schema.json"):
        path = ROOT / "contracts" / relative
        registry = registry.with_resource(
            path.as_uri(), Resource.from_contents(json.loads(path.read_text(encoding="utf-8")))
        )
    return Draft202012Validator(
        {"$ref": (ROOT / "contracts/events/message-event.schema.json").as_uri()},
        registry=registry,
        format_checker=FormatChecker(),
    )


def validate_event(event: dict) -> None:
    """Read the existing wire schema; report no private validation details."""
    if not _validator().is_valid(event):
        raise AdapterError("NORMALIZED_EVENT_INVALID")


def semantic_digest(event: dict) -> str:
    """Receipt time is transport metadata, not redelivery conflict evidence.

    This helper does not replace the existing inbox digest or persist dedup state.
    """
    validate_event(event)
    projection = {key: value for key, value in event.items() if key != "received_at"}
    encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _message_payload(event_type, payload, context):
    message = context.message
    if not isinstance(message, ResolvedMessage):
        raise AdapterError("MESSAGE_MAPPING_REQUIRED")
    if message.allowlisted is not True:
        raise AdapterError("CONVERSATION_NOT_ALLOWED")
    _uuid(message.conversation_id)
    _uuid(message.message_id)
    if type(message.revision) is not int or message.revision < 1:
        raise AdapterError("INVALID_TRUSTED_MAPPING")
    for value in (
        message.provider_chat_id,
        message.provider_reference,
        message.provider_message_id,
    ):
        _text(value)
    if not isinstance(message.source, str) or message.source not in {"app", "api"}:
        raise AdapterError("SOURCE_MAPPING_REQUIRED")

    # Edit/revoke action IDs may differ from the original message's identity.
    if event_type == "message.revoked":
        reference = _text(payload.get("revokedMessageId"))
        details = _object(payload.get("after"))
    else:
        details = payload
        reference = _text(
            payload.get("editedMessageId") if event_type == "message.edited" else payload.get("id")
        )
    if reference != message.provider_reference:
        raise AdapterError("MESSAGE_MAPPING_MISMATCH")
    if type(details.get("fromMe")) is not bool:
        raise AdapterError("INVALID_PROVIDER_SHAPE")
    outgoing = details["fromMe"]
    # The minimum ACK profile may put the peer in `from` without `to`.
    peer = details.get("to") if outgoing else details.get("from")
    if outgoing and event_type == "message.ack" and peer is None:
        peer = details.get("from")
    if _text(peer) != message.provider_chat_id:
        raise AdapterError("CONVERSATION_MAPPING_MISMATCH")
    if message.source == "api" and not outgoing:
        raise AdapterError("SOURCE_MAPPING_MISMATCH")
    if event_type == "message.created" and message.revision != 1:
        raise AdapterError("VERSION_CONFLICT")
    if event_type in {"message.edited", "message.revoked"} and message.revision < 2:
        raise AdapterError("VERSION_CONFLICT")

    result = {"message_id": message.message_id}
    if event_type in {"message.created", "message.edited"}:
        # Missing media classification is not treated as a text-only message.
        if type(details.get("hasMedia")) is not bool:
            raise AdapterError("INVALID_PROVIDER_SHAPE")
        if details["hasMedia"]:
            raise AdapterError("UNSUPPORTED_MEDIA")
        result["text"] = _text(details.get("body"))
    elif event_type == "message.ack":
        ack = payload.get("ack")
        if type(ack) is not int or ack not in ACK_NAMES:
            raise AdapterError("UNSUPPORTED_ACK")
        if "ackName" in payload and payload["ackName"] != ACK_NAMES[ack]:
            raise AdapterError("ACK_MAPPING_MISMATCH")
        if ack == -1:
            raise AdapterError("ACK_ERROR_NEEDS_RECONCILIATION")
        result["delivery_status"] = ACK_STATES[ack]
    return {
        "conversation_id": message.conversation_id,
        "provider_message_id": message.provider_message_id,
        "direction": "outgoing" if outgoing else "incoming",
        "source": message.source,
        "message_revision": message.revision,
        "payload": result,
    }


def normalize_event(raw: dict, context: NormalizationContext, *, received_at: datetime) -> dict:
    """Normalize the explicit A-01 profile after trusted source/ownership checks.

    No provider-ID fallback, automatic revision allocation, data persistence,
    model invocation or external action is performed here.
    """
    if not isinstance(context, NormalizationContext):
        raise AdapterError("INVALID_TRUSTED_MAPPING")
    if context.source_verified is not True:
        raise AdapterError("SOURCE_UNVERIFIED")
    if context.consent_active is not True:
        raise AdapterError("CONSENT_REVOKED")
    _uuid(context.account_id)
    _text(context.instance_id)
    _text(context.session_id)
    raw = _object(raw)
    if raw.get("session") != context.session_id:
        raise AdapterError("SESSION_MAPPING_MISMATCH")
    raw_type = _text(raw.get("event"))
    if raw_type not in EVENT_TYPES:
        raise AdapterError("UNSUPPORTED_EVENT")
    event_type = EVENT_TYPES[raw_type]
    provider_event_id = raw.get("id")
    if not isinstance(provider_event_id, str) or not provider_event_id.strip():
        raise AdapterError("EVENT_ID_REQUIRED")
    payload = _object(raw.get("payload"))
    scope = [context.instance_id, context.account_id, context.session_id, provider_event_id]
    event = {
        "schema_version": "0.1.0",
        "event_id": str(uuid5(IDENTITY_NAMESPACE, json.dumps(scope, separators=(",", ":")))),
        "event_type": event_type,
        "account_id": context.account_id,
        "connector": "waha",
        "session_id": context.session_id,
        "occurred_at": _occurred_at(raw.get("timestamp")),
        "received_at": _utc(received_at),
    }
    if event_type == "session.status":
        if payload.get("name") != context.session_id:
            raise AdapterError("SESSION_MAPPING_MISMATCH")
        state = payload.get("status")
        if not isinstance(state, str) or state not in SESSION_STATES:
            raise AdapterError("UNSUPPORTED_SESSION_STATE")
        event.update(
            conversation_id=None,
            provider_message_id=None,
            direction=None,
            source="app",
            message_revision=None,
            payload={"status": SESSION_STATES[state]},
        )
    else:
        event.update(_message_payload(event_type, payload, context))
        if "source" in raw and raw["source"] != event["source"]:
            raise AdapterError("SOURCE_MAPPING_MISMATCH")
    validate_event(event)
    return event
