"""Real-model extraction provider (skeleton seam).

This module is the non-emitting seam for the separately authorized real-model
integration batch. The default vendor is DeepSeek, but any OpenAI-compatible
vendor (``deepseek``/``openai``/``custom``) is supported in the call shape
so the next batch only has to flip :attr:`LLMProvider._SKELETON_SEAM`.
The provider never makes an outbound network call until both gates are open:

1. The class flag :attr:`LLMProvider._SKELETON_SEAM` is ``False`` (the next
   batch sets it once the seam is no longer a stub).
2. ``GIGMATE_LLM_LIVE=1`` is exported (the explicit operator switch).

Both gates must be open. While the skeleton flag is ``True`` every call —
operator gate on or off, configured or not — is refused with ``needs_review``
and an ``llm:seam-pending`` note so a misconfigured production deployment
cannot silently route real customer messages through an LLM. Once the flag
is lifted, a missing configuration surfaces as ``llm:not-configured`` and a
closed operator gate as ``llm:live-gate-off``. Live-origin input is
additionally refused unless ``GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`` is exported.

Configuration (environment variables):

- ``GIGMATE_LLM_PROVIDER`` - vendor name (``deepseek`` / ``openai`` /
  ``custom``). Used in ``model_version`` and as a sanity check that the
  operator picked a vendor this build actually supports.
- ``GIGMATE_LLM_MODEL`` - model identifier passed to the chat-completions
  call (e.g. ``deepseek-chat``, ``deepseek-reasoner``, ``gpt-4o-mini``).
- ``GIGMATE_LLM_API_KEY`` - server-side only. Read on each call, never
  stored on the instance, never logged.
- ``GIGMATE_LLM_ENDPOINT`` - base URL override. Each known vendor ships its
  own documented default endpoint (``deepseek`` → ``https://api.deepseek.com``,
  ``openai`` → ``https://api.openai.com``); ``custom`` has no default and
  requires this variable. An override that equals another vendor's default
  endpoint is refused so a worker can never quietly call the wrong vendor.
- ``GIGMATE_LLM_PROMPT_PATH`` - optional override of the bundled prompt
  file (defaults to the versioned file in this package).
- ``GIGMATE_LLM_LIVE=1`` - the explicit operator gate. Required to reach
  :meth:`_invoke_model` once the skeleton flag is flipped.
- ``GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`` - opt-in switch that lets
  ``request.origin == "live"`` traffic reach the model. Defaults to off.

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
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

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

_PROMPT_VERSION_PENDING = "0.0.0-skeleton"
_MODEL_VERSION_PENDING = "skeleton:pending"

# OpenAI-compatible vendors this build actually knows how to call. The
# ``custom`` vendor exists so operators can point at a private deployment of
# an OpenAI-compatible API (vLLM, TGI, etc.) without code changes.
_KNOWN_VENDORS = frozenset({"deepseek", "openai", "custom"})

# Pre-activation gate 2: every known vendor ships its own documented default
# endpoint so ``GIGMATE_LLM_PROVIDER`` can never silently route a call to
# another vendor's service. ``custom`` deliberately has no default — the
# operator must supply ``GIGMATE_LLM_ENDPOINT`` explicitly.
_VENDOR_DEFAULT_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com",
}
_DEEPSEEK_DEFAULT_ENDPOINT = _VENDOR_DEFAULT_ENDPOINTS["deepseek"]

# Network hygiene: bound the *per-attempt* request time and the *total* wall
# time a single extraction may spend in the vendor call (pre-activation gate
# 3). The total budget is what protects the worker's row lock and lease: a
# retry is only issued when the remaining budget still allows it.
_REQUEST_TIMEOUT_S = 30.0
_TOTAL_DEADLINE_S = 45.0
_MAX_RETRIES = 1

# Header carrying the persistent correlation id (gate 3). The same value is
# persisted on the ``model_call_traces`` row so an operator can match a trace
# to the vendor's own request log.
_REQUEST_ID_HEADER = "X-Gigmate-Request-Id"

_log = logging.getLogger(__name__)


def _is_transient(exc: BaseException) -> bool:
    """Whether a vendor-call failure is worth one bounded retry (gate 3).

    Only clearly transient classes are retried: connection/reset failures,
    timeouts and ``5xx`` responses. Parse, schema and ``4xx`` failures are
    deterministic — retrying them only doubles cost and latency for the same
    outcome, and a ``4xx`` retry can resend a rejected payload.
    """
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.ReadError, httpx.WriteError)):
        return True
    if isinstance(exc, httpx.RemoteProtocolError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _stable_http_code(exc: BaseException) -> str:
    """Map a transport failure to a stable, secret-free diagnostic code.

    Pre-activation gate 5: exception class names and messages can carry the
    private endpoint path, the vendor name and key fragments, so nothing
    free-form is echoed back. Only the failure *class* (and, for an HTTP
    status, the coarse status bucket) is reported.
    """
    if isinstance(exc, httpx.TimeoutException):
        return "llm:http-failed:timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        bucket = "5xx" if exc.response.status_code >= 500 else "4xx"
        return f"llm:http-failed:status-{bucket}"
    if isinstance(exc, httpx.ConnectError):
        return "llm:http-failed:connect"
    if isinstance(exc, (httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError)):
        return "llm:http-failed:transport"
    if isinstance(exc, httpx.HTTPError):
        return "llm:http-failed:transport"
    return "llm:http-failed:unknown"


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
    """Real-model extraction provider (DeepSeek / OpenAI-compatible seam).

    Two gates run in front of :meth:`_invoke_model`, in order:

    1. The class flag :attr:`_SKELETON_SEAM` — the always-closed skeleton
       gate. While it is ``True`` the provider refuses every request with
       ``assignment: needs_review`` and an ``llm:seam-pending`` note,
       regardless of which environment variables are exported. This is what
       keeps this batch from making outbound network calls no matter how the
       operator configures it, and keeps the next batch from silently
       flipping into "real call" mode by only filling in
       :meth:`_invoke_model`.
    2. ``GIGMATE_LLM_LIVE=1`` — the operator gate. Once the skeleton flag is
       lifted, a closed operator gate still refuses every call with
       ``llm:live-gate-off`` and a missing or unsupported configuration with
       ``llm:not-configured``.

    Only when both gates are open and the configuration is complete does
    control reach the origin check and :meth:`_invoke_model`, which performs
    the real OpenAI-compatible chat-completions call through
    ``self._client_factory``.
    """

    # Safety gate #1. The next authorized batch flips this to ``False``
    # together with the real implementation of ``_invoke_model``; until
    # then it stays ``True`` so the off-switch (``GIGMATE_LLM_LIVE``) and
    # the on-switch cases both refuse at the provider layer rather than
    # entering the network call path.
    _SKELETON_SEAM: bool = True

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

        Gate 1 — the always-closed skeleton seam — runs first: while
        :attr:`_SKELETON_SEAM` is ``True`` every call (operator gate on or
        off, configured or not) is refused with ``llm:seam-pending`` so no
        outbound network request can happen in this batch. Once the flag is
        lifted, configuration is checked before the operator gate so an
        unconfigured deployment keeps the descriptive ``llm:not-configured``
        reason, and the operator gate is a positive opt-in: while
        ``GIGMATE_LLM_LIVE`` is off the provider refuses every call with
        ``llm:live-gate-off``, even when the vendor and model are
        configured. Only when the configuration is complete *and* both
        gates are open does ``propose`` continue to the origin check and
        :meth:`_invoke_model`.
        """
        if self._SKELETON_SEAM:
            return (
                "llm:seam-pending",
                "gigmate.extraction.llm.LLMProvider is still the skeleton "
                "seam (_SKELETON_SEAM=True). The next authorized batch must "
                "set _SKELETON_SEAM=False together with the real "
                "_invoke_model implementation. Until then every call — gate "
                "on or off, configured or not — returns needs_review with "
                "llm:seam-pending so no outbound network request is made.",
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
                "silently fall back to a real model call once _invoke_model "
                "is implemented.",
            )
        # Gate 2 runs before the credential check so an unknown vendor is
        # reported as such instead of being folded into ``not-configured``.
        endpoint_problem = self._endpoint_problem()
        if endpoint_problem is not None:
            return endpoint_problem
        if not self._is_wired_for_live():
            return (
                "llm:not-configured",
                "GIGMATE_LLM_LIVE=1 is set but gigmate.extraction.llm is not "
                "wired for live calls (missing GIGMATE_LLM_API_KEY, or the "
                "vendor GIGMATE_LLM_PROVIDER is not supported by this build). "
                "Refusing the call instead of silently falling back.",
            )
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

    def _endpoint_problem(self) -> tuple[str, str] | None:
        """Pre-activation gate 2: refuse ambiguous vendor/endpoint combinations.

        Without this check a worker configured for one vendor could quietly
        call another vendor's service, because a bare ``GIGMATE_LLM_PROVIDER``
        value used to mean "use the DeepSeek default endpoint". The rules are:

        * an unknown vendor name is refused outright (it is never silently
          mapped onto a default endpoint);
        * ``custom`` has no default endpoint, so ``GIGMATE_LLM_ENDPOINT`` is
          mandatory;
        * an explicit override that equals another known vendor's documented
          default endpoint is refused, because that is exactly the
          misconfiguration this gate exists to catch.
        """
        vendor = self._configured_provider or ""
        if vendor not in _KNOWN_VENDORS:
            return (
                "llm:vendor-unknown",
                "GIGMATE_LLM_PROVIDER is not a vendor this build knows how to "
                "call; refusing instead of falling back to another vendor's "
                "default endpoint. Supported values: " + ", ".join(sorted(_KNOWN_VENDORS)) + ".",
            )
        override = (self._configured_endpoint or "").strip()
        default = _VENDOR_DEFAULT_ENDPOINTS.get(vendor)
        if override:
            if not (override.startswith("https://") or override.startswith("http://")):
                return (
                    "llm:endpoint-invalid",
                    "GIGMATE_LLM_ENDPOINT must be an absolute http(s) URL; "
                    "refusing the call instead of posting to an arbitrary "
                    "target.",
                )
            for other, other_default in _VENDOR_DEFAULT_ENDPOINTS.items():
                if other != vendor and override.rstrip("/") == other_default.rstrip("/"):
                    return (
                        "llm:vendor-endpoint-mismatch",
                        "GIGMATE_LLM_ENDPOINT points at another known vendor's "
                        "documented default endpoint while "
                        "GIGMATE_LLM_PROVIDER names a different vendor; "
                        "refusing the call rather than sending this "
                        "conversation to the wrong provider.",
                    )
            return None
        if default is None:
            return (
                "llm:endpoint-required",
                "GIGMATE_LLM_PROVIDER=custom has no built-in default endpoint; "
                "set GIGMATE_LLM_ENDPOINT before live calls are allowed.",
            )
        return None

    def _resolved_endpoint(self) -> str:
        """Return the endpoint the call will actually use (gate 2)."""
        override = (self._configured_endpoint or "").strip()
        if override:
            return override
        return _VENDOR_DEFAULT_ENDPOINTS.get(
            self._configured_provider or "", _DEEPSEEK_DEFAULT_ENDPOINT
        )

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
        request_id: str | None = None,
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
            request_id=request_id,
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
        except OSError:
            # Gate 5: the OSError message carries the prompt path, which is
            # deployment-private. Only the stable code is surfaced.
            return self._needs_review(
                request,
                reason="llm:prompt-load-failed: the configured prompt file "
                "could not be read as UTF-8 text.",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:prompt-load-failed",),
            )
        # Gate 3: one stable id per call, sent to the vendor and persisted so
        # the trace can be correlated with the vendor's own request log.
        request_id = uuid4().hex
        try:
            raw = self._call_chat_completion(
                endpoint=self._resolved_endpoint(),
                api_key=api_key or "",
                model=self._configured_model or "",
                prompt_body=prompt_body,
                request=request,
                request_id=request_id,
                began=began,
            )
        except httpx.HTTPError as exc:
            return self._needs_review(
                request,
                # Stable, secret-free code; see ``_stable_http_code``.
                reason=_stable_http_code(exc),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:http-failed",),
                request_id=request_id,
            )
        except (json.JSONDecodeError, KeyError, IndexError):
            return self._needs_review(
                request,
                reason="llm:response-malformed: the vendor response did not "
                "carry a usable chat-completions message body.",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-malformed",),
                request_id=request_id,
            )
        return self._parse_response(
            raw, request, began, prompt_version, model_version, request_id=request_id
        )

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
        request_id: str,
        began: float,
    ) -> str:
        """POST to ``{endpoint}/v1/chat/completions`` and return the raw assistant text.

        Pre-activation gate 3 shapes the retry policy:

        * the **total** wall time is bounded by :data:`_TOTAL_DEADLINE_S`, so a
          slow vendor cannot hold the worker's lock for the full per-attempt
          timeout plus an unbounded backoff;
        * only clearly transient failures are retried (see
          :func:`_is_transient`) — ``4xx``, parse and shape failures are
          deterministic and are raised immediately;
        * every attempt carries the same persistent ``request_id`` header so
          the trace row and the vendor's log can be correlated.
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
            _REQUEST_ID_HEADER: request_id,
        }
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                with self._client_factory(timeout=_REQUEST_TIMEOUT_S) as client:
                    response = client.post(url, json=body, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_exc = exc
                retryable = _is_transient(exc)
                remaining = _TOTAL_DEADLINE_S - (time.monotonic() - began)
                if attempt == _MAX_RETRIES or not retryable or remaining <= 0:
                    raise
                _log.warning(
                    "LLM call attempt %d/%d failed (%s); retrying within the "
                    "remaining %0.1fs budget",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    type(exc).__name__,
                    remaining,
                )
        # Unreachable: the loop either returns or raises on the last attempt.
        raise last_exc  # pragma: no cover

    @staticmethod
    def _time_basis(request: ExtractionRequest) -> tuple[dict | None, str | None]:
        """Return the date-grounding basis and, when unusable, a stable code.

        Pre-activation gate 4: relative dates ("明天", "下星期六", "next
        Thursday") are only meaningful against the moment the customer sent
        the message *and* the merchant's timezone. Both are server-attached;
        neither is inferred from the model's own "now". When either is absent
        or fails validation the call continues with ``time_basis`` set to
        ``null`` and ``relative_dates_allowed`` set to ``False``, and
        :meth:`_parse_response` refuses any schedule-bearing proposal.
        """
        received = request.message_received_at
        zone = request.workspace_timezone
        if not received or not zone:
            return None, None
        try:
            moment = datetime.fromisoformat(str(received).replace("Z", "+00:00"))
        except ValueError:
            return None, "llm:time-basis-invalid:received-at"
        if moment.tzinfo is None:
            return None, "llm:time-basis-invalid:received-at"
        try:
            ZoneInfo(zone)
        except (KeyError, ValueError, OSError):
            return None, "llm:time-basis-invalid:timezone"
        return (
            {
                "received_at": moment.astimezone(UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "timezone": zone,
            },
            None,
        )

    def _render_user_message(self, request: ExtractionRequest) -> str:
        """Render the request as the user-role JSON the prompt expects."""
        basis, _ = self._time_basis(request)
        return json.dumps(
            {
                "message_text": request.message_text,
                "context_version": request.context_version,
                "candidate_work_order_ids": list(request.candidate_work_order_ids),
                "base_work_order_version": request.base_work_order_version,
                "base_work_order_snapshot": request.base_work_order_snapshot,
                # Gate 4: the only reliable basis for relative dates. ``null``
                # means the model must not resolve them at all.
                "time_basis": basis,
                "relative_dates_allowed": basis is not None,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _provenance_problem(data: dict, request: ExtractionRequest) -> str | None:
        """Re-bind model-supplied identity fields to the issued request.

        Pre-activation gate 1: ``_parse_response`` used to accept an
        LLM-supplied ``work_order_id``, ``base_work_order_version``,
        ``conversation_id`` and ``sources`` without checking them against the
        request the server actually issued. A structurally valid response
        could therefore attach a proposal to a different work order, a stale
        version or another conversation's message. Every mismatch now
        surfaces as a stable ``llm:response-provenance-failed:<field>`` code
        and never as ``matched``.
        """
        if data.get("conversation_id") != request.conversation_id:
            return "llm:response-provenance-failed:conversation_id"
        if data.get("assignment") == "matched":
            chosen = data.get("work_order_id")
            if chosen not in request.candidate_work_order_ids:
                return "llm:response-provenance-failed:work_order_id"
            if data.get("base_work_order_version") != request.base_work_order_version:
                return "llm:response-provenance-failed:base_work_order_version"
        for change in data.get("changes") or []:
            if not isinstance(change, dict):
                return "llm:response-provenance-failed:change-shape"
            for source in change.get("sources") or []:
                if not isinstance(source, dict):
                    return "llm:response-provenance-failed:source-shape"
                if source.get("message_id") != request.message_id:
                    return "llm:response-provenance-failed:source-message-id"
                if source.get("message_revision") != request.message_revision:
                    return "llm:response-provenance-failed:source-message-revision"
        return None

    def _time_basis_problem(self, proposal, request: ExtractionRequest) -> str | None:
        """Refuse schedule values that were produced without a real basis.

        Pre-activation gate 4: without the connector's sending time and the
        merchant's timezone the model can only guess what "明天" or "next
        Thursday" means, and a guessed date is indistinguishable from a
        customer-confirmed one downstream. When the basis is missing (or
        fails validation) any date-bearing change is refused for review
        instead of being promoted.
        """
        basis, invalid = self._time_basis(request)
        if basis is not None:
            return None
        for change in proposal.changes:
            if change.field not in {"schedule", "deadline"}:
                continue
            for value in (change.old_value, change.new_value):
                kind = getattr(value, "kind", None)
                if kind is None and isinstance(value, dict):
                    kind = value.get("kind")
                if kind in {"timed", "date_only"}:
                    return invalid or "llm:time-basis-missing:schedule"
        return None

    def _parse_response(
        self,
        raw: str | object,
        request: ExtractionRequest,
        began: float,
        prompt_version: str,
        model_version: str,
        *,
        request_id: str | None = None,
    ) -> ExtractionOutcome:
        """Parse the LLM's JSON response into a :class:`ChangeProposal`.

        The LLM is asked to emit JSON only (DeepSeek json_object mode), but
        we still validate strictly against the contract because prompt
        injection or model drift could yield a structurally valid JSON that
        does not match :class:`ChangeProposal`. Any validation error is
        returned as a ``needs_review`` outcome with
        ``llm:response-schema-failed`` so the worker still records evidence.

        Structural validity is not business validity: pre-activation gate 1
        re-binds every identity the model echoes back to the request the
        server actually issued, and gate 4 refuses schedule values that were
        produced without a real time basis.
        """
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return self._needs_review(
                request,
                reason="llm:response-malformed:json",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-malformed",),
                request_id=request_id,
            )
        if not isinstance(data, dict):
            return self._needs_review(
                request,
                reason="llm:response-malformed:not-an-object",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-malformed",),
                request_id=request_id,
            )
        # Force provider-set fields so the LLM cannot override them.
        data["model_version"] = model_version
        data["prompt_version"] = prompt_version
        data.setdefault("schema_version", "0.1.0")
        data.setdefault("proposal_id", str(uuid4()))
        data.setdefault("conversation_id", request.conversation_id)
        data.setdefault("base_context_version", request.context_version)
        data.setdefault("draft_text", None)
        if data.get("assignment") == "needs_review":
            data.setdefault("changes", [])
            data.setdefault("candidates", [])
            if not data.get("unresolved_questions"):
                reason_text = data.get("reason")
                data["unresolved_questions"] = [
                    str(reason_text) if reason_text else "LLM requested review"
                ]
            data.setdefault("work_order_id", None)
            data.setdefault("base_work_order_version", None)
        # When exactly one candidate is known, default work_order_id and
        # base_work_order_version so the LLM cannot pick a wrong order or
        # leave the contract's conditional requirement unsatisfied.
        if data.get("assignment") == "matched" and len(request.candidate_work_order_ids) == 1:
            if not data.get("work_order_id"):
                data["work_order_id"] = request.candidate_work_order_ids[0]
            if (
                data.get("base_work_order_version") is None
                and request.base_work_order_version is not None
            ):
                data["base_work_order_version"] = request.base_work_order_version
        problem = self._provenance_problem(data, request)
        if problem is not None:
            return self._needs_review(
                request,
                reason=problem,
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-provenance-failed",),
                request_id=request_id,
            )
        try:
            proposal = ChangeProposal.model_validate(data)
        except ValidationError as exc:
            # Gate 5: surface the failing field path only. Pydantic messages
            # echo input fragments, which may contain customer text.
            first = exc.errors()[0]
            field_path = ".".join(str(part) for part in first.get("loc", ())) or "root"
            return self._needs_review(
                request,
                reason=f"llm:response-schema-failed:{field_path}",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-schema-failed",),
                request_id=request_id,
            )
        time_problem = self._time_basis_problem(proposal, request)
        if time_problem is not None:
            return self._needs_review(
                request,
                reason=time_problem,
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:time-basis-missing",),
                request_id=request_id,
            )
        if proposal.assignment.value == "matched":
            return ExtractionOutcome(
                provider_name=self.name,
                proposal=proposal,
                latency_ms=self._elapsed(began),
                notes=("llm:matched",),
                refused_reason=None,
                request_id=request_id,
            )
        # LLM explicitly asked for review; pass through with a typed note so
        # the worker records evidence.
        return ExtractionOutcome(
            provider_name=self.name,
            proposal=proposal,
            latency_ms=self._elapsed(began),
            notes=("llm:needs-review",),
            refused_reason="llm:needs-review",
            request_id=request_id,
        )


__all__ = ["LLMProvider", "LLMIntegrationPending"]
