"""A/B media handoff. A owns storage/tasks; B owns OCR, ASR, parsing and GenAI."""

import importlib
import os
from dataclasses import dataclass, field
from typing import Protocol

from gigmate.contracts import WahaMediaResult


class ProcessingUnavailable(Exception):
    """No request was submitted. Operator/B configuration is required."""


class ProcessingUncertain(Exception):
    """Submission may have occurred; reconcile rather than automatic model retry."""


@dataclass(frozen=True)
class MediaInput:
    request_id: str
    account_id: str
    conversation_id: str
    snapshot_id: str
    attachment_id: str
    attachment_version: int
    context_version: int
    source_fingerprint: str
    sha256: str
    mimetype: str
    source_occurred_at: str
    content: bytes = field(repr=False)
    caption: str | None = field(default=None, repr=False)
    origin: str = "live"
    message_sent_at: str | None = None
    timezone: str | None = None
    timezone_source: str = "unknown"
    source_observed_at: str | None = None


class MediaProcessor(Protocol):
    def process(self, request: MediaInput) -> WahaMediaResult:
        """B uses request_id for provider reconciliation/idempotency; proposals only."""

    def reconcile(self, request_id: str) -> WahaMediaResult | None:
        """Read-only lookup, never resubmit. None means still unknown."""


def processor() -> MediaProcessor:
    # Trusted server config only, never an HTTP argument. No network factory in A.
    factory = os.environ.get("GIGMATE_MEDIA_PROCESSOR_FACTORY", "")
    if not factory:
        raise ProcessingUnavailable
    try:
        module, name = factory.split(":", 1)
    except ValueError:
        raise ProcessingUnavailable from None
    if not module or not name or ":" in name:
        raise ProcessingUnavailable
    try:
        loaded_module = importlib.import_module(module)
    except ImportError:
        raise ProcessingUnavailable from None
    make_processor = getattr(loaded_module, name, None)
    if not callable(make_processor):
        raise ProcessingUnavailable
    # Construction failures belong to B's implementation, not configuration parsing.
    # Preserve them for callers; the worker still treats unknown outcomes conservatively.
    result = make_processor()
    if not all(callable(getattr(result, method, None)) for method in ("process", "reconcile")):
        raise ProcessingUnavailable
    return result
