"""Real-model extraction provider skeleton.

This is the seam for the separately authorized real-model provider batch. It
wires configuration, prompt loading and the call shape so the next batch only
has to fill in :meth:`LLMProvider._invoke_model` and
:meth:`LLMProvider._parse_response` without touching the worker, contracts,
registry selection or the Replay path.

Until that batch lands the provider is intentionally non-emitting: every
``propose`` call returns ``assignment: needs_review`` with an
``unresolved_questions`` entry that names the missing piece (no configuration,
or ``GIGMATE_LLM_LIVE`` not set, or the seam not yet implemented). The model
and prompt version strings surface the not-yet-live state in
``ModelCallTrace`` so it is obvious in audit what produced the refusal.

Configuration (environment variables, all optional until the seam is filled):

- ``GIGMATE_LLM_PROVIDER`` - vendor name (e.g. ``openai``, ``anthropic``). Used
  in ``model_version`` and as a sanity check that the operator picked a vendor
  the next batch supports.
- ``GIGMATE_LLM_MODEL`` - model identifier passed to the SDK call. Default
  marker ``skeleton-pending`` until configured.
- ``GIGMATE_LLM_API_KEY`` - server-side only. Never read by this module until
  ``_invoke_model`` is implemented; the seam is responsible for using it
  without logging it.
- ``GIGMATE_LLM_ENDPOINT`` - optional base URL override for testing.
- ``GIGMATE_LLM_PROMPT_PATH`` - optional override of the bundled prompt file
  (defaults to the versioned file in this package).
- ``GIGMATE_LLM_LIVE=1`` - the explicit live gate. It is a *positive* opt-in:
  while it is off the provider refuses every call at the provider layer with a
  ``llm:live-gate-off`` note, even when ``GIGMATE_LLM_PROVIDER`` and
  ``GIGMATE_LLM_MODEL`` are configured. When it is on the call reaches
  :meth:`_invoke_model`, which stays a stub and returns ``needs_review`` with a
  ``llm:seam-pending`` note until the real-model batch implements it. Either
  way a misconfiguration surfaces immediately in the trace rather than
  silently falling back to a real model call.

The prompt header is read on every call. A missing file, an OS error, a
non-UTF-8 file, a missing header line or an empty header value all fall back to
``0.0.0-skeleton`` and surface an auditable ``llm:prompt-malformed`` outcome so
a bad prompt configuration can never raise out of ``propose`` into the worker's
failure path.

The skeleton honors the same origin trust boundary as the deterministic
provider: live-origin input is always refused with ``needs_review`` until the
real-model batch relaxes the guard. See
``docs/en/role-b-extraction.md`` and ``case-007-live-origin-with-fixture-text``
in the evaluation manifest.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import uuid4

from gigmate.contracts import ChangeProposal

from .types import ExtractionOutcome, ExtractionRequest

_PROMPT_VERSION_PREFIX = "prompt_version:"
_DEFAULT_PROMPT_FILENAME = "role_b_extraction_v1.txt"
_LIVE_GATE = "GIGMATE_LLM_LIVE"
_PROVIDER_ENV = "GIGMATE_LLM_PROVIDER"
_MODEL_ENV = "GIGMATE_LLM_MODEL"
_ENDPOINT_ENV = "GIGMATE_LLM_ENDPOINT"
_PROMPT_PATH_ENV = "GIGMATE_LLM_PROMPT_PATH"
_PROMPT_VERSION_PENDING = "0.0.0-skeleton"
_MODEL_VERSION_PENDING = "skeleton:pending"


class LLMIntegrationPending(RuntimeError):
    """Raised when control reaches the unimplemented :meth:`_invoke_model` seam.

    Caught by :meth:`LLMProvider.propose` and returned as a ``needs_review``
    outcome so the worker still records evidence. The provider blocks the
    call at its own layer (missing configuration, live gate off) before the
    seam is reached, so this only fires once an operator has explicitly opened
    the live gate on a build whose seam is still a stub. The next authorized
    batch replaces the stub with a real SDK call and this class becomes
    unreachable.
    """


class LLMProvider:
    """Real-model extraction provider skeleton.

    Until :meth:`_invoke_model` is implemented the provider refuses every
    request with ``assignment: needs_review`` and a clear reason in
    ``unresolved_questions``. The provider never makes outbound network calls
    in this state; it only reads configuration and the bundled prompt file.
    """

    name = "llm"
    model_version = _MODEL_VERSION_PENDING
    prompt_version = _PROMPT_VERSION_PENDING

    def __init__(self) -> None:
        # Class attributes are placeholders for documentation. The real
        # versions depend on configuration, so they are recomputed per call
        # below and surfaced in the returned outcome and trace.
        self._configured_provider = os.environ.get(_PROVIDER_ENV)
        self._configured_model = os.environ.get(_MODEL_ENV)
        self._configured_endpoint = os.environ.get(_ENDPOINT_ENV)
        self._configured_live = os.environ.get(_LIVE_GATE) == "1"
        self._prompt_path = self._resolve_prompt_path()
        # Reset on every ``_read_prompt_version`` call; a non-None value means
        # the prompt file is missing or malformed and ``propose`` surfaces it
        # as an ``llm:prompt-malformed`` outcome instead of letting the
        # underlying error escape into the worker's failure path.
        self._prompt_load_error: str | None = None

    # ------------------------------------------------------------------ public

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome:
        began = time.monotonic()
        prompt_version = self._read_prompt_version()
        model_version = self._model_version()

        # A malformed prompt configuration must still produce an auditable
        # needs_review outcome rather than escaping as a ValidationError (empty
        # version) or UnicodeDecodeError into the worker's failure path.
        if self._prompt_load_error is not None:
            return self._needs_review(
                request,
                reason=self._prompt_load_error,
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:prompt-malformed",),
            )

        # The origin trust boundary is the strongest gate and is checked before
        # configuration so live input is always refused, configured or not.
        if request.origin != "synthetic":
            return self._needs_review(
                request,
                reason=(
                    "LLM provider refuses live-origin input until the real-model "
                    "batch authorizes live content (see case-007)."
                ),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:origin-live-refused",),
            )

        refusal = self._refusal_reason(request)
        if refusal is not None:
            note, reason = refusal
            return self._needs_review(
                request,
                reason=reason,
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=(note,),
            )

        # Reachable only with a complete configuration *and* the live gate on;
        # the seam itself raises until the real-model batch implements it.
        try:
            return self._invoke_model(request, began, prompt_version, model_version)
        except LLMIntegrationPending as exc:
            return self._needs_review(
                request,
                reason=str(exc),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:seam-pending",),
            )

    # ------------------------------------------------------------- helpers

    def _refusal_reason(self, request: ExtractionRequest) -> tuple[str, str] | None:
        """Return ``(note, reason)`` when the call is refused at the provider layer.

        Configuration is checked before the live gate so an unconfigured
        deployment keeps the descriptive ``llm:not-configured`` reason. The
        live gate is then a positive opt-in: while ``GIGMATE_LLM_LIVE`` is off
        the provider refuses every call here with ``llm:live-gate-off``, even
        when the vendor and model are configured. Only when the configuration
        is complete *and* the live gate is on does control reach
        :meth:`_invoke_model`; the skeleton seam there returns ``needs_review``
        with ``llm:seam-pending`` until the real-model batch implements it.
        """
        if not self._configured_provider or not self._configured_model:
            return (
                "llm:not-configured",
                "LLM provider is not configured; set GIGMATE_LLM_PROVIDER and "
                "GIGMATE_LLM_MODEL (and GIGMATE_LLM_API_KEY) before the real-model "
                "batch is authorized.",
            )
        if not self._configured_live:
            return (
                "llm:live-gate-off",
                "GIGMATE_LLM_LIVE=1 is required before the LLM seam is invoked; "
                "the provider refuses every call while the live gate is off - even "
                "when GIGMATE_LLM_PROVIDER/GIGMATE_LLM_MODEL are configured - so a "
                "misconfigured deployment cannot silently fall back to a real "
                "model call once _invoke_model is implemented.",
            )
        return None

    def _model_version(self) -> str:
        provider = self._configured_provider or "skeleton"
        model = self._configured_model or "pending"
        return f"{provider}:{model}"

    def _resolve_prompt_path(self) -> Path:
        override = os.environ.get(_PROMPT_PATH_ENV)
        if override:
            return Path(override)
        return Path(__file__).resolve().parent / "prompts" / _DEFAULT_PROMPT_FILENAME

    def _read_prompt_version(self) -> str:
        """Return the ``prompt_version:`` header, falling back on malformed files.

        Every failure mode - missing file, OS error, non-UTF-8 bytes, a missing
        header line or an empty header value - falls back to
        :data:`_PROMPT_VERSION_PENDING` and records a human-readable cause in
        :attr:`_prompt_load_error`. ``propose`` surfaces that cause as an
        auditable ``llm:prompt-malformed`` outcome, so a bad prompt config can
        no longer raise ``UnicodeDecodeError`` (non-UTF-8 file) or a
        ``ValidationError`` (empty version string) into the worker's failure
        path.
        """
        path = self._prompt_path
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped.startswith(_PROMPT_VERSION_PREFIX):
                        continue
                    version = stripped[len(_PROMPT_VERSION_PREFIX) :].strip()
                    if version:
                        self._prompt_load_error = None
                        return version
                    self._prompt_load_error = (
                        f"LLM prompt file {path} declares an empty "
                        f"{_PROMPT_VERSION_PREFIX} header; using "
                        f"{_PROMPT_VERSION_PENDING}."
                    )
                    return _PROMPT_VERSION_PENDING
        except OSError as exc:
            self._prompt_load_error = (
                f"LLM prompt file {path} could not be opened "
                f"({type(exc).__name__}); using {_PROMPT_VERSION_PENDING}."
            )
            return _PROMPT_VERSION_PENDING
        except UnicodeDecodeError:
            self._prompt_load_error = (
                f"LLM prompt file {path} is not valid UTF-8; using {_PROMPT_VERSION_PENDING}."
            )
            return _PROMPT_VERSION_PENDING
        self._prompt_load_error = (
            f"LLM prompt file {path} has no {_PROMPT_VERSION_PREFIX} header line; "
            f"using {_PROMPT_VERSION_PENDING}."
        )
        return _PROMPT_VERSION_PENDING

    def _needs_review(
        self,
        request: ExtractionRequest,
        *,
        reason: str,
        latency_ms: int,
        prompt_version: str,
        model_version: str,
        notes: tuple[str, ...],
    ) -> ExtractionOutcome:
        proposal = {
            "schema_version": "0.1.0",
            "proposal_id": str(uuid4()),
            "conversation_id": request.conversation_id,
            "work_order_id": None,
            "base_work_order_version": None,
            "base_context_version": request.context_version,
            "assignment": "needs_review",
            "candidates": [
                {"work_order_id": identifier, "confidence": 0.0}
                for identifier in request.candidate_work_order_ids
            ],
            "changes": [],
            "unresolved_questions": [reason],
            "draft_text": None,
            "model_version": model_version,
            "prompt_version": prompt_version,
        }
        validated = ChangeProposal.model_validate(proposal)
        return ExtractionOutcome(
            provider_name=self.name,
            proposal=validated,
            latency_ms=latency_ms,
            notes=notes,
            refused_reason=reason,
        )

    @staticmethod
    def _elapsed(began: float) -> int:
        return max(0, int((time.monotonic() - began) * 1000))

    # ---------------------------------------------------------- seam methods

    def _invoke_model(
        self,
        request: ExtractionRequest,
        began: float,
        prompt_version: str,
        model_version: str,
    ) -> ExtractionOutcome:
        """Call the configured LLM and return a real ``ExtractionOutcome``.

        The authorized real-model batch replaces this method with a real SDK
        call (Anthropic / OpenAI / etc.). Until then it raises
        :class:`LLMIntegrationPending` which :meth:`propose` turns into a
        ``needs_review`` outcome with full evidence.
        """
        raise LLMIntegrationPending(
            "LLMProvider._invoke_model is not implemented; the real-model batch "
            "must replace this method. The provider still records the configured "
            "model and prompt versions on the trace."
        )

    def _parse_response(self, raw: str) -> ChangeProposal:
        """Parse the LLM's JSON response into a :class:`ChangeProposal`.

        Filled in alongside :meth:`_invoke_model`. The skeleton never reaches
        this code path.
        """
        raise LLMIntegrationPending(
            "LLMProvider._parse_response is not implemented; the real-model "
            "batch must replace this method."
        )


__all__ = ["LLMProvider", "LLMIntegrationPending"]
