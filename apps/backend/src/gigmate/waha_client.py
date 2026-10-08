"""Server-side local WAHA capability client. No sending or automatic retries."""

import json
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx

from gigmate.waha_adapter import SESSION_STATES, AdapterError

VERSION = "2026.9.1"
ENGINE = "WEBJS"
IMAGE = "devlikeapro/waha:latest-2026.9.1@sha256:41283bd89922ec3f722e5a772b844c451634d4aa72e9c34043c3480184f970fe"
MAX_RESPONSE = 2 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def local_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError
        parsed.port
    except (ValueError, TypeError, AttributeError):
        raise AdapterError("LOCAL_WAHA_URL_REQUIRED") from None
    return value.rstrip("/")


@dataclass(frozen=True)
class LocalWahaConfig:
    base_url: str
    account_id: str
    session: str
    api_key: str = field(repr=False)
    webhook_secret: str = field(repr=False)
    allowlisted_chats: frozenset[str] = frozenset()
    consent_active: bool = True

    def __post_init__(self):
        local_url(self.base_url)
        try:
            if str(UUID(self.account_id)) != self.account_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AdapterError("INVALID_TRUSTED_MAPPING") from None
        # WAHA Core local probe has one explicitly bound session.
        if self.session != "default":
            raise AdapterError("LOCAL_DEFAULT_SESSION_REQUIRED")
        if any(
            not isinstance(value, str) or len(value) < 32
            for value in (self.api_key, self.webhook_secret)
        ):
            raise AdapterError("STRONG_LOCAL_SECRET_REQUIRED")
        if not isinstance(self.allowlisted_chats, frozenset) or any(
            not isinstance(chat, str) or not chat for chat in self.allowlisted_chats
        ):
            raise AdapterError("INVALID_TRUSTED_MAPPING")
        if type(self.consent_active) is not bool:
            raise AdapterError("INVALID_TRUSTED_MAPPING")


class LocalWahaClient:
    def __init__(self, config: LocalWahaConfig, *, transport=None, docker_service=False):
        if type(docker_service) is not bool:
            raise AdapterError("INVALID_INTERNAL_MODE")
        self.config = config
        self._client = httpx.Client(
            # Operator-only Compose mode has one fixed internal target; config URLs remain loopback-only.
            base_url="http://waha:3000" if docker_service else local_url(config.base_url),
            headers={"X-Api-Key": config.api_key},
            timeout=10,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self):
        self._client.close()

    def _request(self, method, path, *, body=None, params=None, png=False):
        if self.config.consent_active is not True:
            raise AdapterError("CONSENT_REVOKED")
        try:
            with self._client.stream(
                method,
                path,
                json=body,
                params=params,
                headers={"Accept": "image/png" if png else "application/json"},
            ) as response:
                if response.status_code in {401, 403}:
                    raise AdapterError("WAHA_AUTH_REJECTED")
                if response.status_code == 404:
                    raise AdapterError("WAHA_RESOURCE_NOT_FOUND")
                if response.status_code == 409:
                    raise AdapterError("WAHA_STATE_CONFLICT")
                if not 200 <= response.status_code < 300:
                    raise AdapterError("WAHA_HTTP_FAILED")
                data = bytearray()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    if len(data) + len(chunk) > MAX_RESPONSE:
                        raise AdapterError("WAHA_RESPONSE_TOO_LARGE")
                    data.extend(chunk)
                if png:
                    if response.headers.get("content-type", "").split(";")[0] != "image/png":
                        raise AdapterError("WAHA_INVALID_QR")
                    if not data.startswith(PNG_SIGNATURE):
                        raise AdapterError("WAHA_INVALID_QR")
                    return bytes(data)
                try:
                    return json.loads(data)
                except (ValueError, UnicodeDecodeError):
                    raise AdapterError("WAHA_INVALID_RESPONSE") from None
        except httpx.RequestError:
            # A timed-out session mutation may have succeeded. Check state, never blind retry.
            code = "WAHA_RESULT_UNKNOWN" if method != "GET" else "WAHA_UNAVAILABLE"
            raise AdapterError(code) from None

    def create_session(self):
        # Probe is on the separate Compose network, not the business API.
        result = self._request(
            "POST",
            "/api/sessions",
            body={
                "name": self.config.session,
                "start": True,
                "config": {
                    "debug": False,
                    "webjs": {"tagsEventsOn": True},
                    "webhooks": [
                        {
                            "url": "http://probe:18701/probe/webhook",
                            "events": [
                                "session.status",
                                "message.any",
                                "message.edited",
                                "message.revoked",
                                "message.ack",
                            ],
                            "hmac": {"key": self.config.webhook_secret},
                            "retries": {"policy": "constant", "delaySeconds": 2, "attempts": 3},
                        }
                    ],
                },
            },
        )
        if not isinstance(result, dict) or result.get("name") != self.config.session:
            raise AdapterError("WAHA_SESSION_MISMATCH")
        return {"mode": "capability_probe", "session_created": True}

    def status(self):
        result = self._request("GET", "/api/sessions/default")
        if not isinstance(result, dict) or result.get("name") != self.config.session:
            raise AdapterError("WAHA_SESSION_MISMATCH")
        state = result.get("status")
        engine = result.get("engine", {})
        if not isinstance(state, str) or state not in SESSION_STATES:
            raise AdapterError("WAHA_UNKNOWN_STATE")
        if state == "STOPPED" and (engine is None or engine == {}):
            # Stopped sessions have no runtime engine. Verify the pinned server,
            # never assume that missing metadata means the expected engine.
            declared = result.get("config") or {}
            if not isinstance(declared, dict) or declared.get("engine") not in {None, ENGINE}:
                raise AdapterError("WAHA_ENGINE_MISMATCH")
            server = self._request("GET", "/api/server/version")
            if (
                not isinstance(server, dict)
                or server.get("engine") != ENGINE
                or server.get("version") != VERSION
            ):
                raise AdapterError("WAHA_ENGINE_MISMATCH")
            engine = {"engine": ENGINE}
        if not isinstance(engine, dict) or engine.get("engine") != ENGINE:
            raise AdapterError("WAHA_ENGINE_MISMATCH")
        # Never return config/credentials/me/profile to generic command output.
        return {
            "mode": "capability_probe",
            "state": state,
            "connected": state == "WORKING",
            "engine": ENGINE,
        }

    def restart_failed_session(self):
        if self.status()["state"] not in {"FAILED", "STOPPED"}:
            raise AdapterError("WAHA_RECOVERY_NOT_REQUIRED")
        result = self._request("POST", "/api/sessions/default/restart", body={})
        if not isinstance(result, dict) or result.get("name") != self.config.session:
            raise AdapterError("WAHA_SESSION_MISMATCH")
        return {"mode": "capability_probe", "restart_requested": True}

    def configure_business_webhook(self, connection_id):
        try:
            if str(UUID(connection_id)) != connection_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AdapterError("INVALID_TRUSTED_MAPPING") from None
        self.status()  # Check the pinned engine before changing its configuration.
        session = self._request("GET", "/api/sessions/default")
        if not isinstance(session, dict) or session.get("name") != "default":
            raise AdapterError("WAHA_SESSION_MISMATCH")
        existing = session.get("config") or {}
        if not isinstance(existing, dict) or not isinstance(existing.get("webjs") or {}, dict):
            raise AdapterError("WAHA_INVALID_RESPONSE")
        result = self._request(
            "PUT",
            "/api/sessions/default",
            body={
                "name": "default",
                "config": {
                    **existing,
                    "webjs": {**(existing.get("webjs") or {}), "tagsEventsOn": True},
                    "webhooks": [
                        {
                            "url": f"http://ingress:8000/api/v1/connectors/waha/{connection_id}/events",
                            "events": [
                                "session.status",
                                "message.any",
                                "message.edited",
                                "message.revoked",
                                "message.ack",
                            ],
                            "hmac": {"key": self.config.webhook_secret},
                            "retries": {"policy": "constant", "delaySeconds": 2, "attempts": 3},
                        }
                    ],
                },
            },
        )
        if not isinstance(result, dict) or result.get("name") != "default":
            raise AdapterError("WAHA_SESSION_MISMATCH")
        return {"business_webhook_configured": True, "session_restart_possible": True}

    def create_business_session(self, connection_id):
        if str(UUID(connection_id)) != connection_id:
            raise AdapterError("INVALID_TRUSTED_MAPPING")
        result = self._request(
            "POST",
            "/api/sessions",
            body={
                "name": "default",
                "start": True,
                "config": {
                    "debug": False,
                    "webjs": {"tagsEventsOn": True},
                    "webhooks": [
                        {
                            "url": f"http://ingress:8000/api/v1/connectors/waha/{connection_id}/events",
                            "events": [
                                "session.status",
                                "message.any",
                                "message.edited",
                                "message.revoked",
                                "message.ack",
                            ],
                            "hmac": {"key": self.config.webhook_secret},
                            "retries": {"policy": "constant", "delaySeconds": 2, "attempts": 3},
                        }
                    ],
                },
            },
        )
        if not isinstance(result, dict) or result.get("name") != "default":
            raise AdapterError("WAHA_RESULT_UNKNOWN")
        return {"session_created": True}

    def inspect_business_session(self, connection_id):
        status = self.status()
        session = self._request("GET", "/api/sessions/default")
        config = session.get("config") if isinstance(session, dict) else None
        hooks = config.get("webhooks") if isinstance(config, dict) else None
        expected = f"http://ingress:8000/api/v1/connectors/waha/{connection_id}/events"
        matches = bool(
            isinstance(hooks, list)
            and len(hooks) == 1
            and isinstance(hooks[0], dict)
            and hooks[0].get("url") == expected
            and isinstance(hooks[0].get("hmac"), dict)
            and hooks[0]["hmac"].get("key") == self.config.webhook_secret
            and set(hooks[0].get("events", []))
            >= {"session.status", "message.any", "message.edited", "message.revoked", "message.ack"}
        )
        return {**status, "business_webhook_matches": matches}

    def qr(self):
        if self.status()["state"] != "SCAN_QR_CODE":
            raise AdapterError("WAHA_NOT_WAITING_FOR_QR")
        return self._request("GET", "/api/default/auth/qr", png=True)

    def recent_chats(self, *, limit=20, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise AdapterError("INVALID_CHAT_RANGE")
        if not self.status()["connected"]:
            raise AdapterError("WAHA_NOT_CONNECTED")
        result = self._request(
            "GET",
            "/api/default/chats",
            params={
                "limit": limit,
                "offset": offset,
                # Pinned 2026.9.1 accepts this name; current web docs use messageTimestamp.
                "sortBy": "conversationTimestamp",
                "sortOrder": "desc",
            },
        )
        if not isinstance(result, list) or len(result) > limit:
            raise AdapterError("WAHA_INVALID_RESPONSE")
        choices, identities = [], set()
        for item in result:
            if not isinstance(item, dict):
                raise AdapterError("WAHA_INVALID_RESPONSE")
            identity, name = item.get("id"), item.get("name")
            if isinstance(identity, dict):
                # WEBJS chats returns a Wid object. Use its canonical serialized ID only.
                identity = identity.get("_serialized")
            if (
                not isinstance(identity, str)
                or not 1 <= len(identity) <= 256
                or any(ord(char) < 32 or ord(char) == 127 for char in identity)
                or identity in identities
                or (name is not None and not isinstance(name, str))
            ):
                raise AdapterError("WAHA_INVALID_RESPONSE")
            identities.add(identity)
            if identity.endswith(("@c.us", "@lid", "@g.us")):
                # Discovery is local-owner metadata only. Drop all message/profile fields.
                choices.append({"id": identity, "name": (name or "")[:200]})
        return choices

    def history(self, chat: str, *, limit=10, offset=0):
        if chat not in self.config.allowlisted_chats:
            raise AdapterError("CONVERSATION_NOT_ALLOWED")
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise AdapterError("INVALID_HISTORY_RANGE")
        if not self.status()["connected"]:
            raise AdapterError("WAHA_NOT_CONNECTED")
        result = self._request(
            "GET",
            f"/api/default/chats/{quote(chat, safe='')}/messages",
            params={"limit": limit, "offset": offset, "downloadMedia": "false"},
        )
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise AdapterError("WAHA_INVALID_RESPONSE")
        # Count available records only. No text/media/history is exposed or stored.
        return {
            "mode": "capability_probe",
            "available_records": len(result),
            "complete_history": False,
        }
