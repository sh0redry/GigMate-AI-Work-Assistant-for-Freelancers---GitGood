"""Real-model extraction provider (DeepSeek / OpenAI-compatible).

This module is the live real-model extraction provider. The default vendor is
DeepSeek, but any OpenAI-compatible vendor (``deepseek``/``openai``/``custom``)
is supported in the call shape. The provider never makes an outbound network
call until both gates are open:

1. The class flag :attr:`LLMProvider._SKELETON_SEAM` is ``False`` — the seam
   is implemented (see :meth:`LLMProvider._invoke_model`), so this gate is
   open. It exists so a build whose ``_invoke_model`` was replaced by a stub
   still refuses audibly with ``llm:seam-pending`` instead of crashing or
   making a silent network call.
2. ``GIGMATE_LLM_LIVE=1`` is exported (the explicit operator switch).

Both gates must be open. Because gate 1 is open, the refusal notes an operator
actually sees are the configuration ones: a missing configuration surfaces as
``llm:not-configured`` and a closed operator gate as ``llm:live-gate-off``.
Live-origin input is additionally refused unless
``GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`` is exported, so real customer content can
never reach the model by accident.

Configuration (environment variables):

- ``GIGMATE_LLM_PROVIDER`` - vendor name (``deepseek`` / ``openai`` /
  ``custom``). Used in ``model_version`` and as a sanity check that the
  operator picked a vendor this build actually supports.
- ``GIGMATE_LLM_MODEL`` - model identifier passed to the chat-completions
  call (e.g. ``deepseek-chat``, ``deepseek-reasoner``, ``gpt-4o-mini``).
- ``GIGMATE_LLM_API_KEY`` - server-side only. Read on each call, never
  stored on the instance, never logged.
- ``GIGMATE_LLM_ENDPOINT`` - base URL override. Without it the endpoint
  follows the vendor: ``deepseek`` -> ``https://api.deepseek.com``,
  ``openai`` -> ``https://api.openai.com``, ``custom`` -> refused (an
  explicit endpoint is required).
- ``GIGMATE_LLM_PROMPT_PATH`` - optional override of the bundled prompt
  file (defaults to the versioned file in this package).
- ``GIGMATE_LLM_LIVE=1`` - the explicit operator gate. Required to reach
  :meth:`_invoke_model` once the skeleton flag is flipped.
- ``GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`` - opt-in switch that lets
  ``request.origin == "live"`` traffic reach the model. Defaults to off.
- ``GIGMATE_LLM_LIVE_ACCOUNTS`` - optional comma-separated account allowlist.
  When set, live calls for any other account are refused with
  ``llm:account-not-authorized``.
- ``GIGMATE_LLM_DAILY_CALL_BUDGET`` / ``GIGMATE_LLM_DAILY_TOKEN_BUDGET`` -
  required for live traffic. The worker sums the day's committed
  ``model_call_traces`` and attaches the counters to the request; the provider
  refuses with ``llm:budget-not-configured`` or ``llm:budget-exhausted``
  before any network I/O.

Provenance, not model output, decides identity: ``conversation_id``,
``base_context_version``, ``work_order_id``, ``base_work_order_version`` and
every change's ``sources`` are re-bound to the server-issued request before
validation. A response that names an order or version outside the request is
refused with ``llm:provenance-mismatch`` instead of being promoted.

A read timeout or dropped connection after submission is treated as an
unknown outcome (``llm:result-unknown``): it may have been charged, so it is
never retried automatically and never becomes a business change.

The prompt header is read on every call. A missing file, an OS error, a
non-UTF-8 file, a missing header line or an empty header value all fall back
to ``0.0.0-skeleton`` and surface an auditable ``llm:prompt-malformed``
outcome so a bad prompt configuration can never raise out of ``propose`` into
the worker's failure path.

Test seam: ``self._client_factory`` is an instance attribute pointing at
``httpx.Client``. Tests replace it with a fake client to verify the request
shape and parse responses without hitting the network.

This module does not read ``OPENAI_API_KEY`` or ``ANTHROPIC_API_KEY``; only
``GIGMATE_LLM_API_KEY`` is honoured so model credentials stay under the
operator's explicit control.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import ValidationError

from gigmate.contracts import ChangeProposal

from .types import ExtractionOutcome, ExtractionRequest

_PROMPT_VERSION_PREFIX = "prompt_version:"
_DEFAULT_PROMPT_FILENAME = "role_b_extraction_v1.txt"
_LIVE_GATE = "GIGMATE_LLM_LIVE"
_PROVIDER_ENV = "GIGMATE_LLM_PROVIDER"
_MODEL_ENV = "GIGMATE_LLM_MODEL"
_API_KEY_ENV = "GIGMATE_LLM_API_KEY"
_ENDPOINT_ENV = "GIGMATE_LLM_ENDPOINT"
_PROMPT_PATH_ENV = "GIGMATE_LLM_PROMPT_PATH"
_ALLOW_LIVE_ORIGIN_ENV = "GIGMATE_LLM_ALLOW_LIVE_ORIGIN"
_LIVE_ACCOUNTS_ENV = "GIGMATE_LLM_LIVE_ACCOUNTS"

_PROMPT_VERSION_PENDING = "0.0.0-skeleton"
_MODEL_VERSION_PENDING = "skeleton:pending"

# OpenAI-compatible vendors this build actually knows how to call. The
# ``custom`` vendor exists so operators can point at a private deployment of
# an OpenAI-compatible API (vLLM, TGI, etc.) without code changes.
_KNOWN_VENDORS = frozenset({"deepseek", "openai", "custom"})

# Default endpoints per vendor. DeepSeek is the default vendor; the endpoint
# matches the documented DeepSeek API base URL. ``openai`` resolves to the
# documented OpenAI base URL so an OpenAI key can never be sent to DeepSeek
# (and vice versa). ``custom`` has no default: it requires
# ``GIGMATE_LLM_ENDPOINT``.
_DEEPSEEK_DEFAULT_ENDPOINT = "https://api.deepseek.com"
_OPENAI_DEFAULT_ENDPOINT = "https://api.openai.com"

# Models that reject ``response_format={"type": "json_object"}``. DeepSeek's
# reasoning model does not implement JSON Output, so sending this shape to it
# is a guaranteed 400; refusing locally keeps the failure auditable instead of
# burning a round-trip and an opaque vendor error.
_JSON_MODE_UNSUPPORTED_MODELS = frozenset({"deepseek-reasoner"})

# Network hygiene: bound the request time and retry only when the vendor
# definitely did not start work. A 408/429 response and a failed TCP connect
# are safe to repeat; a read timeout, a dropped connection after the request
# was written, a 5xx and a malformed body may all have been charged, so they
# become ``llm:result-unknown`` and are never retried automatically.
_REQUEST_TIMEOUT_S = 30.0
_MAX_RETRIES = 1
_RETRYABLE_STATUS_CODES = frozenset({408, 429})
_RETRY_BACKOFF_S = 0.5

_log = logging.getLogger(__name__)


class LLMResultUnknown(RuntimeError):
    """The request may have reached the vendor and been charged.

    Raised for read timeouts, dropped connections and truncated bodies. The
    caller must record ``llm:result-unknown`` and must not resubmit blind.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


def _normalise_usage(raw: object) -> dict | None:
    """Normalise a vendor ``usage`` object to the three token counters.

    Vendors disagree on the field set (DeepSeek adds cache hit/miss counters,
    OpenAI adds cached-token detail). Only the three counters every
    OpenAI-compatible vendor reports are kept, so the trace row stays stable
    across vendors. Returns ``None`` when the vendor reported nothing usable.
    """

    if not isinstance(raw, dict):
        return None

    def _counter(key: str) -> int | None:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return int(value)

    usage = {
        "prompt_tokens": _counter("prompt_tokens"),
        "completion_tokens": _counter("completion_tokens"),
        "total_tokens": _counter("total_tokens"),
    }
    if all(value is None for value in usage.values()):
        return None
    return usage


def _sanitised_http_reason(exc: BaseException) -> str:
    """Return a stable diagnostic without endpoint, vendor or credential detail.

    The vendor URL, the exception message and any header echo can contain
    private deployment details, so only the failure *class* is reported.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        kind = f"status-{exc.response.status_code}"
    elif isinstance(exc, httpx.TimeoutException):
        kind = "timeout"
    elif isinstance(exc, httpx.ConnectError):
        kind = "connect"
    else:
        kind = "transport"
    return f"LLM HTTP call failed ({kind}); endpoint and credential details are redacted."


class LLMIntegrationPending(RuntimeError):
    """Raised when :meth:`_invoke_model` is still an unimplemented seam.

    The real :meth:`_invoke_model` in this batch returns typed
    ``needs_review`` outcomes instead of raising, so this exception is
    unreachable from this module. It is kept — and still caught by
    :meth:`LLMProvider.propose` — so a deployment that flips
    ``_SKELETON_SEAM=False`` on a build whose ``_invoke_model`` has been
    replaced by a stub still gets an auditable ``llm:seam-pending`` refusal
    instead of a crash or a silent network call.
    """


class LLMProvider:
    """Real-model extraction provider (DeepSeek / OpenAI-compatible).

    Two gates run in front of :meth:`_invoke_model`, in order:

    1. The class flag :attr:`_SKELETON_SEAM` — the implementation gate. It is
       ``False`` because :meth:`_invoke_model` performs the real
       OpenAI-compatible chat-completions call. Keeping the flag means a build
       whose ``_invoke_model`` regressed to a stub still refuses every request
       with ``assignment: needs_review`` and an ``llm:seam-pending`` note
       instead of failing open.
    2. ``GIGMATE_LLM_LIVE=1`` — the operator gate. A closed operator gate
       refuses every call with ``llm:live-gate-off`` and a missing or
       unsupported configuration with ``llm:not-configured``, so deploying
       this code without exporting the switch and the credentials never
       reaches the model.

    Only when both gates are open and the configuration is complete does
    control reach the origin check and :meth:`_invoke_model`, which performs
    the real OpenAI-compatible chat-completions call through
    ``self._client_factory``.
    """

    # Safety gate #1 — implementation gate. ``False`` because
    # :meth:`_invoke_model` is implemented (real OpenAI-compatible
    # chat-completions call). Flipping it back to ``True`` restores the
    # blanket ``llm:seam-pending`` refusal, which is the safe direction:
    # the operator switch (``GIGMATE_LLM_LIVE``) remains the gate that
    # decides whether this deployment is allowed to reach the vendor.
    _SKELETON_SEAM: bool = False

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
        self._allow_live_origin = os.environ.get(_ALLOW_LIVE_ORIGIN_ENV) == "1"
        self._prompt_path = self._resolve_prompt_path()
        # ``_prompt_load_error`` is reset to ``None`` on every
        # ``_read_prompt_version`` call; a non-None value surfaces as an
        # ``llm:prompt-malformed`` outcome so the trace records the cause.
        self._prompt_load_error: str | None = None
        # Test seam: replace this attribute with a fake client to assert
        # the request shape and inject responses without touching the
        # network. The factory is a context-manager-compatible callable.
        self._client_factory = httpx.Client

    # ------------------------------------------------------------------ public

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome:
        began = time.monotonic()
        prompt_version = self._read_prompt_version()
        model_version = self._model_version()

        # A malformed prompt configuration must still produce an auditable
        # needs_review outcome rather than escaping as a ValidationError
        # (empty version) or UnicodeDecodeError into the worker's failure
        # path. Checked before the gates so the cause is always recorded.
        if self._prompt_load_error is not None:
            return self._needs_review(
                request,
                reason=self._prompt_load_error,
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:prompt-malformed",),
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

        # Origin trust boundary: live-origin input is refused unless the
        # operator explicitly opted in. Reachable only when the skeleton
        # gate is open, so live traffic can never reach the model while
        # this batch ships with the gate closed.
        if request.origin != "synthetic" and not self._allow_live_origin:
            return self._needs_review(
                request,
                reason=(
                    "LLM provider refuses live-origin input until "
                    "GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1 is set. See "
                    "case-009-llm-live-origin-refused in the "
                    "evaluation manifest."
                ),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:origin-live-refused",),
            )

        # Reachable only with both gates open *and* a complete
        # configuration; the real implementation returns typed
        # needs_review outcomes on failure instead of raising.
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

        Gate 1 — the implementation gate — runs first. It is open
        (:attr:`_SKELETON_SEAM` is ``False``) because :meth:`_invoke_model`
        performs the real call; it only closes again if a build ships with an
        unimplemented ``_invoke_model``, in which case every call is refused
        with ``llm:seam-pending`` so no outbound network request can happen.
        With the gate open, configuration is checked before the operator gate
        so an unconfigured deployment keeps the descriptive
        ``llm:not-configured`` reason, and the operator gate is a positive
        opt-in: while ``GIGMATE_LLM_LIVE`` is off the provider refuses every
        call with ``llm:live-gate-off``, even when the vendor and model are
        configured. Only when the configuration is complete *and* both
        gates are open does ``propose`` continue to the origin check and
        :meth:`_invoke_model`.
        """
        if self._SKELETON_SEAM:
            return (
                "llm:seam-pending",
                "gigmate.extraction.llm.LLMProvider._SKELETON_SEAM is True, "
                "meaning _invoke_model is not implemented in this build. "
                "Every call — gate on or off, configured or not — returns "
                "needs_review with llm:seam-pending so no outbound network "
                "request is made.",
            )
        if not self._configured_provider or not self._configured_model:
            return (
                "llm:not-configured",
                "LLM provider is not configured; set GIGMATE_LLM_PROVIDER and "
                "GIGMATE_LLM_MODEL (and GIGMATE_LLM_API_KEY) before live "
                "calls are allowed.",
            )
        if not self._configured_live:
            return (
                "llm:live-gate-off",
                "GIGMATE_LLM_LIVE=1 is required before the LLM seam is "
                "invoked; the provider refuses every call while the live "
                "gate is off - even when GIGMATE_LLM_PROVIDER/GIGMATE_LLM_MODEL "
                "are configured - so a misconfigured deployment cannot "
                "silently fall back to a real model call.",
            )
        if not self._is_wired_for_live():
            return (
                "llm:not-configured",
                "GIGMATE_LLM_LIVE=1 is set but gigmate.extraction.llm is not "
                "wired for live calls (missing GIGMATE_LLM_API_KEY, or the "
                "vendor GIGMATE_LLM_PROVIDER is not supported by this build). "
                "Refusing the call instead of silently falling back.",
            )
        if self._resolve_endpoint() is None:
            return (
                "llm:not-configured",
                f"Vendor {self._configured_provider!r} has no default endpoint "
                "in this build; set GIGMATE_LLM_ENDPOINT to the "
                "OpenAI-compatible base URL before live calls are allowed. "
                "Refusing rather than guessing a vendor URL with a real "
                "credential.",
            )
        if self._configured_model in _JSON_MODE_UNSUPPORTED_MODELS:
            return (
                "llm:model-unsupported",
                f"Model {self._configured_model!r} does not support "
                "response_format=json_object, which this provider needs in "
                "order to parse a ChangeProposal. Use a JSON-output-capable "
                "model (for DeepSeek: deepseek-chat).",
            )
        if request.origin == "live":
            if not request.message_received_at or not request.workspace_timezone:
                return (
                    "llm:time-basis-missing",
                    "Live extraction requires the server-attached message "
                    "time and the workspace timezone before relative dates "
                    "can be resolved. Refusing instead of guessing a time "
                    "basis.",
                )
            if not self._account_authorized(request.account_id):
                return (
                    "llm:account-not-authorized",
                    "This account is not in GIGMATE_LLM_LIVE_ACCOUNTS; explicit "
                    "per-account authorization is required before live "
                    "content is sent to the model.",
                )
            return self._budget_refusal(request)
        return None

    def _account_authorized(self, account_id: str) -> bool:
        configured = (os.environ.get(_LIVE_ACCOUNTS_ENV) or "").strip()
        if not configured:
            return True
        allowed = {item.strip() for item in configured.split(",") if item.strip()}
        return account_id in allowed

    def _budget_refusal(self, request: ExtractionRequest) -> tuple[str, str] | None:
        """Refuse a live call whose attached daily budget is missing or spent.

        The worker attaches counters read from durable traces; this method
        only compares numbers, so the provider stays database-free.
        """
        if request.budget_call_limit is None and request.budget_token_limit is None:
            return (
                "llm:budget-not-configured",
                "Live extraction requires an explicit daily budget: set "
                "GIGMATE_LLM_DAILY_CALL_BUDGET and/or "
                "GIGMATE_LLM_DAILY_TOKEN_BUDGET. Refusing to run unmetered.",
            )
        if (
            request.budget_call_limit is not None
            and request.budget_calls_used >= request.budget_call_limit
        ):
            return (
                "llm:budget-exhausted",
                f"Daily call budget reached ({request.budget_calls_used}/"
                f"{request.budget_call_limit}); no vendor request was made.",
            )
        if (
            request.budget_token_limit is not None
            and request.budget_tokens_used >= request.budget_token_limit
        ):
            return (
                "llm:budget-exhausted",
                f"Daily token budget reached ({request.budget_tokens_used}/"
                f"{request.budget_token_limit}); no vendor request was made.",
            )
        return None

    def _resolve_endpoint(self) -> str | None:
        """Resolve the OpenAI-compatible base URL for the configured vendor.

        An explicit ``GIGMATE_LLM_ENDPOINT`` always wins. Without it the URL
        follows the vendor so an OpenAI key is never sent to
        ``api.deepseek.com``; ``custom`` has no default and returns ``None``,
        which ``_refusal_reason`` turns into ``llm:not-configured``.
        """
        override = (self._configured_endpoint or "").strip()
        if override:
            return override.rstrip("/")
        if self._configured_provider == "openai":
            return _OPENAI_DEFAULT_ENDPOINT
        if self._configured_provider == "deepseek":
            return _DEEPSEEK_DEFAULT_ENDPOINT
        return None

    def _is_wired_for_live(self) -> bool:
        """Whether the live gate has everything it needs to make a real call."""
        if not (self._configured_provider and self._configured_model):
            return False
        if self._configured_provider not in _KNOWN_VENDORS:
            return False
        if not os.environ.get(_API_KEY_ENV):
            return False
        return True

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
        """Return the prompt version header from the configured prompt file.

        Reads the first line that starts with ``prompt_version:`` (stripped).
        Every failure mode — missing file, OS error, non-UTF-8 bytes, missing
        header line, empty header value — falls back to
        :data:`_PROMPT_VERSION_PENDING` and sets
        :attr:`_prompt_load_error` to a descriptive string. ``propose()``
        reads that attribute and surfaces the cause as an
        ``llm:prompt-malformed`` outcome so the worker still persists a
        Proposal + ModelCallTrace (with the placeholder prompt version).

        The override path (``GIGMATE_LLM_PROMPT_PATH``) is honoured the same
        way as the bundled file; both must be UTF-8.
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
                        f"{_PROMPT_VERSION_PREFIX} header; treating the file "
                        "as malformed and falling back to "
                        f"{_PROMPT_VERSION_PENDING}."
                    )
                    return _PROMPT_VERSION_PENDING
        except OSError as exc:
            self._prompt_load_error = (
                f"LLM prompt file {path} could not be opened: {exc}. "
                f"Falling back to {_PROMPT_VERSION_PENDING}."
            )
            return _PROMPT_VERSION_PENDING
        except UnicodeDecodeError as exc:
            self._prompt_load_error = (
                f"LLM prompt file {path} is not valid UTF-8 "
                f"({type(exc).__name__}: {exc}). Falling back to "
                f"{_PROMPT_VERSION_PENDING}."
            )
            return _PROMPT_VERSION_PENDING
        self._prompt_load_error = (
            f"LLM prompt file {path} has no {_PROMPT_VERSION_PREFIX} header "
            f"line. Falling back to {_PROMPT_VERSION_PENDING}."
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
        usage: dict | None = None,
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
            usage=usage,
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

        For OpenAI-compatible vendors (deepseek / openai / custom) this POSTs
        to ``{endpoint}/v1/chat/completions`` with the loaded prompt as the
        system message and the request as the user message, then parses the
        response into a :class:`ChangeProposal`. Any failure (HTTP error,
        invalid JSON, schema mismatch) is returned as a ``needs_review``
        outcome with a typed note so the worker still records evidence.
        """
        api_key = os.environ.get(_API_KEY_ENV)
        try:
            prompt_body = self._load_prompt_body()
        except OSError as exc:
            return self._needs_review(
                request,
                reason=f"LLM prompt file could not be loaded: {exc}",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:prompt-load-failed",),
            )
        endpoint = self._resolve_endpoint()
        if endpoint is None:
            # Unreachable through ``propose`` (``_refusal_reason`` checks the
            # endpoint first); kept so a direct call can never fall back to a
            # guessed vendor URL with a real credential attached.
            return self._needs_review(
                request,
                reason=(
                    f"Vendor {self._configured_provider!r} has no default "
                    "endpoint; set GIGMATE_LLM_ENDPOINT before live calls."
                ),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:not-configured",),
            )
        try:
            raw, usage = self._call_chat_completion(
                endpoint=endpoint,
                api_key=api_key or "",
                model=self._configured_model or "",
                prompt_body=prompt_body,
                request=request,
            )
        except LLMResultUnknown as exc:
            # The request may have been submitted and charged. Record the
            # uncertainty, never resubmit behind the operator's back.
            return self._needs_review(
                request,
                reason=(
                    "LLM call result is unknown "
                    f"({exc.kind}); it may have been charged and is not "
                    "retried automatically."
                ),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:result-unknown",),
            )
        except httpx.HTTPError as exc:
            return self._needs_review(
                request,
                reason=_sanitised_http_reason(exc),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:http-failed",),
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return self._needs_review(
                request,
                reason=(
                    "LLM response did not contain a chat-completions result (response-malformed)."
                ),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-malformed",),
            )
        return self._parse_response(raw, request, began, prompt_version, model_version, usage=usage)

    def _load_prompt_body(self) -> str:
        """Read the bundled (or override) prompt file as UTF-8 text."""
        return self._prompt_path.read_text(encoding="utf-8")

    def _call_chat_completion(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        prompt_body: str,
        request: ExtractionRequest,
    ) -> tuple[str, dict | None]:
        """POST to ``{endpoint}/v1/chat/completions``; return ``(content, usage)``.

        ``usage`` is the vendor's token accounting normalised to
        ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``, or
        ``None`` when the vendor omitted it. A real call therefore leaves
        auditable cost evidence behind instead of discarding it.

        Retries once, and only when the vendor definitely did not start work:
        a failed TCP connect and the status codes in
        :data:`_RETRYABLE_STATUS_CODES` (request timeout, rate limit). A read
        timeout, a dropped connection, a 5xx or a non-JSON body may already
        have been charged, so they raise :class:`LLMResultUnknown` instead of
        being repeated; auth and bad-request responses are deterministic and
        fail on the first response. The
        :class:`httpx.Client` is created through ``self._client_factory`` so
        tests can inject a fake client without monkeypatching ``httpx``
        globally.
        """
        url = endpoint.rstrip("/") + "/v1/chat/completions"
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt_body},
                {"role": "user", "content": self._render_user_message(request)},
            ],
            # DeepSeek / OpenAI both honour json_object mode; this is what
            # makes ``_parse_response`` reliable.
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        def _retry_after(attempt: int, kind: str) -> bool:
            if attempt >= _MAX_RETRIES:
                return False
            _log.warning(
                "LLM call attempt %d/%d failed (%s); retrying",
                attempt + 1,
                _MAX_RETRIES + 1,
                kind,
            )
            time.sleep(_RETRY_BACKOFF_S * (attempt + 1))
            return True

        for attempt in range(_MAX_RETRIES + 1):
            try:
                with self._client_factory(timeout=_REQUEST_TIMEOUT_S) as client:
                    response = client.post(url, json=body, headers=headers)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # No connection was established, so the vendor cannot have
                # processed (or charged) the request: one retry is safe.
                if _retry_after(attempt, "connect"):
                    continue
                raise LLMResultUnknown("connect") from exc
            except httpx.HTTPStatusError as exc:
                # Some transports surface a status before ``raise_for_status``.
                if exc.response.status_code in _RETRYABLE_STATUS_CODES and _retry_after(
                    attempt, f"status-{exc.response.status_code}"
                ):
                    continue
                raise
            except httpx.TimeoutException as exc:
                # The request may have been written before the read timed out.
                raise LLMResultUnknown("timeout") from exc
            except httpx.HTTPError as exc:
                raise LLMResultUnknown("transport") from exc
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _RETRYABLE_STATUS_CODES and _retry_after(
                    attempt, f"status-{exc.response.status_code}"
                ):
                    continue
                raise
            try:
                data = response.json()
            except ValueError as exc:
                # A body that is not JSON after a 2xx was still charged and
                # must not be retried.
                raise KeyError("response-json") from exc
            return (
                data["choices"][0]["message"]["content"],
                _normalise_usage(data.get("usage")),
            )
        # Unreachable: every path above returns, continues, or raises.
        raise LLMResultUnknown("retry-exhausted")  # pragma: no cover

    @staticmethod
    def _render_user_message(request: ExtractionRequest) -> str:
        """Render the request as the user-role JSON the prompt expects.

        ``message_received_at`` and ``workspace_timezone`` are the server's
        time basis for relative dates. Message identity is deliberately not
        sent: the provider re-binds ``sources`` locally, so the model cannot
        choose which message a change is attributed to.
        """
        return json.dumps(
            {
                "message_text": request.message_text,
                "message_received_at": request.message_received_at,
                "workspace_timezone": request.workspace_timezone,
                "context_version": request.context_version,
                "candidate_work_order_ids": list(request.candidate_work_order_ids),
                "base_work_order_version": request.base_work_order_version,
                "base_work_order_snapshot": request.base_work_order_snapshot,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _bind_provenance(data: dict, request: ExtractionRequest) -> str | None:
        """Bind identity fields to the server-issued request.

        The model may echo whatever it likes; the server decides which
        conversation, work order, version and message a proposal belongs to.
        Returns the name of the first field that contradicts the request, or
        ``None`` after the data has been rewritten with trusted values.
        """
        data["conversation_id"] = request.conversation_id
        data["base_context_version"] = request.context_version

        candidates = {str(item) for item in request.candidate_work_order_ids}
        listed = data.get("candidates")
        if isinstance(listed, list):
            for candidate in listed:
                if not isinstance(candidate, dict):
                    return "candidates"
                if str(candidate.get("work_order_id")) not in candidates:
                    return "candidates"

        matched = data.get("assignment") == "matched"
        if not matched:
            data["work_order_id"] = None
            data["base_work_order_version"] = None
        else:
            chosen = data.get("work_order_id")
            if chosen is not None and str(chosen) not in candidates:
                return "work_order_id"
            if len(candidates) == 1:
                data["work_order_id"] = request.candidate_work_order_ids[0]
            model_version = data.get("base_work_order_version")
            if request.base_work_order_version is not None:
                if model_version is not None and model_version != request.base_work_order_version:
                    return "base_work_order_version"
                data["base_work_order_version"] = request.base_work_order_version

        changes = data.get("changes")
        if isinstance(changes, list):
            for change in changes:
                if isinstance(change, dict):
                    # The server binds every change to the exact message
                    # revision that produced it; a model-supplied source is
                    # never trusted.
                    change["sources"] = [
                        {
                            "message_id": request.message_id,
                            "message_revision": request.message_revision,
                        }
                    ]
        return None

    def _parse_response(
        self,
        raw: str | object,
        request: ExtractionRequest,
        began: float,
        prompt_version: str,
        model_version: str,
        *,
        usage: dict | None = None,
    ) -> ExtractionOutcome:
        """Parse the LLM's JSON response into a :class:`ChangeProposal`.

        The LLM is asked to emit JSON only (DeepSeek json_object mode), but
        we still validate strictly against the contract because prompt
        injection or model drift could yield a structurally valid JSON that
        does not match :class:`ChangeProposal`. Any validation error is
        returned as a ``needs_review`` outcome with
        ``llm:response-schema-failed`` so the worker still records evidence.

        ``usage`` carries the token accounting of the call that produced this
        response. It is propagated even on parse failures: the vendor charged
        for those tokens, so the trace must show them.
        """
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return self._needs_review(
                request,
                reason="LLM response was not valid JSON (response-malformed).",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-malformed",),
                usage=usage,
            )
        if not isinstance(data, dict):
            return self._needs_review(
                request,
                reason="LLM response must be a JSON object (response-malformed).",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-malformed",),
                usage=usage,
            )
        # Force provider-set fields so the LLM cannot override them.
        data["model_version"] = model_version
        data["prompt_version"] = prompt_version
        data.setdefault("schema_version", "0.1.0")
        data.setdefault("proposal_id", str(uuid4()))
        data.setdefault("draft_text", None)
        if data.get("assignment") == "needs_review":
            data.setdefault("changes", [])
            data.setdefault("candidates", [])
            if not data.get("unresolved_questions"):
                reason_text = data.get("reason")
                data["unresolved_questions"] = [
                    str(reason_text) if reason_text else "LLM requested review"
                ]
        mismatch = self._bind_provenance(data, request)
        if mismatch is not None:
            return self._needs_review(
                request,
                reason=(
                    "LLM response did not bind to the request's provenance "
                    f"({mismatch}); it is recorded as evidence and cannot "
                    "create an actionable change."
                ),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:provenance-mismatch",),
                usage=usage,
            )
        try:
            proposal = ChangeProposal.model_validate(data)
        except ValidationError as exc:
            return self._needs_review(
                request,
                reason=(
                    "LLM response did not match ChangeProposal "
                    f"(response-schema-failed at {exc.errors()[0]['loc']})."
                ),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-schema-failed",),
                usage=usage,
            )
        if proposal.assignment.value == "matched":
            return ExtractionOutcome(
                provider_name=self.name,
                proposal=proposal,
                latency_ms=self._elapsed(began),
                notes=("llm:matched",),
                refused_reason=None,
                usage=usage,
            )
        # LLM explicitly asked for review; pass through with a typed note so
        # the worker records evidence.
        return ExtractionOutcome(
            provider_name=self.name,
            proposal=proposal,
            latency_ms=self._elapsed(began),
            notes=("llm:needs-review",),
            refused_reason="llm:needs-review",
            usage=usage,
        )


__all__ = ["LLMProvider", "LLMIntegrationPending", "LLMResultUnknown"]
