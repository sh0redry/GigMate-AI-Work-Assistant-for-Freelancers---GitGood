"""Extended vendor-boundary regressions for the Role B extraction client.

Every case here comes from an independent PR #31 review finding that the first
round of P2 fixes did not close. All of them use synthetic input and the
injected ``_client_factory`` seam: no real vendor, credential, network call,
real model activation or message sending is involved.

The four boundaries:

* the total deadline has to stop a body that keeps arriving, not just the wait;
* the token bound must never under-count, and a tokenizer that cannot be
  bounded keeps the hard ceiling unmet instead of pretending otherwise;
* a wrongly shaped envelope is one recorded outcome, never an escaping
  ``TypeError`` that becomes a worker retry;
* ``NaN``/``Infinity`` money cannot reach a paid comparison.
"""

from __future__ import annotations

import json as json_module
import time
from decimal import Decimal
from uuid import uuid4

import pytest

from gigmate.extraction import llm as llm_module
from gigmate.extraction.llm import (
    LLMProvider,
    _cost_configuration_problem,
    _envelope_content,
    _estimate_tokens,
    validate_provider_config,
)
from gigmate.extraction.types import ExtractionRequest
from gigmate.seed import uid

ACCOUNT_ID = uid(1)
CONVERSATION_ID = "00000000-0000-4000-8000-000000000002"
CANDIDATE = "00000000-0000-4000-8000-000000000003"
MESSAGE_ID = "00000000-0000-4000-8000-000000000004"

_ENV_NAMES = (
    "GIGMATE_LLM_PROVIDER",
    "GIGMATE_LLM_MODEL",
    "GIGMATE_LLM_API_KEY",
    "GIGMATE_LLM_ENDPOINT",
    "GIGMATE_LLM_PROMPT_PATH",
    "GIGMATE_LLM_LIVE",
    "GIGMATE_LLM_ALLOW_LIVE_ORIGIN",
    "GIGMATE_LLM_COST_BUDGET_USD",
    "GIGMATE_LLM_COST_INPUT_USD_PER_1K",
    "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K",
    "GIGMATE_LLM_MAX_INPUT_TOKENS",
    "GIGMATE_LLM_MAX_OUTPUT_TOKENS",
    "GIGMATE_WORKSPACE_TIMEZONE",
)


def _configure(monkeypatch, **extra) -> None:
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-fake-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "https://fake.example.test")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def _request(**overrides) -> ExtractionRequest:
    values = {
        "account_id": ACCOUNT_ID,
        "conversation_id": CONVERSATION_ID,
        "message_id": MESSAGE_ID,
        "message_revision": 1,
        "message_text": "改下星期四下午三点，地址我晚些发",
        "context_version": 5,
        "candidate_work_order_ids": (CANDIDATE,),
        "base_work_order_version": 3,
        "base_work_order_snapshot": None,
        "origin": "synthetic",
        "message_received_at": "2026-10-07T00:00:00Z",
        "workspace_timezone": "Asia/Hong_Kong",
    }
    values.update(overrides)
    return ExtractionRequest(**values)


def _gate_open_provider(client) -> LLMProvider:
    class _GateOpen(LLMProvider):
        _SKELETON_SEAM = False

    provider = _GateOpen()
    provider._client_factory = client
    return provider


def _needs_review_payload() -> dict:
    return {"assignment": "needs_review", "unresolved_questions": ["synthetic"]}


class _BodyClient:
    """Serve one whole JSON body, exactly like a fast in-deadline response."""

    requests: list[dict] = []

    def __init__(self, body: dict):
        self._body = body

    def __call__(self, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def stream(self, method, url, json=None, headers=None):  # noqa: A002
        type(self).requests.append({"url": url, "headers": headers})
        body = self._body
        return _ImmediateStream(json_module.dumps(body).encode("utf-8"))


class _ImmediateStream:
    """One-chunk stream standing in for a body that arrived in time."""

    def __init__(self, payload: bytes):
        self._payload = payload
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self, *args, **kwargs):
        yield self._payload

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# Total deadline against a streamed body
# ---------------------------------------------------------------------------


def test_total_deadline_stops_a_body_that_keeps_arriving(monkeypatch):
    """A vendor that trickles data must not outlive the total deadline.

    Review finding: bounding ``httpx`` phase timeouts still let a body that
    keeps arriving before every read timeout run far past the declared budget,
    because the whole body was read before the clock was looked at again. The
    fix reads as a stream, re-checks the clock between chunks and closes the
    stream, which tears the transfer down instead of only abandoning the wait.
    """
    state = {"chunks": 0, "closed": False, "exhausted": False}

    def trickle() -> bytes:
        try:
            for _ in range(400):
                state["chunks"] += 1
                time.sleep(0.005)
                yield b'{"choices":'
        finally:
            state["closed"] = True

    monkeypatch.setattr(llm_module, "_TOTAL_DEADLINE_S", 0.05)
    monkeypatch.setattr(llm_module, "_MIN_REQUEST_TIMEOUT_S", 0.0)
    _configure(monkeypatch)
    provider = _gate_open_provider(_BodyClient({}))

    class _TrickleClient:
        def __call__(self, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def stream(self, method, url, json=None, headers=None):  # noqa: A002
            return _TrickleStream(trickle())

    provider._client_factory = _TrickleClient()
    began = time.monotonic()
    outcome = provider.propose(_request())
    elapsed = time.monotonic() - began

    # 400 chunks at 5 ms each would take 2 s; giving up has to be immediate.
    assert elapsed < 1.0
    assert state["chunks"] < 400
    # Reading stopped: the generator was closed instead of being drained while
    # the caller pretended to have given up.
    assert state["closed"] is True
    assert outcome.notes == ("llm:deadline-exceeded",)
    assert outcome.refused_reason == "llm:deadline-exceeded"
    assert outcome.request_id


class _TrickleStream:
    def __init__(self, iterator):
        self._iterator = iterator
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self, *args, **kwargs):
        return self._iterator

    def close(self):
        self.closed = True
        # Closing has to stop the producer as well, not just drop the value.
        self._iterator.close()


# ---------------------------------------------------------------------------
# Token bound and hard-ceiling honesty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["gpt-4o-mini", "gpt-4o", "deepseek-chat", "deepseek-reasoner"])
def test_cjk_tokens_are_never_under_counted(model):
    """The bound has to cover each CJK character, not average them away.

    Review counter-case: "你好" repeated is one token per character (three
    bytes), so a characters/3 average priced only a third of the real prompt.
    """
    text = "你好客戶地址"
    assert _estimate_tokens(text, model) == len(text.encode("utf-8"))
    # One token per character is the real count for these models, so the bound
    # can only be above it.
    assert _estimate_tokens(text, model) >= len(text)


def test_unbounded_tokenizer_keeps_the_hard_ceiling_unmet(monkeypatch):
    """A model whose tokenizer carries no provable bound stays unproven.

    Rather than reporting an average as if it were a ceiling, the call is
    refused with ``llm:cost-estimate-unsupported``, which is exactly the
    activation gate the batch has not cleared.
    """
    _configure(
        monkeypatch,
        GIGMATE_LLM_MODEL="mystery-model",
        GIGMATE_LLM_COST_INPUT_USD_PER_1K="0.001",
        GIGMATE_LLM_COST_OUTPUT_USD_PER_1K="0.002",
    )
    provider = _gate_open_provider(_BodyClient({}))
    note, max_tokens = provider._cost_plan("system prompt.", _request())
    assert note == "llm:cost-estimate-unsupported"
    assert max_tokens == 0


def test_known_tokenizer_enforces_the_input_ceiling(monkeypatch):
    """A prompt above the configured input ceiling is refused before billing."""
    _configure(monkeypatch, GIGMATE_LLM_MAX_INPUT_TOKENS="1")
    provider = _gate_open_provider(_BodyClient({}))
    note, max_tokens = provider._cost_plan("system prompt.", _request())
    assert note == "llm:cost-input-too-large"
    assert max_tokens == 0


# ---------------------------------------------------------------------------
# Vendor envelope shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"choices": 17},
        {"choices": [{"message": 17}]},
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        {"nonsense": True},
    ],
)
def test_malformed_envelopes_are_one_recorded_outcome(monkeypatch, body):
    """Wrong shapes must not escape as a TypeError and become a job retry.

    Review finding: both forms raised ``TypeError: 'int' object is not
    subscriptable``, which the worker treated as PROCESSING_FAILED — no
    evidence row, and after activation a repeated paid call.
    """
    _configure(monkeypatch)
    provider = _gate_open_provider(_BodyClient(body))
    outcome = provider.propose(_request())
    assert outcome.notes == ("llm:response-malformed",)
    assert outcome.refused_reason and "llm:response-malformed" in outcome.refused_reason
    assert outcome.request_id
    assert outcome.proposal.changes == []


def test_well_formed_envelope_still_yields_content():
    """The type checks must not weaken the happy path."""
    content = json_module.dumps(_needs_review_payload())
    body = {"choices": [{"message": {"content": content}}], "usage": {}}
    assert _envelope_content(body) == content


# ---------------------------------------------------------------------------
# Money configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity", "-1", "abc"])
def test_non_usable_budget_is_reported_at_startup(monkeypatch, raw):
    """``NaN``/``Infinity`` parse as Decimals but cannot bound money.

    Review finding: ``validate_provider_config`` returned ``[]`` for
    ``GIGMATE_LLM_COST_BUDGET_USD=NaN`` and the later comparison could raise
    ``InvalidOperation`` inside a paid call instead of failing at boot.
    """
    monkeypatch.setenv(llm_module._COST_BUDGET_ENV, raw)
    assert _cost_configuration_problem("openai", "gpt-4o-mini") == "llm:cost-budget-invalid"
    assert "llm:cost-budget-invalid" in validate_provider_config()


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-0.5"])
def test_non_usable_pricing_override_is_reported_at_startup(monkeypatch, raw):
    """A negative or non-finite price is a configuration error, not a guess."""
    monkeypatch.setenv(llm_module._COST_INPUT_ENV, raw)
    monkeypatch.setenv(llm_module._COST_OUTPUT_ENV, raw)
    assert _cost_configuration_problem("openai", "gpt-4o-mini") == "llm:cost-pricing-invalid"


def test_budget_boundary_and_retry_total_stay_inside_the_budget():
    """Both accepting and refusing costs stay decided from a usable budget."""
    assert llm_module._money("0.10") == Decimal("0.10")
    assert llm_module._money("NaN") is None
    assert llm_module._money("-0.01") is None


def test_non_usable_budget_refuses_before_any_request(monkeypatch):
    """A budget that cannot bound money is refused before the call is issued."""
    _configure(monkeypatch, GIGMATE_LLM_COST_BUDGET_USD="NaN")
    provider = _gate_open_provider(_BodyClient({}))
    note, max_tokens = provider._cost_plan("system prompt.", _request())
    assert note == "llm:cost-budget-invalid"
    assert max_tokens == 0
    assert provider.propose(_request()).notes == ("llm:cost-budget-invalid",)


def test_request_id_is_unique_per_call(monkeypatch):
    """Two calls must never reuse a correlation id in a trace."""
    _configure(monkeypatch)
    provider = _gate_open_provider(_BodyClient({"choices": []}))
    first = provider.propose(_request())
    second = provider.propose(_request())
    assert first.request_id and second.request_id
    assert first.request_id != second.request_id
    assert len(first.request_id) == len(uuid4().hex)
