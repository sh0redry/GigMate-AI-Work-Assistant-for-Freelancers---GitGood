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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from gigmate import secrets
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
# retry is only issued when the remaining budget still allows it, and every
# attempt inherits the *remaining* budget as its own timeout (see
# ``_call_chat_completion``) instead of unconditionally asking for the full
# per-attempt timeout again.
_REQUEST_TIMEOUT_S = 30.0
# Review fix P2-1 (second round). ``gigmate.worker`` leases a job for
# ``_WORKER_LEASE_S`` seconds and only renews it between processing steps, so
# an extraction allowed to run longer than the lease can still be in flight
# after another worker has legitimately reclaimed the same row. The total
# budget therefore has to fit *inside* the lease with room for the trace and
# proposal writes that follow the call, which is why it is 20 s and not the
# 45 s this module used to declare. ``test_extraction_gates`` asserts the
# relation instead of the literal.
_WORKER_LEASE_S = 30.0
_TOTAL_DEADLINE_S = 20.0
_MAX_RETRIES = 1
# An attempt that cannot be granted at least this much read budget is not
# issued at all: a request into a guaranteed timeout only holds the worker's
# lock and burns the deadline for no possible result.
_MIN_REQUEST_TIMEOUT_S = 1.0
# Review fix P2-1 (round 2): ``httpx`` applies one timeout value to *each*
# operation it performs, so a scalar timeout never bounded an attempt — a
# request that spent 30 s connecting and then 30 s reading was "within" a
# 30 s timeout and one extraction could run 60 s against the declared 45 s
# deadline. The remaining budget is therefore split across the operations
# (see :func:`_attempt_timeout`) so their **sum** cannot exceed it.
_CONNECT_TIMEOUT_S = 5.0
_WRITE_TIMEOUT_S = 5.0
_POOL_TIMEOUT_S = 1.0

# Header carrying the persistent correlation id (gate 3). The same value is
# persisted on the ``model_call_traces`` row so an operator can match a trace
# to the vendor's own request log.
_REQUEST_ID_HEADER = "X-Gigmate-Request-Id"

# Pre-activation cost accounting (batch 2). The seam is still closed, so
# these constants are part of the *next* authorized batch's contract; they
# exist now so the price table and the budget check can be unit-tested in
# isolation and so a future live deployment can flip the seam without
# touching this module's surface. While the seam stays closed no call ever
# reaches ``_compute_cost``; the helper is exercised by the cost test
# through a gate-open subclass.
_COST_INPUT_ENV = "GIGMATE_LLM_COST_INPUT_USD_PER_1K"
_COST_OUTPUT_ENV = "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K"
_COST_BUDGET_ENV = "GIGMATE_LLM_COST_BUDGET_USD"
_DEFAULT_COST_BUDGET_USD = "0.10"
# Token ceilings used to bound the worst case of a call *before* it is paid
# for (review fix P2-2). Without them the budget could only ever be checked
# after the vendor had already spent it.
_COST_MAX_INPUT_TOKENS_ENV = "GIGMATE_LLM_MAX_INPUT_TOKENS"
_COST_MAX_OUTPUT_TOKENS_ENV = "GIGMATE_LLM_MAX_OUTPUT_TOKENS"
# The ceilings are compared against :func:`_estimate_tokens`, which returns a
# *provable upper bound* (UTF-8 bytes), not a typical count. Codes with ASCII
# prompts cost roughly one token per four bytes and CJK roughly one token per
# three, so the input ceiling is sized for the bound and not for a token count:
# the 6.5 kB system prompt plus the request together stay under it, while an
# operator who lowers it still gets ``llm:cost-input-too-large`` rather than a
# silently truncated call.
_DEFAULT_MAX_INPUT_TOKENS = 16000
_DEFAULT_MAX_OUTPUT_TOKENS = 1000
# Review fix P2-2 (second round). A "characters / 3" rule is an average, not a
# bound: against the real tokenizer it under-counts CJK text badly (每 is one
# token and three bytes), and an under-count silently raises the real worst
# case above the ceiling the budget was computed from.
#
# For a byte-level BPE tokenizer every token covers at least one byte, so the
# UTF-8 byte count of a text is a *provable* upper bound on its token count.
# These are the vendor/model pairs whose tokenizer has that property; any other
# model cannot be bounded this way, so it must keep the hard ceiling as an
# unmet activation gate (``llm:cost-estimate-unsupported``) instead of having
# an estimate reported as a ceiling.
# The tokenizer belongs to the model, not to the vendor pair, so the bound is
# keyed on the model name and still applies when the same model is reached
# through a custom endpoint.
_BYTE_LEVEL_BPE_MODELS = frozenset({"deepseek-chat", "deepseek-reasoner", "gpt-4o-mini", "gpt-4o"})
# Role markers, separators and the json_object preamble of the two-message chat
# payload are not part of the rendered text but are still billed, so framing is
# charged separately instead of being ignored (review fix P2-2, second round).
_CHAT_FRAMING_TOKENS = 16

# Pre-activation gate 4 / review fix P2-5: the fields and the value kinds that
# carry a date, and therefore may only be produced against a real time basis.
# ``instant`` is the ``InstantDeadline`` shape ("明天交稿") and was the hole
# in the original guard.
_DATE_BEARING_FIELDS = frozenset({"schedule", "deadline"})
_DATE_BEARING_KINDS = frozenset({"timed", "date_only", "instant"})

# Best-effort default price list in USD per 1K tokens, keyed by
# (vendor, model). The values approximate the public price lists as of
# 2026-10 and are an upper bound for what a call should cost. An operator
# with a contract that differs (e.g. enterprise discount, custom model)
# sets ``GIGMATE_LLM_COST_INPUT_USD_PER_1K`` /
# ``GIGMATE_LLM_COST_OUTPUT_USD_PER_1K`` and the env override wins.
_PRICING_PER_1K: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("deepseek", "deepseek-chat"): (Decimal("0.00014"), Decimal("0.00028")),
    ("deepseek", "deepseek-reasoner"): (Decimal("0.00055"), Decimal("0.00219")),
    ("openai", "gpt-4o-mini"): (Decimal("0.00015"), Decimal("0.0006")),
    ("openai", "gpt-4o"): (Decimal("0.0025"), Decimal("0.01")),
}

_log = logging.getLogger(__name__)


def _now() -> float:
    """Monotonic wall clock used for every deadline and latency budget.

    Indirection exists so a test can inject a fake clock and prove the total
    deadline is really enforced (see the gate-3 deadline tests).
    """
    return time.monotonic()


class _TotalDeadlineExceeded(RuntimeError):
    """Raised when the total wall-clock budget of one extraction is gone.

    Gate 3 (review fix P2-1): the deadline is enforced before every attempt
    *and* against a response that only arrived after it. This is deliberately
    not an :class:`httpx.HTTPError`, so :func:`_is_transient` never retries
    it — retrying after the deadline can only hold the worker's lock longer.
    """


class _MalformedVendorResponse(RuntimeError):
    """Raised when a vendor payload is valid JSON but not a usable envelope.

    Review fix P2-6 (extended stable boundary). ``{"choices": 17}`` and
    ``{"choices": [{"message": 17}]}`` are legal JSON, so the old
    ``data["choices"][0]["message"]["content"]`` indexing raised a bare
    ``TypeError`` that escaped the vendor boundary: the worker turned it into a
    process failure and retry with no evidence row, which after activation is a
    repeated paid call. Every accessor is now type-checked and the failure is
    mapped to the stable note ``llm:response-malformed`` with its request id.
    """


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


def _attempt_timeout(remaining: float) -> httpx.Timeout | None:
    """Split ``remaining`` across the ``httpx`` operations of one attempt.

    Review fix P2-1 (round 2). ``httpx.Client(timeout=scalar)`` copies that
    scalar into *each* of connect / read / write / pool, so one request could
    legally spend the whole timeout on connecting and then the whole timeout
    again on reading — the declared ``_TOTAL_DEADLINE_S`` was only checked
    between attempts, never inside one, and a 30 s timeout plus a retry ran
    60 s. The remaining budget is now divided between the operations, so the
    largest wall time one attempt can spend is the remaining budget itself:

    * the fixed per-operation ceilings (:data:`_CONNECT_TIMEOUT_S`,
      :data:`_WRITE_TIMEOUT_S`, :data:`_POOL_TIMEOUT_S`) are capped further
      when the remaining budget is small;
    * the read budget is what is left after those three, still capped by
      :data:`_REQUEST_TIMEOUT_S`;
    * an attempt whose read budget would fall below
      :data:`_MIN_REQUEST_TIMEOUT_S` is not issued at all (``None``), because
      a request into a guaranteed timeout only holds the worker's lock.
    """
    if remaining <= 0:
        return None
    pool = min(_POOL_TIMEOUT_S, remaining / 10.0)
    connect = min(_CONNECT_TIMEOUT_S, remaining / 4.0)
    write = min(_WRITE_TIMEOUT_S, remaining / 4.0)
    read = min(_REQUEST_TIMEOUT_S, remaining - pool - connect - write)
    if read < _MIN_REQUEST_TIMEOUT_S:
        return None
    return httpx.Timeout(connect=connect, read=read, write=write, pool=pool)


def _timeout_budget_s(timeout: httpx.Timeout | float | None) -> float:
    """Return the largest wall time ``timeout`` can spend (its components' sum)."""
    if timeout is None:
        return 0.0
    if isinstance(timeout, httpx.Timeout):
        return sum(
            value
            for value in (
                timeout.connect,
                timeout.read,
                timeout.write,
                timeout.pool,
            )
            if value is not None
        )
    return float(timeout)


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


def _envelope_content(data: object) -> str:
    """Return the assistant content of a chat-completions envelope.

    Review fix P2-6. Every level is type-checked before it is subscripted:
    ``{"choices": 17}`` and ``{"choices": [{"message": 17}]}`` are legal JSON,
    and indexing them used to raise a bare ``TypeError`` that escaped to the
    worker. A ``TypeError`` here becomes :class:`_MalformedVendorResponse`, so
    the call ends as one recorded ``llm:response-malformed`` outcome rather
    than an unrecorded job failure that could be retried and paid for twice.
    """
    if not isinstance(data, dict):
        raise TypeError("envelope is not an object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TypeError("choices is not a non-empty array")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise TypeError("choice is not an object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise TypeError("message is not an object")
    content = message.get("content")
    if not isinstance(content, str):
        raise TypeError("message.content is not a string")
    return content


def _resolve_pricing(vendor: str, model: str) -> tuple[Decimal, Decimal] | None:
    """Return ``(input, output) USD per 1K tokens`` for ``(vendor, model)``.

    Pre-activation batch 2 (cost boundary). Operator-supplied env overrides
    take precedence and are validated as decimals; an unparseable override
    is treated as "no override" so the call falls through to the default
    table and reports a clean missing-pricing refusal instead of a
    half-configured state. ``None`` means the caller must refuse the call
    with :data:`llm:cost-pricing-missing` rather than silently guessing.
    """
    in_override = os.environ.get(_COST_INPUT_ENV)
    out_override = os.environ.get(_COST_OUTPUT_ENV)
    if in_override and out_override:
        try:
            return (Decimal(in_override), Decimal(out_override))
        except (InvalidOperation, ValueError):
            return _PRICING_PER_1K.get((vendor, model))
    return _PRICING_PER_1K.get((vendor, model))


def _compute_cost(
    input_tokens: int, output_tokens: int, vendor: str, model: str
) -> tuple[Decimal | None, str | None]:
    """Return ``(cost_usd, note)`` for one vendor call.

    ``note`` is non-``None`` only when pricing is missing for the configured
    vendor/model and the operator has not supplied per-1K overrides; the
    caller then refuses the call. Negative token counts are clamped to
    zero — vendors do not emit negative usage but a defensive clamp keeps
    a misbehaving client from producing a negative cost row.
    """
    safe_in = max(0, int(input_tokens))
    safe_out = max(0, int(output_tokens))
    pricing = _resolve_pricing(vendor, model)
    if pricing is None:
        return None, "llm:cost-pricing-missing"
    in_price, out_price = pricing
    cost = (Decimal(safe_in) / Decimal(1000)) * in_price + (
        Decimal(safe_out) / Decimal(1000)
    ) * out_price
    return cost.quantize(Decimal("0.000001")), None


def _money(raw: str) -> Decimal | None:
    """Return a usable non-negative amount, or ``None`` for anything else.

    Review fix P2-7. ``Decimal`` accepts ``NaN`` and ``Infinity`` as perfectly
    valid numbers, and comparing against them either answers nonsense or raises
    ``InvalidOperation`` inside a call that has already been paid for. Only a
    finite, non-negative amount can bound money; anything else is refused here
    *and* reported at startup by :func:`_cost_configuration_problem` rather
    than silently falling back to the default.
    """
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value < 0:
        return None
    return value


def _cost_budget() -> Decimal | None:
    """Return the per-call budget in USD, or ``None`` when it cannot bound money."""
    return _money(os.environ.get(_COST_BUDGET_ENV, _DEFAULT_COST_BUDGET_USD))


def _cost_budget_problem(cost: Decimal) -> str | None:
    """Return a stable code when ``cost`` overran the usable per-call budget."""
    budget = _cost_budget()
    if budget is None:
        return "llm:cost-budget-invalid"
    return "llm:cost-budget-exceeded" if cost > budget else None


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive-integer ceiling, falling back to ``default``."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _tokens_configuration_problem(env: Mapping[str, str] | None = None) -> str | None:
    """Return ``llm:cost-tokens-invalid`` for a non-positive token ceiling.

    Review fix P2-2: the pre-call ceiling is derived from these values, so a
    garbage or negative ceiling must be reported at startup instead of being
    silently replaced by the default.
    """
    get = (env or os.environ).get
    for name in (_COST_MAX_INPUT_TOKENS_ENV, _COST_MAX_OUTPUT_TOKENS_ENV):
        raw = get(name)
        if raw is None or not raw.strip():
            continue
        try:
            if int(raw) <= 0:
                return "llm:cost-tokens-invalid"
        except ValueError:
            return "llm:cost-tokens-invalid"
    return None


def _estimate_tokens(text: str | None, model: str | None = None) -> int | None:
    """Return a provable upper bound on the tokens ``text`` is billed for.

    Review fix P2-2 (second round). ``None`` means this tokenizer cannot be
    bounded here, so the caller must keep the hard ceiling as an unmet
    activation gate instead of reporting an estimate as a ceiling. For a
    byte-level BPE (see :data:`_BYTE_LEVEL_BPE_MODELS`) every token covers at
    least one byte, so the UTF-8 byte count can only ever over-count, and an
    over-count can only refuse a call, never under-fund its budget.
    """
    if not text:
        return 0
    if model is not None and model not in _BYTE_LEVEL_BPE_MODELS:
        return None
    return len(text.encode("utf-8"))


def _value_kind(value: object) -> str | None:
    """Return the contract ``kind`` of a field value, or ``None``."""
    if isinstance(value, dict):
        kind = value.get("kind")
        return kind if isinstance(kind, str) else None
    kind = getattr(value, "kind", None)
    return kind if isinstance(kind, str) else None


def _carries_a_date(value: object) -> bool:
    """Whether a date-bearing field value states a date (gate 4, round 2).

    A structured value states a date through its contract ``kind``; a scalar
    value (``str`` / ``int`` / ``float`` / ``bool``) states one whenever it is
    not ``None``, because the contract lets a ``deadline`` carry free text and
    "明天下午三点" is exactly the relative date the guard exists to stop.
    """
    if value is None:
        return False
    return _value_kind(value) in _DATE_BEARING_KINDS or isinstance(value, (str, int, float, bool))


def _cost_configuration_problem(
    vendor: str, model: str, env: Mapping[str, str] | None = None
) -> str | None:
    """Return a stable code when cost accounting cannot be performed.

    Pre-activation batch 2. The check is callable at startup (with an
    explicit ``env`` mapping for testability) and at call time (with
    ``os.environ``).     A non-``None`` return refuses the call rather than
    silently issuing an unpriceable request. The token ceilings that bound a
    call before it is paid for are validated here too, so a garbage ceiling
    is reported at startup instead of silently falling back to the default.
    """
    get = (env or os.environ).get
    tokens_problem = _tokens_configuration_problem(env=env)
    if tokens_problem is not None:
        return tokens_problem
    budget_raw = get(_COST_BUDGET_ENV, _DEFAULT_COST_BUDGET_USD)
    # Review fix P2-7: ``Decimal`` parses ``NaN`` and ``Infinity`` as numbers,
    # but neither can bound money — comparing against them either answers
    # nonsense or raises ``InvalidOperation`` inside a paid comparison. A
    # budget that cannot bound money is rejected at startup rather than later.
    budget = _money(budget_raw)
    if budget is None:
        return "llm:cost-budget-invalid"
    # Review fix P2-2 (round 2): a *negative* budget is nonsense and must be
    # reported at startup. A budget of exactly zero is left to ``_cost_plan``,
    # which refuses the call with ``llm:cost-budget-exceeded`` — "no money may
    # be spent" is a budget nothing fits into, not a malformed setting.
    in_override = get(_COST_INPUT_ENV)
    out_override = get(_COST_OUTPUT_ENV)
    if (in_override is None) != (out_override is None):
        return "llm:cost-pricing-partial"
    if in_override and out_override:
        if _money(in_override) is None or _money(out_override) is None:
            return "llm:cost-pricing-invalid"
        return None
    if not vendor or not model:
        return None  # not configured; the call will be refused elsewhere
    if (vendor, model) not in _PRICING_PER_1K:
        return "llm:cost-pricing-missing"
    return None


def validate_provider_config(
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Audit the LLM provider configuration and return a list of issue codes.

    Pre-activation batch 2. The helper is callable at API and worker boot
    time so a misconfigured deployment fails fast instead of silently
    issuing a wrong call when the seam is finally opened. Every entry is
    a stable, secret-free code (mirroring gate 5's sanitised diagnostic
    style); ``[]`` means the configuration is internally consistent.

    The check covers:

    * unknown vendor (``llm:vendor-unknown``)
    * a non-http(s) endpoint override (``llm:endpoint-invalid``)
    * an endpoint override that equals another known vendor's default
      (``llm:vendor-endpoint-mismatch``)
    * ``custom`` without an endpoint override (``llm:endpoint-required``)
    * an unparsable or non-existent prompt file
      (``llm:prompt-path-invalid``)
    * an invalid IANA workspace timezone
      (``workspace-timezone-invalid`` — operator-side, not vendor-side)
    * malformed / missing cost budget or pricing configuration
      (``llm:cost-budget-invalid`` / ``llm:cost-pricing-invalid`` /
      ``llm:cost-pricing-partial`` / ``llm:cost-pricing-missing``)
    * a non-positive input/output token ceiling
      (``llm:cost-tokens-invalid``)
    * a missing or empty API key when ``GIGMATE_LLM_LIVE=1``
      (``llm:api-key-missing``)

    Passing ``env`` lets tests drive the helper without touching the real
    environment.
    """
    get = (env or os.environ).get
    issues: list[str] = []
    vendor = (get(_PROVIDER_ENV) or "").strip()
    if vendor and vendor not in _KNOWN_VENDORS:
        issues.append("llm:vendor-unknown")
    endpoint = (get(_ENDPOINT_ENV) or "").strip()
    if endpoint:
        if not (endpoint.startswith("https://") or endpoint.startswith("http://")):
            issues.append("llm:endpoint-invalid")
        elif vendor in _KNOWN_VENDORS:
            for other, other_default in _VENDOR_DEFAULT_ENDPOINTS.items():
                if other != vendor and endpoint.rstrip("/") == other_default.rstrip("/"):
                    issues.append("llm:vendor-endpoint-mismatch")
                    break
    elif vendor == "custom":
        issues.append("llm:endpoint-required")
    prompt_path = get(_PROMPT_PATH_ENV)
    if prompt_path:
        path = Path(prompt_path)
        if not path.is_file():
            issues.append("llm:prompt-path-invalid")
        else:
            try:
                path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                issues.append("llm:prompt-path-invalid")
    zone = get("GIGMATE_WORKSPACE_TIMEZONE")
    if zone:
        try:
            ZoneInfo(zone)
        except (KeyError, ValueError, OSError):
            issues.append("workspace-timezone-invalid")
    cost_problem = _cost_configuration_problem(
        vendor,
        get(_MODEL_ENV) or "",
        env=env,
    )
    if cost_problem is not None:
        issues.append(cost_problem)
    if get(_LIVE_GATE) == "1" and not secrets.configured(_API_KEY_ENV):
        issues.append("llm:api-key-missing")
    return issues


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
        # ``_now`` (not ``time.monotonic`` directly) so the deadline basis used
        # to measure this call is the same clock the budget is checked against.
        began = _now()
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
        # Batch 2: refuse the call when its cost cannot be accounted for.
        # A call that cannot be priced cannot be bounded, so it must never
        # be issued — otherwise the first unlisted model would be the one
        # that quietly burns the monthly budget.
        cost_problem = _cost_configuration_problem(
            self._configured_provider or "", self._configured_model or ""
        )
        if cost_problem is not None:
            return (
                cost_problem,
                "LLM provider cannot account for the cost of this call "
                f"({cost_problem}); refusing instead of issuing an "
                "unbounded request. Set GIGMATE_LLM_COST_BUDGET_USD and, "
                "for a model outside the built-in price list, "
                "GIGMATE_LLM_COST_INPUT_USD_PER_1K / "
                "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K.",
            )
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
        if not secrets.configured(_API_KEY_ENV):
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
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        cost_note: str | None = None,
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
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            cost_note=cost_note,
        )

    @staticmethod
    def _elapsed(began: float) -> int:
        return max(0, int((_now() - began) * 1000))

    def _token_ceiling(self) -> tuple[int, int]:
        """Return ``(max_input_tokens, max_output_tokens)`` for one attempt."""
        return (
            _positive_int_env(_COST_MAX_INPUT_TOKENS_ENV, _DEFAULT_MAX_INPUT_TOKENS),
            _positive_int_env(_COST_MAX_OUTPUT_TOKENS_ENV, _DEFAULT_MAX_OUTPUT_TOKENS),
        )

    def _cost_plan(self, prompt_body: str, request: ExtractionRequest) -> tuple[str | None, int]:
        """Return ``(refusal_note, max_tokens)`` for one paid attempt.

        Review fix P2-2. The post-call check can only refuse a proposal whose
        money has already been spent, so the ceiling has to be enforced while
        the request is still ours to shape:

        * the budget covers *every* attempt of one extraction, so a single
          attempt may only spend its share of it;
        * a non-positive budget refuses every attempt outright — "no money may
          be spent" is not a budget a zero-priced worst case may fit into;
        * the worst case is the estimated input plus the configured output
          ceiling — a call whose worst case does not fit its share is never
          issued (``llm:cost-budget-exceeded``), and a prompt that is itself
          larger than the input ceiling is refused with
          ``llm:cost-input-too-large`` instead of being truncated;
        * the request carries that same output ceiling as ``max_tokens``, so
          the vendor is told the bound the budget was computed from and the
          post-call check can hold it to it.

        A ``None`` note means the call may be issued with the returned
        ``max_tokens``.
        """
        # Review fix P2-2 (round 2): a non-positive budget means no call may
        # be paid for, whatever the price list says. Checking it here (and not
        # only through the worst-case comparison below) is what stops a
        # zero-priced vendor from "fitting" a zero budget and reaching the
        # network.
        budget = _cost_budget()
        if budget is None:
            # Review fix P2-7: ``NaN``/``Infinity`` cannot bound money at all,
            # so nothing may be paid for.
            return "llm:cost-budget-invalid", 0
        if budget <= 0:
            return "llm:cost-budget-exceeded", 0
        pricing = _resolve_pricing(self._configured_provider or "", self._configured_model or "")
        if pricing is None:
            return "llm:cost-pricing-missing", 0
        in_price, out_price = pricing
        max_input, max_output = self._token_ceiling()
        per_attempt = budget / Decimal(_MAX_RETRIES + 1)
        model = self._configured_model or ""
        system_tokens = _estimate_tokens(prompt_body, model)
        user_tokens = _estimate_tokens(self._render_user_message(request), model)
        if system_tokens is None or user_tokens is None:
            # Review fix P2-2 (second round): this tokenizer has no provable
            # bound here, so the hard per-call ceiling stays an unmet
            # activation gate instead of being claimed as enforced.
            return "llm:cost-estimate-unsupported", 0
        # Chat framing is billed on top of the two rendered messages.
        estimated_input = system_tokens + user_tokens + _CHAT_FRAMING_TOKENS
        if estimated_input > max_input:
            return "llm:cost-input-too-large", 0
        input_cost = (Decimal(estimated_input) / Decimal(1000)) * in_price
        worst_case = input_cost + (Decimal(max_output) / Decimal(1000)) * out_price
        # The whole point of the check: if the bounded worst case of one
        # attempt does not fit its share of the budget, no money is spent.
        if worst_case > per_attempt:
            return "llm:cost-budget-exceeded", 0
        return None, max_output

    def _evaluate_cost(
        self, usage: dict | None
    ) -> tuple[Decimal | None, str | None, int | None, int | None]:
        """Return ``(cost, note, input_tokens, output_tokens)`` for one vendor call.

        Pre-activation batch 2. ``usage`` is the OpenAI-compatible token
        block from the vendor response. Three outcomes are possible:

        * ``usage`` is missing → no cost is known and ``cost_note`` is
          ``llm:cost-usage-missing``; the caller must not assume zero cost.
        * ``usage`` is present but the vendor/model has no price entry and
          the operator supplied no override → ``llm:cost-pricing-missing``.
        * otherwise the cost is computed from the token counts.
        """
        if usage is None:
            return None, "llm:cost-usage-missing", None, None
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            return None, "llm:cost-usage-invalid", None, None
        cost, note = _compute_cost(
            input_tokens,
            output_tokens,
            self._configured_provider or "",
            self._configured_model or "",
        )
        return cost, note, input_tokens, output_tokens

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

        Pre-activation batch 2 / review fix P2-2: the per-call budget
        (``GIGMATE_LLM_COST_BUDGET_USD``) is enforced **before** the paid
        request is issued as well as after it. ``_cost_plan`` prices the
        bounded worst case of one attempt and returns the ``max_tokens`` the
        vendor is told to respect; a call whose worst case does not fit its
        share of the budget is refused without spending anything. The
        post-call check remains as the second line of defence: a vendor that
        returns more tokens than it was allowed to produce is still refused
        with ``llm:cost-budget-exceeded``, and a response that omits
        ``usage`` is recorded with ``llm:cost-usage-missing`` rather than
        pretending a cost of zero.
        """
        api_key = secrets.secret(_API_KEY_ENV)
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
        # Review fix P2-2: bound the worst case before anything is paid for.
        refusal, max_tokens = self._cost_plan(prompt_body, request)
        if refusal is not None:
            return self._needs_review(
                request,
                reason=f"LLM provider refuses the call before it is issued "
                f"({refusal}); the bounded worst case does not fit the "
                "per-attempt share of GIGMATE_LLM_COST_BUDGET_USD, or the "
                "prompt exceeds GIGMATE_LLM_MAX_INPUT_TOKENS.",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=(refusal,),
            )
        # Gate 3: one stable id per call, sent to the vendor and persisted so
        # the trace can be correlated with the vendor's own request log.
        request_id = request.extra.get("request_id") or uuid4().hex
        try:
            raw, usage = self._call_chat_completion(
                endpoint=self._resolved_endpoint(),
                api_key=api_key or "",
                model=self._configured_model or "",
                prompt_body=prompt_body,
                request=request,
                request_id=request_id,
                began=began,
                max_tokens=max_tokens,
            )
        except _TotalDeadlineExceeded:
            # Review fix P2-1: the total wall-clock deadline is a hard
            # boundary, so a late success is refused exactly like a timeout.
            return self._needs_review(
                request,
                reason="llm:deadline-exceeded",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:deadline-exceeded",),
                request_id=request_id,
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
        except (json.JSONDecodeError, _MalformedVendorResponse, KeyError, IndexError):
            # Review fix P2-6: an unshaped envelope is one recorded outcome with
            # its request id, never a programming exception escaping to the worker.
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
        # Batch 2 / review fix P2-2: the post-call check is the *second*
        # line of defence. It still runs after the HTTP/parse gates because a
        # 4xx response never produces usage data and a parse failure cannot
        # be charged to a budget, but a call that reaches it has already been
        # bounded by ``_cost_plan`` before it was paid for, so what is left to
        # catch is a vendor that ignored the ``max_tokens`` it was given.
        cost, cost_note, input_tokens, output_tokens = self._evaluate_cost(usage)
        if cost is not None and _cost_budget_problem(cost) is not None:
            return self._needs_review(
                request,
                reason="llm:cost-budget-exceeded",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:cost-budget-exceeded",),
                request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=float(cost),
                cost_note="llm:cost-budget-exceeded",
            )
        return self._parse_response(
            raw,
            request,
            began,
            prompt_version,
            model_version,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=float(cost) if cost is not None else None,
            cost_note=cost_note,
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
        max_tokens: int,
    ) -> tuple[str, dict | None]:
        """POST to ``{endpoint}/v1/chat/completions`` and return ``(raw, usage)``.

        Pre-activation gate 3 shapes the retry policy, and the P2-1 review fix
        makes the total deadline an actual per-request budget:

        * the **total** wall time is bounded by :data:`_TOTAL_DEADLINE_S`, so a
          slow vendor cannot hold the worker's lock for the full per-attempt
          timeout plus an unbounded backoff. Each attempt is granted only the
          *remaining* budget, and that budget is split across the ``httpx``
          operations by :func:`_attempt_timeout` so the **sum** of connect /
          write / read / pool cannot exceed it — a scalar ``httpx`` timeout
          bounds each operation separately, which is how a 30 s timeout plus
          one retry used to run 60 s against the declared 45 s deadline;
        * an attempt whose read budget would fall below
          :data:`_MIN_REQUEST_TIMEOUT_S` is not issued, and a response
          that only arrives after the deadline is refused with
          :class:`_TotalDeadlineExceeded` — a late success is worthless once
          the worker's lease has run out;
        * only clearly transient failures are retried (see
          :func:`_is_transient`) — ``4xx``, parse and shape failures are
          deterministic and are raised immediately;
        * every attempt carries the same persistent ``request_id`` header so
          the trace row and the vendor's log can be correlated;
        * the request carries the budget-derived ``max_tokens`` (see
          :meth:`_cost_plan`) so the vendor is told the same bound the
          pre-call ceiling was computed from.

        The returned ``usage`` dict is the OpenAI-compatible
        ``{"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}``
        block from the vendor response when present, or ``None`` when the
        vendor omits it (some compatible servers and proxy deployments do).
        The caller uses it for the cost-accounting check; a missing block
        surfaces as ``llm:cost-usage-missing`` so the audit row records the
        cause instead of silently dropping the cost.
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
            # Review fix P2-2: the vendor is told the same output bound the
            # pre-call ceiling was computed from.
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            _REQUEST_ID_HEADER: request_id,
        }
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            # Review fix P2-1: the *remaining* total budget bounds this
            # attempt, and (round 2) that budget is split across the httpx
            # operations so their sum — not each one separately — is what is
            # granted. Without this the retry would ask for the full 30 s
            # again and a single attempt could spend it twice.
            remaining = _TOTAL_DEADLINE_S - (_now() - began)
            timeout = _attempt_timeout(remaining)
            if timeout is None:
                raise _TotalDeadlineExceeded()
            try:
                with self._client_factory(timeout=timeout) as client:
                    # Review fix P2-1 (second round). ``client.post`` bounded
                    # each *phase* (connect/read/write), not the request: a
                    # server that keeps sending a little before every read
                    # timeout could hold the worker's lease far past the
                    # declared deadline. The body is therefore read as a stream
                    # with the wall clock re-checked between chunks, and the
                    # stream is closed before giving up — closing tears down
                    # the transfer itself instead of only abandoning the wait.
                    with client.stream("POST", url, json=body, headers=headers) as response:
                        response.raise_for_status()
                        payload = bytearray()
                        for chunk in response.iter_bytes():
                            if len(payload) + len(chunk) > 512 * 1024:
                                raise _MalformedVendorResponse()
                            payload.extend(chunk)
                            if _now() - began > _TOTAL_DEADLINE_S:
                                response.close()
                                raise _TotalDeadlineExceeded()
                data = json.loads(bytes(payload))
                raw = _envelope_content(data)
                usage = data.get("usage")
                if not isinstance(usage, dict):
                    usage = None
                # A response that only arrived after the deadline is refused:
                # the worker's lease is gone, so promoting it would be the
                # same staleness bug the deadline exists to prevent.
                if _now() - began > _TOTAL_DEADLINE_S:
                    raise _TotalDeadlineExceeded()
                return raw, usage
            except (TypeError, ValueError, KeyError, IndexError) as exc:
                # Review fix P2-6: wrong shapes now leave the vendor boundary
                # as one typed error instead of a stray TypeError.
                raise _MalformedVendorResponse(str(exc)) from exc
            except _TotalDeadlineExceeded:
                raise
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_exc = exc
                retryable = _is_transient(exc)
                remaining = _TOTAL_DEADLINE_S - (_now() - began)
                if attempt == _MAX_RETRIES or not retryable or _attempt_timeout(remaining) is None:
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
    def _provenance_problem(data: dict, request: ExtractionRequest) -> tuple[str | None, bool]:
        """Re-bind model-supplied identity fields to the issued request.

        Returns ``(problem, rebound)``: ``problem`` is a stable refusal code or
        ``None``, and ``rebound`` marks that a source identifier the model
        supplied had to be replaced by the server's own value.

        Pre-activation gate 1: ``_parse_response`` used to accept an
        LLM-supplied ``work_order_id``, ``base_work_order_version``,
        ``conversation_id`` and ``sources`` without checking them against the
        request the server actually issued. A structurally valid response
        could therefore attach a proposal to a different work order, a stale
        version or another conversation's message. Every mismatch now
        surfaces as a stable ``llm:response-provenance-failed:<field>`` code
        and never as ``matched``.

        Review fix P2-3 also binds ``base_context_version``. The worker
        compares the database context version with ``request.context_version``
        but persistence then uses ``proposal.base_context_version``, so a
        model-supplied value survived the post-call check and reached the
        proposal; a later confirmation would then be refused for a context
        mismatch.

        Review fix P2-4: this runs *before* Pydantic, so every collection is
        type-checked before it is iterated. Legal JSON such as
        ``"changes": 17`` or ``"changes": true`` used to raise an uncaught
        ``TypeError`` out of ``propose``, which the worker would have turned
        into a job failure retry (paying for the same call twice) instead of
        the stable ``needs_review`` this module promises.
        """
        rebound = False
        if data.get("conversation_id") != request.conversation_id:
            return "llm:response-provenance-failed:conversation_id", rebound
        if data.get("assignment") == "matched":
            chosen = data.get("work_order_id")
            if chosen not in request.candidate_work_order_ids:
                return "llm:response-provenance-failed:work_order_id", rebound
            if data.get("base_work_order_version") != request.base_work_order_version:
                return "llm:response-provenance-failed:base_work_order_version", rebound
        # P2-3: the context version is server-owned; a different value is a
        # mismatch, not something to overwrite silently. Round 2 also refuses
        # an echoed value that is merely *equal* after coercion — ``7.0`` and
        # ``True`` compare equal to ``7`` / ``1`` in Python, and a value the
        # request did not send is still the model speaking about a version it
        # was never given.
        declared_context = data.get("base_context_version")
        if declared_context is not None:
            if not isinstance(declared_context, int) or isinstance(declared_context, bool):
                return "llm:response-provenance-failed:base_context_version", rebound
            if declared_context != request.context_version:
                return "llm:response-provenance-failed:base_context_version", rebound
        changes = data.get("changes")
        if changes is not None and not isinstance(changes, list):
            return "llm:response-provenance-failed:changes-shape", rebound
        for change in changes or []:
            if not isinstance(change, dict):
                return "llm:response-provenance-failed:change-shape", rebound
            sources = change.get("sources")
            if sources is not None and not isinstance(sources, list):
                return "llm:response-provenance-failed:source-shape", rebound
            if not sources:
                # A change with no source at all is still unbacked: refuse.
                return "llm:response-provenance-failed:source-missing", rebound
            for source in sources or []:
                if not isinstance(source, dict):
                    return "llm:response-provenance-failed:source-shape", rebound
                # Server-authoritative re-binding. The request carries exactly
                # one message and its revision, so any source can only ever be
                # that message. Real vendors echo the wrong identifier often —
                # observed live: DeepSeek wrote the *work order* id into
                # ``sources[].message_id`` on every proposal — which used to
                # fail the whole proposal with ``source-message-id``. Writing
                # the server's own value is stricter than trusting the echo and
                # keeps the proposal usable; a missing source is still refused.
                if source.get("message_id") != request.message_id:
                    rebound = True
                source["message_id"] = request.message_id
                source["message_revision"] = request.message_revision
        # P2-4 (round 2): every other collection the module reads is
        # type-checked here as well, before Pydantic sees it. A wrong shape is
        # then reported as a provenance code instead of a schema one, and no
        # code path iterates a value the model chose the type of.
        candidates = data.get("candidates")
        if candidates is not None and not isinstance(candidates, list):
            return "llm:response-provenance-failed:candidates-shape", rebound
        questions = data.get("unresolved_questions")
        if questions is not None and not isinstance(questions, list):
            return "llm:response-provenance-failed:unresolved-questions-shape", rebound
        # Batch 3: a new-work-order suggestion carries critical fields too, so
        # every suggested value is bound to the same source message that was
        # issued with this request. Without this check a compromised model could
        # quote a field from a message the merchant never saw.
        suggestion = data.get("new_work_order")
        if suggestion is not None:
            if not isinstance(suggestion, dict):
                return "llm:response-provenance-failed:new-work-order-shape", rebound
            fields = suggestion.get("fields")
            if fields is not None and not isinstance(fields, list):
                return "llm:response-provenance-failed:suggested-fields-shape", rebound
            for suggested in fields or []:
                if not isinstance(suggested, dict):
                    return "llm:response-provenance-failed:suggested-field-shape", rebound
                sources = suggested.get("sources")
                if sources is not None and not isinstance(sources, list):
                    return "llm:response-provenance-failed:suggested-source-shape", rebound
                if not sources:
                    return "llm:response-provenance-failed:suggested-source-missing", rebound
                for source in sources or []:
                    if not isinstance(source, dict):
                        return "llm:response-provenance-failed:suggested-source-shape", rebound
                    if source.get("message_id") != request.message_id:
                        rebound = True
                    source["message_id"] = request.message_id
                    source["message_revision"] = request.message_revision
            missing = suggestion.get("missing_fields")
            if missing is not None and not isinstance(missing, list):
                return "llm:response-provenance-failed:missing-fields-shape", rebound
            suggested_questions = suggestion.get("unresolved_questions")
            if suggested_questions is not None and not isinstance(suggested_questions, list):
                return "llm:response-provenance-failed:suggested-questions-shape", rebound
        return None, rebound

    def _time_basis_problem(self, proposal, request: ExtractionRequest) -> str | None:
        """Refuse schedule values that were produced without a real basis.

        Pre-activation gate 4: without the connector's sending time and the
        merchant's timezone the model can only guess what "明天" or "next
        Thursday" means, and a guessed date is indistinguishable from a
        customer-confirmed one downstream. When the basis is missing (or
        fails validation) any date-bearing change is refused for review
        instead of being promoted.

        Review fix P2-5: every date-bearing contract kind is covered. The
        check used to accept only ``timed`` / ``date_only`` and let
        ``InstantDeadline`` (``kind: instant``, the "明天交稿" shape) through
        untouched, so the most common relative date a customer types was the
        one the guard missed. Both the old and the new value are checked.

        Review fix P2-5 (round 2): the guard is keyed on the *field*, not only
        on the value shape. ``FieldValue`` also admits plain strings and
        numbers, so a model that wrote ``"明天下午三点"`` — or "2026-10-18"
        without a timezone — into a ``deadline`` / ``schedule`` change still
        produced a date the customer never stated, and the kind-based check
        let it through as ``matched``. Any non-null value on a date-bearing
        field now needs the basis; only a missing value (``None``, the
        "customer has not said yet" case) is exempt.
        """
        basis, invalid = self._time_basis(request)
        if basis is not None:
            return None
        for change in proposal.changes:
            if change.field not in _DATE_BEARING_FIELDS:
                continue
            for value in (change.old_value, change.new_value):
                if _carries_a_date(value):
                    return invalid or "llm:time-basis-missing:schedule"
        # Batch 3: the same rule guards a new-work-order suggestion. A relative
        # date inside a suggestion ("下星期三") is exactly as unfounded as one
        # inside a change when the basis is missing, and a guessed opening date
        # would be indistinguishable from a customer-stated one downstream.
        suggestion = proposal.new_work_order
        if suggestion is not None:
            for suggested in suggestion.fields:
                if suggested.field not in _DATE_BEARING_FIELDS:
                    continue
                if _carries_a_date(suggested.value):
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
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        cost_note: str | None = None,
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
        produced without a real time basis. The cost fields are threaded
        through so the trace always records what the call actually cost,
        even when the proposal is refused for another reason.
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
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                cost_note=cost_note,
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
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                cost_note=cost_note,
            )
        # Force provider-set fields so the LLM cannot override them.
        data["model_version"] = model_version
        data["prompt_version"] = prompt_version
        data.setdefault("schema_version", "0.1.0")
        data.setdefault("proposal_id", str(uuid4()))
        data.setdefault("conversation_id", request.conversation_id)
        data.setdefault("draft_text", None)
        if data.get("assignment") == "needs_review":
            data.setdefault("changes", [])
            data.setdefault("candidates", [])
            # Batch 3: a new-work-order suggestion carries its own
            # ``unresolved_questions``; do not pad the proposal-level list with
            # a filler sentence when the questions live inside the suggestion.
            if not data.get("unresolved_questions") and not data.get("new_work_order"):
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
        problem, rebound = self._provenance_problem(data, request)
        if problem is not None:
            return self._needs_review(
                request,
                reason=problem,
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:response-provenance-failed",),
                request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                cost_note=cost_note,
            )
        # P2-3: the context version is server-owned, so it is assigned after
        # the provenance guard (which has already refused a mismatching value)
        # and never left to whatever the model echoed back.
        data["base_context_version"] = request.context_version
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
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                cost_note=cost_note,
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
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                cost_note=cost_note,
            )
        # Observability, not trust: when the vendor echoed the wrong source
        # identifier the proposal still carries the server's value, and the
        # trace says so instead of hiding the correction.
        outcome_notes = ("llm:source-rebound",) if rebound else ()
        if proposal.assignment.value == "matched":
            return ExtractionOutcome(
                provider_name=self.name,
                proposal=proposal,
                latency_ms=self._elapsed(began),
                notes=("llm:matched", *outcome_notes),
                refused_reason=None,
                request_id=request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                cost_note=cost_note,
            )
        # LLM explicitly asked for review; pass through with a typed note so
        # the worker records evidence.
        return ExtractionOutcome(
            provider_name=self.name,
            proposal=proposal,
            latency_ms=self._elapsed(began),
            notes=("llm:needs-review", *outcome_notes),
            refused_reason="llm:needs-review",
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            cost_note=cost_note,
        )


__all__ = [
    "LLMProvider",
    "LLMIntegrationPending",
    "validate_provider_config",
]
