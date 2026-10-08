"""Provider interface and request/outcome DTOs for AI extraction.

Implementations MUST obey the contract surfaced in
``docs/en/role-a-team-local-development.md`` and
``docs/en/architecture.md``: never emit ``field_status: confirmed``, never
carry fields that grant execution authority, and always populate
``model_version`` and ``prompt_version``. Real input that does not match a
known synthetic fixture must be returned as
``assignment: needs_review`` with empty ``changes`` until a future authorized
batch relaxes this guard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from gigmate.contracts import ChangeProposal


@dataclass(frozen=True)
class ExtractionRequest:
    """Bounded, allowlisted inputs handed to an extraction provider.

    ``origin`` is the server-side trust boundary: ``"synthetic"`` marks input
    that arrived through a trusted synthetic channel (Replay fixtures, offline
    evaluation); ``"live"`` marks input received from a real connector. The
    default is ``"live"`` so an unmarked request can never be treated as
    synthetic. Providers must gate fixed-template proposals on
    ``origin == "synthetic"``.
    """

    account_id: str
    conversation_id: str
    message_id: str
    message_revision: int
    message_text: str | None
    context_version: int
    candidate_work_order_ids: tuple[str, ...] = ()
    base_work_order_version: int | None = None
    base_work_order_snapshot: dict | None = None
    origin: Literal["synthetic", "live"] = "live"
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionOutcome:
    """Provider result plus the call-level evidence persisted with the proposal."""

    provider_name: str
    proposal: ChangeProposal
    latency_ms: int
    notes: tuple[str, ...] = ()
    refused_reason: str | None = None


class Provider(Protocol):
    name: str
    model_version: str
    prompt_version: str

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome: ...
