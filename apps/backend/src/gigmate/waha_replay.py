"""Synthetic corpus and in-memory A-01 acceptance ledger, never live ingestion."""

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from gigmate.waha_adapter import (
    PROFILE,
    ROOT,
    AdapterError,
    NormalizationContext,
    ResolvedMessage,
    semantic_digest,
)

FIXTURES = ROOT / "apps/backend/tests/fixtures/waha_a01.json"


def _merge(base, patch):
    if not isinstance(base, dict) or not isinstance(patch, dict):
        raise ValueError
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_cases(path: Path = FIXTURES) -> list[dict]:
    """Expand synthetic patches; trust declarations apply only to the offline demo."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if (
            document["manifest_version"] != "1.0.0"
            or document["profile"] != PROFILE
            or document["data_classification"] != "synthetic"
        ):
            raise ValueError
        cases = []
        names = set()
        for case in document["cases"]:
            name = case["name"]
            if not isinstance(name, str) or not name or name in names:
                raise ValueError
            names.add(name)
            context_data = _merge(document["context"], case.get("context_patch", {}))
            message_data = context_data.pop("message", None)
            context = NormalizationContext(
                **context_data,
                message=ResolvedMessage(**message_data) if message_data is not None else None,
            )
            raw = _merge(document["raw"], case.get("raw_patch", {}))
            # Keep fixture IDs visibly fictional. Other failures are normalizer test inputs.
            for value in (raw.get("id"), raw.get("session")):
                if isinstance(value, str) and not value.startswith("synthetic:"):
                    raise ValueError
            cases.append({"name": name, "raw": raw, "context": context, "expect": case["expect"]})
        if not cases:
            raise ValueError
        return cases
    except (OSError, ValueError, KeyError, TypeError):
        raise AdapterError("INVALID_SYNTHETIC_CORPUS") from None


@dataclass(frozen=True)
class ReplayResult:
    duplicate: bool
    context_version: int | None


class ReplayLedger:
    """Demonstrate dedup/revision policies without database/queue guarantees.

    New receipt times do not conflict. ACKs never collapse with text revisions.
    No raw provider data, jobs, AI calls, approvals or sends are stored/created.
    State disappears when this object/process ends. Do not use in a webhook.
    """

    def __init__(self):
        self._events = {}
        self._messages = {}
        self._scopes = {}
        self._context_versions = {}

    def accept(self, event: dict) -> ReplayResult:
        digest = semantic_digest(event)
        event_id = event["event_id"]
        account = event["account_id"]
        conversation = event["conversation_id"]
        scope = (account, conversation)
        version = self._context_versions.get(scope, 0) if conversation else None
        if event_id in self._events:
            if self._events[event_id] != digest:
                raise AdapterError("IDEMPOTENCY_CONFLICT")
            return ReplayResult(True, version)
        event_type = event["event_type"]
        if event_type != "session.status":
            message_id = event["payload"]["message_id"]
            identity = (*scope, event["provider_message_id"])
            if message_id in self._scopes and self._scopes[message_id] != identity:
                raise AdapterError("MESSAGE_MAPPING_MISMATCH")
            latest = self._messages.get(identity)
            revision = event["message_revision"]
            projection = {
                key: deepcopy(event[key])
                for key in ("event_type", "direction", "source", "payload")
            }
            if event_type == "message.ack":
                if not latest or revision != latest[0]:
                    raise AdapterError("VERSION_CONFLICT")
                if latest[1]["payload"]["message_id"] != message_id:
                    raise AdapterError("MESSAGE_MAPPING_MISMATCH")
                if event["direction"] != latest[1]["direction"]:
                    raise AdapterError("MESSAGE_MAPPING_MISMATCH")
            elif latest and revision == latest[0]:
                if projection != latest[1]:
                    raise AdapterError("IDEMPOTENCY_CONFLICT")
                self._events[event_id] = digest
                return ReplayResult(True, version)
            else:
                if event_type == "message.created":
                    valid = latest is None and revision == 1
                else:
                    valid = (
                        latest is not None
                        and revision == latest[0] + 1
                        and latest[1]["payload"]["message_id"] == message_id
                        and latest[1]["event_type"] != "message.revoked"
                    )
                if not valid:
                    raise AdapterError("VERSION_CONFLICT")
                # Mutate only after all checks pass. This is an in-memory demonstration.
                self._messages[identity] = (revision, projection)
                self._scopes[message_id] = identity
                version += 1
                self._context_versions[scope] = version
        self._events[event_id] = digest
        return ReplayResult(False, version)
