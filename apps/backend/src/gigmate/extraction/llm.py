"""Real-model extraction provider (skeleton seam).

This module is the non-emitting seam for the separately authorized real-model
integration batch. The default vendor is DeepSeek, but any OpenAI-compatible
vendor (``deepseek``/``openai``/``custom``) is supported in the call shape
so the next batch only has to flip :attr:`LLMProvider._SKELETON_SEAM` and
fill in :meth:`LLMProvider._invoke_model`. The provider never makes an
outbound network call until both gates are open:

1. The class flag :attr:`LLMProvider._SKELETON_SEAM` is ``False`` (the next
   batch sets it once the seam is no longer a stub).
2. ``GIGMATE_LLM_LIVE=1`` is exported (the explicit operator switch).

Both gates must be open. Turning the operator switch on while the skeleton
flag is still ``True`` is refused with ``needs_review`` and an
``llm:seam-pending`` note so a misconfigured production deployment cannot
silently route real customer messages through an LLM. Live-origin input is
additionally refused unless ``GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`` is exported.

Configuration (environment variables):

- ``GIGMATE_LLM_PROVIDER`` - vendor name (``deepseek`` / ``openai`` /
  ``custom``). Used in ``model_version`` and as a sanity check that the
  operator picked a vendor this build actually supports.
- ``GIGMATE_LLM_MODEL`` - model identifier passed to the chat-completions
  call (e.g. ``deepseek-chat``, ``deepseek-reasoner``, ``gpt-4o-mini``).
- ``GIGMATE_LLM_API_KEY`` - server-side only. Read on each call, never
  stored on the instance, never logged.
- ``GIGMATE_LLM_ENDPOINT`` - base URL override (defaults to
  ``https://api.deepseek.com``).
- ``GIGMATE_LLM_PROMPT_PATH`` - optional override of the bundled prompt
  file (defaults to the versioned file in this package).
- ``GIGMATE_LLM_LIVE=1`` - the explicit live gate. Required to actually
  invoke the model once the skeleton flag is flipped.
- ``GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`` - opt-in switch that lets
  ``request.origin == "live"`` traffic reach the model. Defaults to off.

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

_PROMPT_VERSION_PENDING = "0.0.0-skeleton"
_MODEL_VERSION_PENDING = "skeleton:pending"

# OpenAI-compatible vendors this build actually knows how to call. The
# ``custom`` vendor exists so operators can point at a private deployment of
# an OpenAI-compatible API (vLLM, TGI, etc.) without code changes.
_KNOWN_VENDORS = frozenset({"deepseek", "openai", "custom"})

# Default endpoint. DeepSeek is the default vendor; the endpoint matches the
# documented DeepSeek API base URL.
_DEEPSEEK_DEFAULT_ENDPOINT = "https://api.deepseek.com"

# Network hygiene: bound the request time and retry once on transient errors
# so a flaky network does not hang the worker thread.
_REQUEST_TIMEOUT_S = 30.0
_MAX_RETRIES = 1

_log = logging.getLogger(__name__)


class LLMIntegrationPending(RuntimeError):
    """Raised when a request must be refused at the provider layer.

    The provider raises this when the skeleton seam is still in place, when
    the live gate is off, when required configuration is missing or when the
    origin trust boundary blocks the input. :meth:`LLMProvider.propose`
    catches it and returns a ``needs_review`` outcome with the
    ``llm:seam-pending`` note so the worker still records evidence.
    """


class LLMProvider:
    """Real-model extraction provider (DeepSeek / OpenAI-compatible skeleton).

    The class flag :attr:`_SKELETON_SEAM` is the second gate in front of
    :meth:`_invoke_model`: while it is ``True``, the provider refuses every
    request with ``assignment: needs_review`` and an ``llm:seam-pending``
    note, regardless of which environment variables are exported. This is
    what keeps the next batch from silently flipping into "real call" mode
    by only filling in :meth:`_invoke_model` — both the skeleton flag and
    ``GIGMATE_LLM_LIVE=1`` must be open. The provider never makes outbound
    network calls until then; it only reads configuration and the bundled
    prompt file.
    """

    # Safety gate #1. The next authorized batch flips this to ``False``
    # together with the real implementation of ``_invoke_model``; until
    # then it stays ``True`` so the off-switch (``GIGMATE_LLM_LIVE``) and
    # the on-switch-but-unimplemented case both refuse at the provider
    # layer rather than entering the network call path.
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
        # Surface malformed/missing prompt files as a refused outcome BEFORE
        # the gate checks. ``_read_prompt_version`` never raises (it returns
        # the placeholder), but it records a descriptive cause so the worker
        # can persist an auditable ``ModelCallTrace``.
        if self._prompt_load_error is not None:
            return self._needs_review(
                request,
                reason=self._prompt_load_error,
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:prompt-malformed",),
            )
        try:
            reason = self._refusal_reason(request)
        except LLMIntegrationPending as exc:
            return self._needs_review(
                request,
                reason=str(exc),
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:seam-pending",),
            )
        if reason is not None:
            return self._needs_review(
                request,
                reason=reason,
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:not-configured",),
            )
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

    def _refusal_reason(self, request: ExtractionRequest) -> str | None:
        """Decide whether the call may proceed to :meth:`_invoke_model`.

        The two gates below run **before** :meth:`_invoke_model` is reached:

        1. :attr:`_SKELETON_SEAM` — class-level safety gate. While ``True``,
           the provider refuses every call regardless of the environment.
           This is what keeps the next batch from accidentally flipping into
           real-call mode by only filling in ``_invoke_model``.
        2. ``GIGMATE_LLM_LIVE=1`` — operator switch. Required to leave the
           skeleton state once the seam flag is open.

        Configuration mistakes (missing API key, unknown vendor) raise so the
        trace records a distinct cause. The function returns ``None`` only
        when both gates are open AND the configuration is complete; in this
        skeleton batch that branch is unreachable because gate 1 is closed.
        """
        if self._SKELETON_SEAM:
            raise LLMIntegrationPending(
                "gigmate.extraction.llm.LLMProvider is still the skeleton "
                "seam (_SKELETON_SEAM=True). The next authorized batch must "
                "set _SKELETON_SEAM=False together with the real "
                "_invoke_model implementation. Until then every call — gate "
                "on or off, configured or not — returns needs_review with "
                "llm:seam-pending so no outbound network request is made."
            )
        if not self._configured_live:
            raise LLMIntegrationPending(
                "GIGMATE_LLM_LIVE=1 is required to actually invoke the model. "
                "The provider refuses every call while the live gate is off, "
                "even when GIGMATE_LLM_PROVIDER/GIGMATE_LLM_MODEL are "
                "configured, so a misconfigured deployment cannot silently "
                "fall back to a real model call."
            )
        if not self._is_wired_for_live():
            raise LLMIntegrationPending(
                "GIGMATE_LLM_LIVE=1 is set but gigmate.extraction.llm is not "
                "wired for live calls (missing GIGMATE_LLM_API_KEY, or the "
                "vendor GIGMATE_LLM_PROVIDER is not supported by this build). "
                "Refusing the call instead of silently falling back."
            )
        if not self._configured_provider or not self._configured_model:
            return (
                "LLM provider is not configured; set GIGMATE_LLM_PROVIDER, "
                "GIGMATE_LLM_MODEL and GIGMATE_LLM_API_KEY before live calls."
            )
        if self._configured_provider not in _KNOWN_VENDORS:
            return (
                f"LLM vendor {self._configured_provider!r} is not supported by "
                f"this build; known vendors: {sorted(_KNOWN_VENDORS)}."
            )
        if not os.environ.get(_API_KEY_ENV):
            raise LLMIntegrationPending(
                f"GIGMATE_LLM_LIVE=1 is set but {_API_KEY_ENV} is not exported. "
                "Refusing the call instead of silently falling back."
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
        endpoint = self._configured_endpoint or _DEEPSEEK_DEFAULT_ENDPOINT
        try:
            raw = self._call_chat_completion(
                endpoint=endpoint,
                api_key=api_key or "",
                model=self._configured_model or "",
                prompt_body=prompt_body,
                request=request,
            )
        except httpx.HTTPError as exc:
            return self._needs_review(
                request,
                reason=f"LLM HTTP call failed: {type(exc).__name__}: {exc}",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:http-failed",),
            )
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            return self._needs_review(
                request,
                reason=f"LLM response was not valid JSON: {type(exc).__name__}: {exc}",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-malformed",),
            )
        return self._parse_response(raw, request, began, prompt_version, model_version)

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
    ) -> str:
        """POST to ``{endpoint}/v1/chat/completions`` and return the raw assistant text.

        Retries once on transient HTTP errors so a flaky network does not
        cause a missed extraction. The :class:`httpx.Client` is created
        through ``self._client_factory`` so tests can inject a fake client
        without monkeypatching ``httpx`` globally.
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
                if attempt == _MAX_RETRIES:
                    raise
                _log.warning(
                    "LLM call attempt %d/%d failed (%s); retrying",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    type(exc).__name__,
                )
        # Unreachable: the loop either returns or raises on the last attempt.
        raise last_exc  # pragma: no cover

    @staticmethod
    def _render_user_message(request: ExtractionRequest) -> str:
        """Render the request as the user-role JSON the prompt expects."""
        return json.dumps(
            {
                "message_text": request.message_text,
                "context_version": request.context_version,
                "candidate_work_order_ids": list(request.candidate_work_order_ids),
                "base_work_order_version": request.base_work_order_version,
                "base_work_order_snapshot": request.base_work_order_snapshot,
            },
            ensure_ascii=False,
        )

    def _parse_response(
        self,
        raw: str | object,
        request: ExtractionRequest,
        began: float,
        prompt_version: str,
        model_version: str,
    ) -> ExtractionOutcome:
        """Parse the LLM's JSON response into a :class:`ChangeProposal`.

        The LLM is asked to emit JSON only (DeepSeek json_object mode), but
        we still validate strictly against the contract because prompt
        injection or model drift could yield a structurally valid JSON that
        does not match :class:`ChangeProposal`. Any validation error is
        returned as a ``needs_review`` outcome with
        ``llm:response-schema-failed`` so the worker still records evidence.
        """
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            return self._needs_review(
                request,
                reason=f"LLM response was not valid JSON: {exc}",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-malformed",),
            )
        if not isinstance(data, dict):
            return self._needs_review(
                request,
                reason=f"LLM response must be a JSON object, got {type(data).__name__}",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-malformed",),
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
        try:
            proposal = ChangeProposal.model_validate(data)
        except ValidationError as exc:
            return self._needs_review(
                request,
                reason=f"LLM response did not match ChangeProposal: {exc.errors()[0]['msg']}",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-schema-failed",),
            )
        if proposal.assignment.value == "matched":
            return ExtractionOutcome(
                provider_name=self.name,
                proposal=proposal,
                latency_ms=self._elapsed(began),
                notes=("llm:matched",),
                refused_reason=None,
            )
        # LLM explicitly asked for review; pass through with a typed note so
        # the worker records evidence.
        return ExtractionOutcome(
            provider_name=self.name,
            proposal=proposal,
            latency_ms=self._elapsed(began),
            notes=("llm:needs-review",),
            refused_reason="llm:needs-review",
        )


__all__ = ["LLMProvider", "LLMIntegrationPending"]
