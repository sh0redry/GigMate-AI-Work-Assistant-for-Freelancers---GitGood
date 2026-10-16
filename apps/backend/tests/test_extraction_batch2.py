"""Role B pre-activation batch 2 acceptance suite.

Covers three deliverables listed in ``docs/en/role-b-extraction.md``
under "Batch 2" and the open follow-ups in the same file:

* cost boundary (per-call budget, price table, ``llm:cost-budget-exceeded``
  / ``llm:cost-pricing-missing`` / ``llm:cost-usage-missing`` / usage parsing);
* provider configuration startup validation
  (`:func:`gigmate.extraction.llm.validate_provider_config``);
* the prompt-injection regression suite shipped in
  ``contracts/evaluation/injection.json``.

Every test runs against a gate-open subclass of :class:`LLMProvider`, so the
``_SKELETON_SEAM`` stays closed and no network call, real credential, real
vendor or real model is involved.
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gigmate.db import Base, ModelCallTrace
from gigmate.extraction.llm import (
    _COST_BUDGET_ENV,
    _COST_INPUT_ENV,
    _COST_MAX_INPUT_TOKENS_ENV,
    _COST_MAX_OUTPUT_TOKENS_ENV,
    _COST_OUTPUT_ENV,
    _DEFAULT_MAX_OUTPUT_TOKENS,
    LLMProvider,
    _compute_cost,
    _cost_budget_problem,
    _cost_configuration_problem,
    _resolve_pricing,
    validate_provider_config,
)
from gigmate.extraction.persistence import persist_proposal
from gigmate.extraction.types import ExtractionRequest
from gigmate.seed import uid
from gigmate.worker import audit_provider_config

ACCOUNT_ID = uid(1)
CONVERSATION_ID = "00000000-0000-4000-8000-000000000002"
CANDIDATE = "00000000-0000-4000-8000-000000000003"
MESSAGE_ID = "00000000-0000-4000-8000-000000000004"

RECEIVED_AT = "2026-10-07T00:00:00Z"
TIMEZONE = "Asia/Hong_Kong"

# ``contracts/evaluation/injection.json`` is the data source for the
# regression suite. The path is resolved from the repository root so the
# test can be run from any working directory.
REPO_ROOT = Path(__file__).resolve().parents[3]
INJECTION_MANIFEST = REPO_ROOT / "contracts" / "evaluation" / "injection.json"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _StreamedResponse:
    """Adapt a post-style fake response to the streaming production reader.

    ``_call_chat_completion`` reads the body with ``client.stream(...)`` and
    re-checks the total deadline between chunks, so a test double that only
    answers ``post`` no longer describes a real vendor client. The helper keeps
    the existing fakes meaningful: one whole body arrives as one chunk, exactly
    like a response that fits inside the deadline.
    """

    def __init__(self, response):
        self._response = response
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def raise_for_status(self):
        return self._response.raise_for_status()

    def iter_bytes(self, *args, **kwargs):
        yield json.dumps(self._response.json()).encode("utf-8")

    def close(self):
        self.closed = True


def _env(monkeypatch) -> None:
    """Clear every LLM provider env var so each test starts from a known state."""
    for name in (
        "GIGMATE_LLM_PROVIDER",
        "GIGMATE_LLM_MODEL",
        "GIGMATE_LLM_API_KEY",
        "GIGMATE_LLM_ENDPOINT",
        "GIGMATE_LLM_PROMPT_PATH",
        "GIGMATE_LLM_LIVE",
        "GIGMATE_LLM_ALLOW_LIVE_ORIGIN",
        "GIGMATE_WORKSPACE_TIMEZONE",
        _COST_BUDGET_ENV,
        _COST_INPUT_ENV,
        _COST_OUTPUT_ENV,
        _COST_MAX_INPUT_TOKENS_ENV,
        _COST_MAX_OUTPUT_TOKENS_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def _configure(monkeypatch, *, vendor: str = "openai", model: str = "gpt-4o-mini", **extra) -> None:
    """Set the minimum environment required to open the seam in a test."""
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", vendor)
    monkeypatch.setenv("GIGMATE_LLM_MODEL", model)
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-fake-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "https://fake.example.test")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def _scripted_client(raw: dict, *, usage: dict | None = None, status_code: int = 200):
    """Fake ``httpx`` client that returns ``raw`` as the assistant text.

    The optional ``usage`` block is what an OpenAI-compatible vendor puts
    in the response body; the LLM provider parses it for the cost check.
    """

    class _Response:
        def __init__(self):
            self.status_code = status_code

        def raise_for_status(self):
            if status_code >= 400:
                request = httpx.Request("POST", "https://fake.example.test/v1/chat/completions")
                raise httpx.HTTPStatusError("bad status", request=request, response=self)

        def json(self):
            body = {"choices": [{"message": {"content": json.dumps(raw)}}]}
            if usage is not None:
                body["usage"] = usage
            return body

    class _Client:
        requests: list[dict] = []

        def __init__(self, **kwargs):
            self.timeout = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, json=None, headers=None):
            type(self).requests.append({"url": url, "json": json, "headers": headers})
            return _Response()

        def stream(self, method, url, json=None, headers=None):
            return _StreamedResponse(self.post(url, json=json, headers=headers))

    return _Client


def _boom_client():
    class _Boom:
        def __init__(self, *args, **kwargs):
            raise AssertionError("no vendor call may be issued")

    return _Boom


def _gate_open_provider(client):
    class _GateOpen(LLMProvider):
        _SKELETON_SEAM = False

    provider = _GateOpen()
    provider._client_factory = client
    return provider


def _grounded_request(**overrides) -> ExtractionRequest:
    values = {
        "account_id": ACCOUNT_ID,
        "conversation_id": CONVERSATION_ID,
        "message_id": MESSAGE_ID,
        "message_revision": 1,
        "message_text": "改下星期四下午三点，地址我晚些发",
        "context_version": 5,
        "candidate_work_order_ids": (CANDIDATE,),
        "base_work_order_version": 3,
        "base_work_order_snapshot": {
            "id": CANDIDATE,
            "version": 3,
            "fields": {
                "schedule": {
                    "value": {
                        "kind": "timed",
                        "start_at": "2026-10-07T07:00:00Z",
                        "end_at": "2026-10-07T08:00:00Z",
                        "timezone": TIMEZONE,
                    }
                }
            },
        },
        "message_received_at": RECEIVED_AT,
        "workspace_timezone": TIMEZONE,
        "origin": "synthetic",
    }
    values.update(overrides)
    return ExtractionRequest(**values)


def _matched_schedule_payload(**overrides) -> dict:
    payload = {
        "assignment": "matched",
        "work_order_id": CANDIDATE,
        "base_work_order_version": 3,
        "candidates": [{"work_order_id": CANDIDATE, "confidence": 1.0}],
        "changes": [
            {
                "field": "schedule",
                "old_value": None,
                "new_value": {
                    "kind": "timed",
                    "start_at": "2026-10-08T07:00:00Z",
                    "end_at": "2026-10-08T08:00:00Z",
                    "timezone": TIMEZONE,
                },
                "field_status": "proposed",
                "customer_confirmation": "pending",
                "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
                "reason": "Customer asked to move the appointment.",
            }
        ],
        "unresolved_questions": [],
        "draft_text": None,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Section A - cost accounting (batch 2 cost boundary)
# ---------------------------------------------------------------------------


def test_resolve_pricing_uses_default_table(monkeypatch):
    monkeypatch.delenv(_COST_INPUT_ENV, raising=False)
    monkeypatch.delenv(_COST_OUTPUT_ENV, raising=False)
    pricing = _resolve_pricing("deepseek", "deepseek-chat")
    assert pricing == (Decimal("0.00014"), Decimal("0.00028"))


def test_resolve_pricing_env_override_takes_precedence(monkeypatch):
    monkeypatch.setenv(_COST_INPUT_ENV, "0.0005")
    monkeypatch.setenv(_COST_OUTPUT_ENV, "0.0010")
    pricing = _resolve_pricing("unknown", "unknown-model")
    assert pricing == (Decimal("0.0005"), Decimal("0.0010"))


def test_resolve_pricing_env_override_garbage_falls_back_to_table(monkeypatch):
    monkeypatch.setenv(_COST_INPUT_ENV, "not-a-decimal")
    monkeypatch.setenv(_COST_OUTPUT_ENV, "still-not-a-decimal")
    pricing = _resolve_pricing("deepseek", "deepseek-chat")
    assert pricing == (Decimal("0.00014"), Decimal("0.00028"))


def test_resolve_pricing_unknown_model_without_override_returns_none(monkeypatch):
    monkeypatch.delenv(_COST_INPUT_ENV, raising=False)
    monkeypatch.delenv(_COST_OUTPUT_ENV, raising=False)
    assert _resolve_pricing("anthropic", "claude-3") is None


def test_compute_cost_quantises_to_microdollars(monkeypatch):
    monkeypatch.delenv(_COST_INPUT_ENV, raising=False)
    monkeypatch.delenv(_COST_OUTPUT_ENV, raising=False)
    cost, note = _compute_cost(1234, 567, "deepseek", "deepseek-chat")
    assert note is None
    # (1234/1000) * 0.00014 + (567/1000) * 0.00028
    # = 0.00017276 + 0.000158760000
    # = 0.000331520000 -> quantised to 0.000332
    assert cost == Decimal("0.000332")


def test_compute_cost_clamps_negative_token_counts(monkeypatch):
    monkeypatch.delenv(_COST_INPUT_ENV, raising=False)
    monkeypatch.delenv(_COST_OUTPUT_ENV, raising=False)
    cost, note = _compute_cost(-5, -1, "deepseek", "deepseek-chat")
    assert note is None
    assert cost == Decimal("0.000000")


def test_compute_cost_reports_missing_pricing(monkeypatch):
    monkeypatch.delenv(_COST_INPUT_ENV, raising=False)
    monkeypatch.delenv(_COST_OUTPUT_ENV, raising=False)
    cost, note = _compute_cost(100, 200, "anthropic", "claude-3")
    assert cost is None
    assert note == "llm:cost-pricing-missing"


def test_cost_budget_problem_respects_environment(monkeypatch):
    monkeypatch.setenv(_COST_BUDGET_ENV, "0.05")
    assert _cost_budget_problem(Decimal("0.06")) == "llm:cost-budget-exceeded"
    assert _cost_budget_problem(Decimal("0.04")) is None


def test_cost_budget_problem_defaults_to_ten_cents(monkeypatch):
    monkeypatch.delenv(_COST_BUDGET_ENV, raising=False)
    assert _cost_budget_problem(Decimal("0.11")) == "llm:cost-budget-exceeded"
    assert _cost_budget_problem(Decimal("0.09")) is None


def test_cost_configuration_problem_partial_override(monkeypatch):
    monkeypatch.setenv(_COST_INPUT_ENV, "0.0005")
    assert (
        _cost_configuration_problem("deepseek", "deepseek-chat", env=os.environ)
        == "llm:cost-pricing-partial"
    )


def test_cost_configuration_problem_invalid_budget(monkeypatch):
    monkeypatch.setenv(_COST_BUDGET_ENV, "ten cents")
    assert (
        _cost_configuration_problem("deepseek", "deepseek-chat", env=os.environ)
        == "llm:cost-budget-invalid"
    )


def test_cost_configuration_problem_pricing_for_unlisted_model(monkeypatch):
    monkeypatch.delenv(_COST_INPUT_ENV, raising=False)
    monkeypatch.delenv(_COST_OUTPUT_ENV, raising=False)
    assert (
        _cost_configuration_problem("anthropic", "claude-3", env=os.environ)
        == "llm:cost-pricing-missing"
    )


def test_cost_configuration_problem_clean_default(monkeypatch):
    monkeypatch.delenv(_COST_INPUT_ENV, raising=False)
    monkeypatch.delenv(_COST_OUTPUT_ENV, raising=False)
    monkeypatch.delenv(_COST_BUDGET_ENV, raising=False)
    assert _cost_configuration_problem("deepseek", "deepseek-chat", env=os.environ) is None


def test_matched_response_under_budget_records_cost(monkeypatch):
    _configure(monkeypatch, vendor="deepseek", model="deepseek-chat")
    monkeypatch.setenv(_COST_BUDGET_ENV, "0.50")
    payload = _matched_schedule_payload()
    client = _scripted_client(
        payload, usage={"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
    )
    provider = _gate_open_provider(client)
    outcome = provider.propose(_grounded_request())
    assert outcome.notes == ("llm:matched",)
    assert outcome.proposal.assignment.value == "matched"
    # (1000/1000)*0.00014 + (500/1000)*0.00028 = 0.00014 + 0.00014 = 0.00028
    assert outcome.input_tokens == 1000
    assert outcome.output_tokens == 500
    assert outcome.cost_usd == pytest.approx(0.00028)
    assert outcome.cost_note is None


def test_matched_response_over_budget_refuses_with_stable_code(monkeypatch):
    """Post-call accounting: the vendor billed more than the budget allows.

    The pre-call ceiling lets this call through because its *bounded* worst
    case fits the budget, so this exercises the second line of defence: a
    vendor that ignores ``max_tokens`` still cannot promote a proposal.
    """
    _configure(monkeypatch, vendor="deepseek", model="deepseek-chat")
    monkeypatch.setenv(_COST_BUDGET_ENV, "0.10")
    payload = _matched_schedule_payload()
    client = _scripted_client(
        payload,
        usage={"prompt_tokens": 1_000_000, "completion_tokens": 500_000, "total_tokens": 1_500_000},
    )
    provider = _gate_open_provider(client)
    outcome = provider.propose(_grounded_request())
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:cost-budget-exceeded",)
    assert outcome.refused_reason == "llm:cost-budget-exceeded"
    assert outcome.cost_note == "llm:cost-budget-exceeded"
    assert outcome.input_tokens == 1_000_000
    assert outcome.output_tokens == 500_000


@pytest.mark.parametrize("budget", ["0", "0.0001"])
def test_pre_call_ceiling_refuses_without_issuing_a_call(monkeypatch, budget):
    """A budget that cannot cover the bounded worst case must spend nothing.

    The counter-case from review: with the budget set to 0 the old code still
    issued the call and only refused afterwards, once the money was gone.
    ``_boom_client`` turns any attempted call into a test failure.
    """
    _configure(monkeypatch, vendor="deepseek", model="deepseek-chat")
    monkeypatch.setenv(_COST_BUDGET_ENV, budget)
    provider = _gate_open_provider(_boom_client())
    outcome = provider.propose(_grounded_request())
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:cost-budget-exceeded",)
    assert "llm:cost-budget-exceeded" in (outcome.refused_reason or "")


def test_pre_call_ceiling_sends_the_output_ceiling_as_max_tokens(monkeypatch):
    _configure(monkeypatch, vendor="deepseek", model="deepseek-chat")
    client = _scripted_client(
        _matched_schedule_payload(),
        usage={"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
    )
    provider = _gate_open_provider(client)
    provider.propose(_grounded_request())
    assert client.requests[0]["json"]["max_tokens"] == _DEFAULT_MAX_OUTPUT_TOKENS


def test_pre_call_ceiling_honours_a_configured_output_ceiling(monkeypatch):
    _configure(
        monkeypatch,
        vendor="deepseek",
        model="deepseek-chat",
        GIGMATE_LLM_MAX_OUTPUT_TOKENS="250",
    )
    client = _scripted_client(
        _matched_schedule_payload(),
        usage={"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100},
    )
    provider = _gate_open_provider(client)
    provider.propose(_grounded_request())
    assert client.requests[0]["json"]["max_tokens"] == 250


def test_oversized_prompt_is_refused_before_the_call(monkeypatch):
    """A prompt bigger than the input ceiling is refused, never truncated."""
    _configure(monkeypatch, vendor="deepseek", model="deepseek-chat")
    monkeypatch.setenv(_COST_MAX_INPUT_TOKENS_ENV, "1")
    provider = _gate_open_provider(_boom_client())
    outcome = provider.propose(_grounded_request())
    assert outcome.notes == ("llm:cost-input-too-large",)
    assert outcome.proposal.assignment.value == "needs_review"


def test_cost_plan_reports_an_unpriceable_model(monkeypatch):
    _configure(monkeypatch, vendor="openai", model="gpt-9000-not-in-table")
    provider = _gate_open_provider(_boom_client())
    note, max_tokens = provider._cost_plan("system prompt", _grounded_request())
    assert note == "llm:cost-pricing-missing"
    assert max_tokens == 0


def test_matched_response_missing_usage_records_audit_note(monkeypatch):
    _configure(monkeypatch, vendor="deepseek", model="deepseek-chat")
    payload = _matched_schedule_payload()
    client = _scripted_client(payload, usage=None)
    provider = _gate_open_provider(client)
    outcome = provider.propose(_grounded_request())
    # The proposal still matches; the cost row simply records why it could
    # not be priced. The audit row never silently records zero.
    assert outcome.proposal.assignment.value == "matched"
    assert outcome.cost_note == "llm:cost-usage-missing"
    assert outcome.cost_usd is None
    assert outcome.input_tokens is None
    assert outcome.output_tokens is None


def test_matched_response_malformed_usage_records_audit_note(monkeypatch):
    _configure(monkeypatch, vendor="deepseek", model="deepseek-chat")
    payload = _matched_schedule_payload()
    # ``prompt_tokens`` is a string, which is not a real int - the provider
    # must surface ``llm:cost-usage-invalid`` rather than pretend the call
    # had zero tokens.
    client = _scripted_client(payload, usage={"prompt_tokens": "1000", "completion_tokens": 500})
    provider = _gate_open_provider(client)
    outcome = provider.propose(_grounded_request())
    assert outcome.cost_note == "llm:cost-usage-invalid"


def test_unlisted_model_refuses_at_call_time(monkeypatch, caplog):
    _configure(monkeypatch, vendor="openai", model="gpt-9000-not-in-table")
    caplog.set_level(logging.INFO)
    provider = _gate_open_provider(_boom_client())
    outcome = provider.propose(_grounded_request())
    # ``notes`` carries the stable code; ``refused_reason`` is the
    # human-readable message (still secret-free, see gate 5).
    assert outcome.notes == ("llm:cost-pricing-missing",)
    assert "llm:cost-pricing-missing" in (outcome.refused_reason or "")


def test_cost_row_is_persisted_with_the_trace(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'batch2.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    _configure(monkeypatch, vendor="deepseek", model="deepseek-chat")
    payload = _matched_schedule_payload()
    client = _scripted_client(
        payload, usage={"prompt_tokens": 800, "completion_tokens": 200, "total_tokens": 1000}
    )
    provider = _gate_open_provider(client)
    outcome = provider.propose(_grounded_request())
    assert outcome.proposal.assignment.value == "matched"
    with session_factory() as db:
        persist_proposal(
            db,
            account_id=ACCOUNT_ID,
            conversation_id=CONVERSATION_ID,
            event_id=str(uuid4()),
            proposal=outcome.proposal,
            outcome=outcome,
        )
        db.commit()
    with session_factory() as db:
        trace = db.scalar(select(ModelCallTrace))
        assert trace is not None
        assert trace.input_tokens == 800
        assert trace.output_tokens == 200
        # (800/1000) * 0.00014 + (200/1000) * 0.00028 = 0.000112 + 0.000056 = 0.000168
        assert float(trace.cost_usd) == pytest.approx(0.000168)


# ---------------------------------------------------------------------------
# Section B - provider configuration startup validation
# ---------------------------------------------------------------------------


def test_validate_provider_config_clean(monkeypatch):
    _env(monkeypatch)
    assert validate_provider_config() == []


def test_validate_provider_config_unknown_vendor(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "anthropic")
    assert validate_provider_config() == ["llm:vendor-unknown"]


def test_validate_provider_config_custom_missing_endpoint(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "custom")
    assert validate_provider_config() == ["llm:endpoint-required"]


def test_validate_provider_config_non_url_endpoint(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "custom")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "api.deepseek.com")
    assert validate_provider_config() == ["llm:endpoint-invalid"]


def test_validate_provider_config_vendor_endpoint_mismatch(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "https://api.deepseek.com")
    assert "llm:vendor-endpoint-mismatch" in validate_provider_config()


def test_validate_provider_config_invalid_workspace_timezone(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_WORKSPACE_TIMEZONE", "Mars/Olympus_Mons")
    assert "workspace-timezone-invalid" in validate_provider_config()


def test_validate_provider_config_invalid_prompt_path(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROMPT_PATH", "/nonexistent/role-b-prompt.md")
    assert "llm:prompt-path-invalid" in validate_provider_config()


def test_validate_provider_config_non_numeric_token_ceiling(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv(_COST_MAX_INPUT_TOKENS_ENV, "lots")
    assert validate_provider_config() == ["llm:cost-tokens-invalid"]


def test_validate_provider_config_non_positive_token_ceiling(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv(_COST_MAX_OUTPUT_TOKENS_ENV, "-5")
    assert validate_provider_config() == ["llm:cost-tokens-invalid"]


def test_validate_provider_config_accepts_explicit_token_ceilings(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv(_COST_MAX_INPUT_TOKENS_ENV, "8000")
    monkeypatch.setenv(_COST_MAX_OUTPUT_TOKENS_ENV, "500")
    assert validate_provider_config() == []


def test_validate_provider_config_live_without_key(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "deepseek-chat")
    monkeypatch.delenv("GIGMATE_LLM_API_KEY", raising=False)
    assert "llm:api-key-missing" in validate_provider_config()


def test_validate_provider_config_env_override_drive(monkeypatch):
    """``env`` mapping lets tests drive the helper without mutating the real env."""
    issues = validate_provider_config(
        env={
            "GIGMATE_LLM_PROVIDER": "anthropic",
            "GIGMATE_LLM_LIVE": "1",
        }
    )
    assert "llm:vendor-unknown" in issues
    assert "llm:api-key-missing" in issues


def test_audit_provider_config_logs_warning_when_live_off(monkeypatch, caplog):
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "anthropic")
    caplog.set_level(logging.WARNING, logger="gigmate.worker")
    # The worker is the only process that boots through this audit, so we
    # call the helper directly here. Live=0 means the seam refuses anyway,
    # so the warning is non-fatal.
    assert audit_provider_config() is True
    assert "provider_config_invalid" in caplog.text


def test_audit_provider_config_refuses_to_start_when_live_on(monkeypatch, caplog):
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    caplog.set_level(logging.ERROR, logger="gigmate.worker")
    # A worker that is about to issue real vendor calls must not boot with
    # a known-broken configuration; audit_provider_config returns False
    # and worker.main() turns that into an early return.
    assert audit_provider_config() is False
    assert "provider_config_invalid" in caplog.text


# ---------------------------------------------------------------------------
# Section C - prompt-injection regression suite
# ---------------------------------------------------------------------------


def _load_injection_cases() -> list[dict]:
    return json.loads(INJECTION_MANIFEST.read_text(encoding="utf-8"))["cases"]


def _build_request_from_event(event: dict) -> ExtractionRequest:
    fields = {
        "account_id": event["account_id"],
        "conversation_id": event["conversation_id"],
        "message_id": event["message_id"],
        "message_revision": event["message_revision"],
        "message_text": event["text"],
        "context_version": event["context_version"],
        "candidate_work_order_ids": tuple(event.get("candidate_work_order_ids", ())),
        "base_work_order_version": event.get("base_work_order_version"),
        "base_work_order_snapshot": event.get("base_work_order_snapshot"),
        "message_received_at": event.get("message_received_at"),
        "workspace_timezone": event.get("workspace_timezone"),
        "origin": "synthetic",
    }
    return ExtractionRequest(**fields)


@pytest.mark.parametrize("case", _load_injection_cases(), ids=lambda c: c["case_id"])
def test_injection_regression_suite(monkeypatch, case: dict):
    """Every prompt-injection case must surface a needs_review with a stable code.

    The provider is driven through the gate-open subclass with a scripted
    client that returns the ``compromised_response`` field; the test
    asserts the guard chain catches the attempt and never produces a
    ``matched`` proposal. The test name in pytest output is the case id
    so a failure points directly at the regression.
    """
    _configure(
        monkeypatch,
        vendor="deepseek",
        model="deepseek-chat",
        GIGMATE_LLM_ALLOW_LIVE_ORIGIN="1",
    )
    request = _build_request_from_event(case["input_event"])
    client = _scripted_client(case["compromised_response"])
    provider = _gate_open_provider(client)
    outcome = provider.propose(request)
    # The injection must never promote the proposal to ``matched``.
    assert outcome.proposal.assignment.value == case["expected_assignment"]
    # The expected stable code must appear in notes (notes is a tuple; the
    # provider may emit additional ones, so we check containment).
    assert case["expected_note"] in outcome.notes
    # ``refused_reason`` must carry a stable prefix with no customer text.
    assert outcome.refused_reason is not None
    assert outcome.refused_reason.startswith(case["expected_refused_reason_prefix"])
    for leaked in ("改", "商", "Mars", "00000000-0000-4000-8000-000000000999"):
        assert leaked not in outcome.refused_reason, (
            f"{case['case_id']}: refused_reason must not echo injection payload"
        )


def test_injection_manifest_is_synthetic_only():
    """The regression suite must never carry live or otherwise non-synthetic data."""
    manifest = json.loads(INJECTION_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["data_classification"] == "synthetic"
    for case in manifest["cases"]:
        assert case["data_classification"] == "synthetic"
        assert case["case_id"].startswith("inj-")
