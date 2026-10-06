"""Local authenticated capability probe, deliberately not a business inbox.

Returns transport observation only. No content persistence, normalized events,
AI, tasks, approvals or sends. Volatile counters never imply durable acceptance.
"""

import hashlib
import hmac
import json
import re
from collections import OrderedDict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gigmate.waha_adapter import EVENT_TYPES, AdapterError
from gigmate.waha_client import LocalWahaConfig

MAX_BODY = 256 * 1024


def verify_hmac(body: bytes, signature: str | None, algorithm: str | None, secret: str):
    if (
        algorithm != "sha512"
        or not isinstance(signature, str)
        or not re.fullmatch(r"[0-9a-f]{128}", signature)
    ):
        raise AdapterError("WEBHOOK_AUTH_REJECTED")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise AdapterError("WEBHOOK_AUTH_REJECTED")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise AdapterError("INVALID_WEBHOOK_JSON")
        result[key] = value
    return result


def _non_json_constant(value):
    raise AdapterError("INVALID_WEBHOOK_JSON")


class ProbeObservations:
    def __init__(self):
        self.counts = {"observed": 0, "duplicate": 0, "identity_conflict": 0}
        self.identities = OrderedDict()
        self.latest = None

    def observe(self, raw: dict, config: LocalWahaConfig):
        event_type = raw.get("event")
        if not isinstance(event_type, str) or event_type not in EVENT_TYPES:
            raise AdapterError("UNSUPPORTED_EVENT")
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            raise AdapterError("INVALID_WEBHOOK_JSON")
        if event_type != "session.status":
            details = payload.get("after") if event_type == "message.revoked" else payload
            if not isinstance(details, dict) or type(details.get("fromMe")) is not bool:
                raise AdapterError("MESSAGE_MAPPING_REQUIRED")
            chat = details.get("to") if details["fromMe"] else details.get("from")
            if event_type == "message.ack" and chat is None:
                chat = details.get("from")
            if not isinstance(chat, str) or chat not in config.allowlisted_chats:
                raise AdapterError("CONVERSATION_NOT_ALLOWED")
        provider_id = raw.get("id")
        if not isinstance(provider_id, str) or not provider_id:
            raise AdapterError("EVENT_ID_REQUIRED")
        # Private content is not retained; stable hashes support redelivery comparison.
        identity = hmac.new(
            config.webhook_secret.encode(), provider_id.encode(), hashlib.sha256
        ).hexdigest()
        digest = hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        previous = self.identities.get(identity)
        if previous is not None and previous != digest:
            self.counts["identity_conflict"] += 1
            raise AdapterError("IDEMPOTENCY_CONFLICT")
        duplicate = previous is not None
        self.counts["duplicate" if duplicate else "observed"] += 1
        self.identities[identity] = digest
        self.identities.move_to_end(identity)
        if len(self.identities) > 100:
            self.identities.popitem(last=False)
        self.latest = {
            "event_type": EVENT_TYPES[event_type],
            "has_event_timestamp": type(raw.get("timestamp")) is int,
            "has_edit_target": isinstance(payload.get("editedMessageId"), str),
            "has_revoke_target": isinstance(payload.get("revokedMessageId"), str),
            "has_ack": type(payload.get("ack")) is int,
            "duplicate": duplicate,
        }
        return {"mode": "capability_probe", "durable_acceptance": False, "duplicate": duplicate}


def create_probe(config: LocalWahaConfig):
    app = FastAPI(
        title="Local WAHA capability probe", docs_url=None, redoc_url=None, openapi_url=None
    )
    observations = ProbeObservations()

    @app.exception_handler(AdapterError)
    async def error_handler(request: Request, exc: AdapterError):
        status = 422
        if exc.code == "WEBHOOK_AUTH_REJECTED":
            status = 401
        elif exc.code in {
            "CONSENT_REVOKED",
            "CONVERSATION_NOT_ALLOWED",
            "SESSION_MAPPING_MISMATCH",
        }:
            status = 403
        elif exc.code == "IDEMPOTENCY_CONFLICT":
            status = 409
        elif exc.code == "WEBHOOK_TOO_LARGE":
            status = 413
        return JSONResponse(
            status_code=status, content={"error": exc.code, "mode": "capability_probe"}
        )

    @app.get("/health")
    async def health():
        return {"mode": "capability_probe", "durable_acceptance": False}

    @app.get("/probe/observations")
    async def stats(request: Request):
        authorization = request.headers.get("Authorization", "")
        if not hmac.compare_digest(
            authorization.encode("utf-8"), ("Bearer " + config.api_key).encode("utf-8")
        ):
            raise AdapterError("WEBHOOK_AUTH_REJECTED")
        return {
            "mode": "capability_probe",
            "volatile": True,
            "counts": observations.counts,
            "latest": observations.latest,
        }

    @app.post("/probe/webhook")
    async def webhook(request: Request):
        if config.consent_active is not True:
            raise AdapterError("CONSENT_REVOKED")
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise AdapterError("INVALID_WEBHOOK_JSON")
        for name in ("x-webhook-hmac", "x-webhook-hmac-algorithm"):
            if len(request.headers.getlist(name)) != 1:
                raise AdapterError("WEBHOOK_AUTH_REJECTED")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY:
                raise AdapterError("WEBHOOK_TOO_LARGE")
            body.extend(chunk)
        verify_hmac(
            bytes(body),
            request.headers.get("X-Webhook-Hmac"),
            request.headers.get("X-Webhook-Hmac-Algorithm"),
            config.webhook_secret,
        )
        try:
            raw = json.loads(body, object_pairs_hook=_pairs, parse_constant=_non_json_constant)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise AdapterError("INVALID_WEBHOOK_JSON") from None
        if not isinstance(raw, dict):
            raise AdapterError("INVALID_WEBHOOK_JSON")
        if raw.get("session") != config.session:
            raise AdapterError("SESSION_MAPPING_MISMATCH")
        result = observations.observe(raw, config)
        return JSONResponse(
            content=result, headers={"X-GigMate-Probe-Only": "true", "Cache-Control": "no-store"}
        )

    return app
