"""Selects the registered extraction provider based on configuration.

Selection order:

1. ``GIGMATE_EXTRACTION_PROVIDER`` env var (default ``deterministic``).
2. Match the name to the registered providers table; raise on unknown.

The provider is cached for the process. Tests can call
:func:`_reset_provider_for_testing` to force a fresh lookup or inject a custom
implementation.
"""

from __future__ import annotations

import os
import threading
from typing import Iterable

from .deterministic import DeterministicProvider
from .disabled import DisabledProvider
from .types import ExtractionRequest, Provider

_REGISTRY: dict[str, type[Provider]] = {
    "deterministic": DeterministicProvider,
    "disabled": DisabledProvider,
}

_lock = threading.Lock()
_active: Provider | None = None


def registered_providers() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def register(name: str, factory: type[Provider]) -> None:
    """Add or replace a provider factory under ``name``.

    Intended for tests and future authorized real-model integrations. Production
    code should not need to call this.
    """
    _REGISTRY[name] = factory


def build_provider(name: str | None = None) -> Provider:
    chosen = name or os.environ.get("GIGMATE_EXTRACTION_PROVIDER", "deterministic")
    if chosen not in _REGISTRY:
        raise ValueError(f"Unknown extraction provider {chosen!r}; registered: {sorted(_REGISTRY)}")
    return _REGISTRY[chosen]()


def provider() -> Provider:
    global _active
    with _lock:
        if _active is None:
            _active = build_provider()
    return _active


def _reset_provider_for_testing(instance: Provider | None = None) -> None:
    """Tests inject a custom provider deterministically.

    Passing ``None`` clears the cached provider so the next ``provider()`` call
    re-reads ``GIGMATE_EXTRACTION_PROVIDER`` from the environment.
    """
    global _active
    with _lock:
        _active = instance


def list_provider_metadata() -> list[dict]:
    return [
        {"name": cls.name, "model_version": cls.model_version, "prompt_version": cls.prompt_version}
        for cls in _REGISTRY.values()
    ]


def build_request_for(  # pragma: no cover - test helper only
    *,
    account_id: str,
    conversation_id: str,
    message_id: str,
    message_revision: int,
    message_text: str | None,
    context_version: int,
    candidate_work_order_ids: Iterable[str] = (),
    base_work_order_version: int | None = None,
    base_work_order_snapshot: dict | None = None,
) -> ExtractionRequest:
    return ExtractionRequest(
        account_id=account_id,
        conversation_id=conversation_id,
        message_id=message_id,
        message_revision=message_revision,
        message_text=message_text,
        context_version=context_version,
        candidate_work_order_ids=tuple(candidate_work_order_ids),
        base_work_order_version=base_work_order_version,
        base_work_order_snapshot=base_work_order_snapshot,
    )


__all__ = [
    "Provider",
    "ExtractionRequest",
    "build_provider",
    "list_provider_metadata",
    "provider",
    "registered_providers",
    "register",
]
