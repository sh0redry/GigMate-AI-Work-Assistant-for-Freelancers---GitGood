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
    # Date-grounding basis (pre-activation gate 4). Both are server-attached:
    # ``message_received_at`` is the connector's sending time in UTC ``Z`` form
    # and ``workspace_timezone`` is the merchant's validated IANA zone. Either
    # may be ``None`` when the caller cannot supply it; a provider must then
    # refuse to promote relative-date interpretations instead of guessing.
    message_received_at: str | None = None
    workspace_timezone: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionOutcome:
    """Provider result plus the call-level evidence persisted with the proposal."""

    provider_name: str
    proposal: ChangeProposal
    latency_ms: int
    notes: tuple[str, ...] = ()
    refused_reason: str | None = None
    # Stable per-call identifier sent to the vendor and persisted with the
    # trace so an operator can correlate a row with the vendor's own logs.
    # ``None`` when no vendor call was ever issued.
    request_id: str | None = None
    # Cost accounting (pre-activation batch 2). All four fields are
    # ``None`` while the seam is closed; the next authorized batch populates
    # them whenever a real vendor call completes. ``cost_usd`` is rounded to
    # the same precision that ``model_call_traces.cost_usd`` stores
    # (``Numeric(12, 6)``); callers should not rely on finer precision.
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    # Stable, secret-free diagnostic note that explains why no cost was
    # recorded (e.g. ``llm:cost-pricing-missing`` for an unknown model or
    # ``llm:cost-usage-missing`` when the vendor omits ``usage``). ``None``
    # when a cost row was recorded.
    cost_note: str | None = None


class Provider(Protocol):
    name: str
    model_version: str
    prompt_version: str

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome: ...
