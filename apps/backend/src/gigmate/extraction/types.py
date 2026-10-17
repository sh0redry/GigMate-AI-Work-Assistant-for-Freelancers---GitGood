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
    # Server-attached time basis for relative-date resolution. ``None`` means
    # the source did not carry a trustworthy timestamp, and the provider must
    # not invent one (unknown stays missing).
    message_received_at: str | None = None
    workspace_timezone: str | None = None
    # Budget snapshot computed by the worker from durable call traces. The
    # provider never touches the database; it only refuses when the snapshot
    # it was handed is already exhausted. ``None`` means "no budget was
    # attached", which live-origin requests treat as unconfigured.
    budget_call_limit: int | None = None
    budget_token_limit: int | None = None
    budget_calls_used: int = 0
    budget_tokens_used: int = 0
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionOutcome:
    """Provider result plus the call-level evidence persisted with the proposal.

    ``usage`` is the vendor-reported token accounting of the call, normalised
    to ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``. It is
    ``None`` when no call reached the vendor (every refusal path) or when the
    vendor reported nothing usable, which is what keeps a refusal from
    claiming cost evidence it never incurred.
    """

    provider_name: str
    proposal: ChangeProposal
    latency_ms: int
    notes: tuple[str, ...] = ()
    refused_reason: str | None = None
    usage: dict | None = None


class Provider(Protocol):
    name: str
    model_version: str
    prompt_version: str

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome: ...
