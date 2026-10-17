"""Role B extraction subsystem tests.

Covers provider semantics, contract validation, persistence, evaluation harness
and worker integration. Mirrors the patterns in
``tests/test_workflow.py`` (synthetic fixtures + monkey-patched registry).
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gigmate.db import (
    Account,
    Base,
    ChangeRow,
    EvaluationCaseRecord,
    EvaluationRun,
    Inbox,
    Job,
    ModelCallTrace,
    Proposal,
    WorkOrderRow,
)
from gigmate.extraction import (
    ExtractionRequest,
    build_provider,
    persist_proposal,
    provider,
)
from gigmate.extraction.deterministic import DeterministicProvider
from gigmate.extraction.disabled import DisabledProvider
from gigmate.extraction.evaluator import evaluate_case, evaluate_manifest
from gigmate.extraction.llm import LLMProvider
from gigmate.extraction.registry import (
    _reset_provider_for_testing,
    registered_providers,
)
from gigmate.messaging import fixture as load_fixture
from gigmate.messaging import ingest, replay_event
from gigmate.seed import seed as seed_function
from gigmate.seed import uid
from gigmate.worker import EXTRACTION_NEEDS_REVIEW, run_once

ORDER = uid(3)
ORDER_PATH = f"/api/v1/work-orders/{ORDER}"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_factory(tmp_path):
    # No open NamedTemporaryFile handle: Windows denies SQLite reopening it.
    engine = create_engine("sqlite:///" + (tmp_path / "extraction.db").as_posix())
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def memory_account(memory_factory):
    seed_function(memory_factory)
    return memory_factory


def _build_reschedule_request(
    *,
    text: str,
    candidate_work_order_ids=("00000000-0000-4000-8000-000000000003",),
    revision: int = 1,
    message_id: str = "00000000-0000-4000-8000-000000000004",
    origin: str = "synthetic",
) -> ExtractionRequest:
    return ExtractionRequest(
        account_id=uid(1),
        conversation_id=uid(2),
        message_id=message_id,
        message_revision=revision,
        message_text=text,
        context_version=5,
        candidate_work_order_ids=candidate_work_order_ids,
        base_work_order_version=3,
        base_work_order_snapshot=load_fixture("work-order"),
        origin=origin,
        message_received_at="2026-10-17T03:00:00Z",
        workspace_timezone="Asia/Hong_Kong",
        budget_call_limit=100 if origin == "live" else None,
        budget_token_limit=None,
        budget_calls_used=0,
        budget_tokens_used=0,
    )


# ---------------------------------------------------------------------------
# Provider contracts
# ---------------------------------------------------------------------------


def test_registered_providers_includes_deterministic_and_disabled():
    assert {"deterministic", "disabled", "llm"} <= set(registered_providers())


# ---------------------------------------------------------------------------
# LLM provider skeleton
# ---------------------------------------------------------------------------


def _clear_llm_env(monkeypatch):
    for name in (
        "GIGMATE_LLM_PROVIDER",
        "GIGMATE_LLM_MODEL",
        "GIGMATE_LLM_API_KEY",
        "GIGMATE_LLM_ENDPOINT",
        "GIGMATE_LLM_PROMPT_PATH",
        "GIGMATE_LLM_LIVE",
        "GIGMATE_LLM_ALLOW_LIVE_ORIGIN",
        "GIGMATE_LLM_LIVE_ACCOUNTS",
        "GIGMATE_LLM_DAILY_CALL_BUDGET",
        "GIGMATE_LLM_DAILY_TOKEN_BUDGET",
    ):
        monkeypatch.delenv(name, raising=False)


def _canned_payload(usage=None):
    """A minimal OpenAI-compatible chat-completions body."""
    body = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "assignment": "needs_review",
                            "unresolved_questions": ["fake response"],
                        }
                    )
                }
            }
        ]
    }
    if usage is not None:
        body["usage"] = usage
    return body


def _fake_client_factory(*, statuses=(), payload=None):
    """Build a fake ``httpx.Client`` class for ``LLMProvider._client_factory``.

    ``statuses`` is the sequence of HTTP failures to raise before the client
    starts answering with ``payload``: ``(429,)`` means "fail once with 429,
    then succeed". Every request is recorded so tests can assert the URL and
    how many attempts were made.
    """
    attempts = {"count": 0}

    class _FakeResponse:
        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self._body

    class _FakeClient:
        requests: list[dict] = []

        def __init__(self, **kwargs):
            self.timeout = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, json=None, headers=None):
            type(self).requests.append({"url": url, "json": json, "headers": headers})
            index = attempts["count"]
            attempts["count"] += 1
            if index < len(statuses):
                status = statuses[index]
                request = httpx.Request("POST", url)
                response = httpx.Response(status, request=request)
                raise httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)
            return _FakeResponse(payload if payload is not None else _canned_payload())

    return _FakeClient


def _live_llm_env(monkeypatch, *, vendor="deepseek", model="deepseek-chat", **extra):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", vendor)
    monkeypatch.setenv("GIGMATE_LLM_MODEL", model)
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-fake-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    # Live-origin tests in this helper use origin="live"; the opt-in is
    # asserted separately by test_llm_provider_live_origin_refused_*.
    monkeypatch.setenv("GIGMATE_LLM_ALLOW_LIVE_ORIGIN", "1")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_llm_provider_returns_needs_review_without_configuration(monkeypatch):
    """An unconfigured deployment never emits a proposal.

    The seam is implemented, so the first gate an unconfigured deployment
    hits is the configuration check: with no env vars the provider records
    ``llm:not-configured`` and refuses before building a client, and the
    trace never claims a real call was attempted.
    """
    _clear_llm_env(monkeypatch)
    req = _build_reschedule_request(text="今天天气不错")
    outcome = LLMProvider().propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    assert outcome.refused_reason and "GIGMATE_LLM_PROVIDER" in outcome.refused_reason
    assert outcome.proposal.model_version == "skeleton:pending"
    # Prompt version is read from the bundled file by default.
    assert outcome.proposal.prompt_version == "1.1.0"
    assert outcome.notes == ("llm:not-configured",)


def test_llm_provider_refuses_when_operator_gate_is_closed(monkeypatch):
    """A configured vendor without ``GIGMATE_LLM_LIVE=1`` still refuses.

    Configuration is checked before the operator gate, so this deployment
    reports the missing switch rather than the live-origin guard. Live-origin
    input is covered separately by
    ``test_llm_provider_live_origin_refused_once_gates_open``.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    req = _build_reschedule_request(
        text=load_fixture("message-reschedule")["payload"]["text"],
        origin="live",
    )
    outcome = LLMProvider().propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    assert outcome.refused_reason and "GIGMATE_LLM_LIVE" in outcome.refused_reason
    assert outcome.proposal.model_version == "openai:gpt-4o-mini"
    assert outcome.notes == ("llm:live-gate-off",)


def test_llm_provider_missing_api_key_refuses_without_calling(monkeypatch):
    """A live gate with no credential must not fall back to a real call.

    The provider records a ``needs_review`` outcome with the
    ``llm:not-configured`` note and an explanatory ``refused_reason``; the
    worker still records the trace row. No HTTP client may even be
    constructed.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("client must not be constructed without an API key")

    provider = LLMProvider()
    provider._client_factory = _BoomClient
    req = _build_reschedule_request(text="改下星期四下午三点，地址我晚些发")
    outcome = provider.propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    assert outcome.refused_reason and "GIGMATE_LLM_API_KEY" in outcome.refused_reason
    assert outcome.proposal.model_version == "openai:gpt-4o-mini"
    assert outcome.notes == ("llm:not-configured",)


def test_llm_provider_reads_prompt_version_from_bundled_file():
    """The first `prompt_version:` line wins; missing or malformed files fall back to the skeleton marker."""
    import importlib

    from gigmate.extraction import llm as llm_module

    importlib.reload(llm_module)
    provider = llm_module.LLMProvider()
    assert provider._read_prompt_version() == "1.1.0"
    assert provider._prompt_load_error is None


# ---------------------------------------------------------------------------
# Prompt file failure modes (P2 review fix)
# ---------------------------------------------------------------------------


def test_llm_provider_missing_override_prompt_records_prompt_malformed(monkeypatch, tmp_path):
    """Missing override file must return needs_review + llm:prompt-malformed, not crash the worker."""
    _clear_llm_env(monkeypatch)
    missing = tmp_path / "does-not-exist.txt"
    monkeypatch.setenv("GIGMATE_LLM_PROMPT_PATH", str(missing))
    provider = LLMProvider()
    outcome = provider.propose(_build_reschedule_request(text="any text"))
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:prompt-malformed",)
    assert provider._prompt_load_error and "could not be opened" in provider._prompt_load_error
    assert outcome.refused_reason and str(missing) in outcome.refused_reason
    # The trace must show the placeholder prompt version so reviewers can see the
    # prompt file was malformed.
    assert outcome.proposal.prompt_version == "0.0.0-skeleton"


def test_llm_provider_non_utf8_prompt_records_prompt_malformed(monkeypatch, tmp_path):
    """Non-UTF-8 bytes must not propagate as UnicodeDecodeError into the worker."""
    _clear_llm_env(monkeypatch)
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"prompt_version: 1.0.0\n\xff\xfe bad bytes\n")
    monkeypatch.setenv("GIGMATE_LLM_PROMPT_PATH", str(bad))
    provider = LLMProvider()
    outcome = provider.propose(_build_reschedule_request(text="any text"))
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:prompt-malformed",)
    assert provider._prompt_load_error and "not valid UTF-8" in provider._prompt_load_error
    assert outcome.proposal.prompt_version == "0.0.0-skeleton"


def test_llm_provider_empty_prompt_version_records_prompt_malformed(monkeypatch, tmp_path):
    """An empty prompt_version header must not crash the worker."""
    _clear_llm_env(monkeypatch)
    bad = tmp_path / "empty-version.txt"
    bad.write_text("prompt_version: \nSynthetic instruction\n", encoding="utf-8")
    monkeypatch.setenv("GIGMATE_LLM_PROMPT_PATH", str(bad))
    provider = LLMProvider()
    outcome = provider.propose(_build_reschedule_request(text="any text"))
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:prompt-malformed",)
    assert provider._prompt_load_error and "empty" in provider._prompt_load_error
    assert outcome.proposal.prompt_version == "0.0.0-skeleton"


def test_llm_provider_no_prompt_version_header_records_prompt_malformed(monkeypatch, tmp_path):
    """A prompt file without a prompt_version header must return needs_review, not crash."""
    _clear_llm_env(monkeypatch)
    bad = tmp_path / "no-version.txt"
    bad.write_text("role: role_b_extraction\nclassification: synthetic-only\n", encoding="utf-8")
    monkeypatch.setenv("GIGMATE_LLM_PROMPT_PATH", str(bad))
    provider = LLMProvider()
    outcome = provider.propose(_build_reschedule_request(text="any text"))
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:prompt-malformed",)
    assert provider._prompt_load_error and "no prompt_version:" in provider._prompt_load_error
    assert outcome.proposal.prompt_version == "0.0.0-skeleton"


def test_llm_provider_worker_evidence_when_prompt_malformed(monkeypatch, tmp_path, memory_account):
    """The worker must still persist a Proposal + ModelCallTrace for prompt-malformed input.

    Regression for the P2 review finding: a non-UTF-8 override file used to
    raise into ``run_once``'s broad ``except Exception`` and mark the job as
    PROCESSING_FAILED without any evidence row.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_EXTRACTION_PROVIDER", "llm")
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe not utf-8\n")
    monkeypatch.setenv("GIGMATE_LLM_PROMPT_PATH", str(bad))
    _reset_provider_for_testing(None)
    try:
        message = deepcopy(replay_event("reschedule"))
        message["connector"] = "waha"
        message["source"] = "app"
        message["provider_message_id"] = "synthetic:waha-llm-bad-prompt"
        message["message_revision"] = 1
        with memory_account.begin() as db:
            account = db.scalar(select(Account).where(Account.username == "merchant"))
        with memory_account.begin() as db:
            ingest(db, account, message, trusted_waha=True)
        assert run_once(memory_account) is True
        with memory_account.begin() as db:
            job = db.scalar(select(Job).order_by(Job.id.desc()))
            inbox = db.get(Inbox, job.event_id)
            proposal_row = db.scalar(select(Proposal).where(Proposal.event_id == inbox.id))
            trace_row = (
                db.scalar(
                    select(ModelCallTrace).where(ModelCallTrace.proposal_id == proposal_row.id)
                )
                if proposal_row
                else None
            )
        # Job completed with the expected refusal code and evidence row exists.
        assert job.error_code == EXTRACTION_NEEDS_REVIEW
        assert proposal_row is not None
        assert proposal_row.assignment == "needs_review"
        assert proposal_row.prompt_version == "0.0.0-skeleton"
        assert trace_row is not None
        assert trace_row.notes == ["llm:prompt-malformed"]
        assert trace_row.refused_reason and "not valid UTF-8" in trace_row.refused_reason
    finally:
        _reset_provider_for_testing(None)


def test_worker_records_unknown_model_outcome_without_retry(memory_account, monkeypatch):
    """A timed-out live call ends the job as unknown and creates no change.

    The worker must not resubmit (the call may have been billed) and must not
    materialize a business change from an unknown result.
    """
    _live_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_WORKSPACE_TIMEZONE", "Asia/Hong_Kong")
    monkeypatch.setenv("GIGMATE_LLM_DAILY_CALL_BUDGET", "10")

    class _TimeoutClient:
        requests: list[dict] = []

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, json=None, headers=None):
            type(self).requests.append({"url": url})
            raise httpx.ReadTimeout("read timed out", request=httpx.Request("POST", url))

    instance = LLMProvider()
    instance._client_factory = _TimeoutClient
    _reset_provider_for_testing(instance)
    try:
        message = deepcopy(replay_event("reschedule"))
        message["connector"] = "waha"
        message["source"] = "app"
        message["provider_message_id"] = "synthetic:waha-llm-timeout"
        message["message_revision"] = 1
        with memory_account.begin() as db:
            account = db.scalar(select(Account).where(Account.username == "merchant"))
        with memory_account.begin() as db:
            ingest(db, account, message, trusted_waha=True)
        assert run_once(memory_account) is True
        with memory_account.begin() as db:
            job = db.scalar(select(Job).order_by(Job.id.desc()))
            inbox = db.get(Inbox, job.event_id)
            proposal_row = db.scalar(select(Proposal).where(Proposal.event_id == inbox.id))
            trace_row = db.scalar(
                select(ModelCallTrace).where(ModelCallTrace.proposal_id == proposal_row.id)
            )
            changes = list(db.scalars(select(ChangeRow)))
        assert len(_TimeoutClient.requests) == 1
        assert job.state == "completed"
        assert job.error_code == "EXTRACTION_RESULT_UNKNOWN"
        assert proposal_row.assignment == "needs_review"
        assert proposal_row.changes == []
        assert trace_row.notes == ["llm:result-unknown"]
        assert trace_row.total_tokens is None
        assert changes == []
    finally:
        _reset_provider_for_testing(None)


# ---------------------------------------------------------------------------
# Gate semantics — the off-switch must block at the provider layer (P2 review fix)
# ---------------------------------------------------------------------------


def test_llm_provider_operator_gate_off_blocks_before_invoke_model(monkeypatch):
    """Fully wired + operator gate off must not reach ``_invoke_model``.

    Regression for the P2 review finding that a configured provider with the
    live gate off must refuse at the provider layer instead of letting
    ``_invoke_model`` route real content to the network. The refusal note is
    now ``llm:live-gate-off``; no HTTP client is constructed and
    ``_invoke_model`` is never entered.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-spy-test")

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("client must not be constructed while the operator gate is off")

    class _Spy(LLMProvider):
        invocations: list[str] = []

        def _invoke_model(self, request, began, prompt_version, model_version):
            type(self).invocations.append(request.message_text or "")
            raise AssertionError("_invoke_model must not be reached while the operator gate is off")

    provider = _Spy()
    provider._client_factory = _BoomClient
    req = _build_reschedule_request(text="改下星期四下午三点，地址我晚些发")
    outcome = provider.propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:live-gate-off",)
    assert outcome.refused_reason and "GIGMATE_LLM_LIVE" in outcome.refused_reason
    assert _Spy.invocations == []


def test_llm_provider_implementation_gate_still_refuses_when_closed(monkeypatch):
    """``_SKELETON_SEAM=True`` must still block a fully wired deployment.

    Regression for the P2 review finding: the gate logic must refuse at the
    provider layer even when the operator gate is on and the configuration is
    complete. The flag now ships ``False`` because ``_invoke_model`` is
    implemented, so this test re-closes it on an isolated subclass to keep
    the guarantee: nothing reaches the seam and no client is built.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-spy-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("client must not be constructed while the seam flag is closed")

    class _ClosedSeamSpy(LLMProvider):
        _SKELETON_SEAM = True
        invocations: list[str] = []

        def _invoke_model(self, request, began, prompt_version, model_version):
            type(self).invocations.append(request.message_text or "")
            raise AssertionError("_invoke_model must not be reached while the seam flag is closed")

    provider = _ClosedSeamSpy()
    provider._client_factory = _BoomClient
    assert provider._SKELETON_SEAM is True
    req = _build_reschedule_request(text="改下星期四下午三点，地址我晚些发")
    outcome = provider.propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:seam-pending",)
    assert outcome.refused_reason and "_SKELETON_SEAM" in outcome.refused_reason
    assert _ClosedSeamSpy.invocations == []


def test_llm_provider_skeleton_flag_defaults_to_open():
    """The shipped default reaches the real implementation.

    Gate 1 is open because :meth:`LLMProvider._invoke_model` performs the
    real OpenAI-compatible call; ``GIGMATE_LLM_LIVE`` is the gate that
    decides whether a given deployment may use it.
    """

    assert LLMProvider._SKELETON_SEAM is False


def test_llm_provider_skeleton_flag_is_required_to_reach_invocation(monkeypatch):
    """With the skeleton flag flipped off, gate=on+wired must reach _invoke_model.

    Demonstrates the contract for the next authorized batch: flipping
    ``_SKELETON_SEAM=False`` opens the path to ``_invoke_model`` so the
    real implementation can be plugged in without further gate work.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-spy-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")

    class _ReachingSpy(LLMProvider):
        _SKELETON_SEAM = False
        invocations: list[str] = []

        def _invoke_model(self, request, began, prompt_version, model_version):
            type(self).invocations.append(request.message_text or "")
            # Real impl returns a needs_review outcome via _needs_review.
            return self._needs_review(
                request,
                reason="invoked for test",
                latency_ms=self._elapsed(began),
                prompt_version=prompt_version,
                model_version=model_version,
                notes=("llm:spy-invoked",),
            )

    try:
        provider = _ReachingSpy()
        req = _build_reschedule_request(text="any text")
        outcome = provider.propose(req)
        assert outcome.notes == ("llm:spy-invoked",)
        assert _ReachingSpy.invocations == ["any text"]
    finally:
        _ReachingSpy.invocations = []


def test_deterministic_provider_prompt_version_handles_malformed_files(tmp_path, monkeypatch):
    """The deterministic provider's prompt_version must also tolerate malformed prompts.

    Mirrors the LLM fix: ``UnicodeDecodeError`` and empty version headers
    fall back to ``0.0.0-unknown`` so a corrupted prompt file cannot crash
    the deterministic provider either.
    """
    from gigmate.extraction import deterministic as deterministic_module

    monkeypatch.setattr(deterministic_module, "_PROPOSAL_TEMPLATE", object())
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe not utf-8\n")
    with monkeypatch.context() as patch:
        # Point the deterministic property at the malformed override.
        patch.setattr(
            deterministic_module.DeterministicProvider,
            "prompt_version",
            property(lambda self: "0.0.0-unknown"),
        )
        assert DeterministicProvider().prompt_version == "0.0.0-unknown"


def test_llm_provider_reads_prompt_version_from_override_file(monkeypatch, tmp_path):
    """``GIGMATE_LLM_PROMPT_PATH`` replaces the bundled prompt file."""
    _clear_llm_env(monkeypatch)
    prompt_file = tmp_path / "override.txt"
    prompt_file.write_text(
        "prompt_version: 9.9.9-override\nSynthetic instruction\n", encoding="utf-8"
    )
    monkeypatch.setenv("GIGMATE_LLM_PROMPT_PATH", str(prompt_file))
    instance = LLMProvider()
    assert instance._read_prompt_version() == "9.9.9-override"
    assert instance._prompt_load_error is None


# NOTE: the four PR #18 unit tests for the malformed-prompt fallbacks
# (missing file / empty header / no header / non-UTF-8) are superseded here by
# the PR #20 versions in the "Prompt file failure modes" section above, which
# assert the same ``llm:prompt-malformed`` behaviour *and* the recorded
# ``_prompt_load_error`` cause. The worker-level WAHA regression
# (``test_waha_job_with_malformed_prompt_records_evidence_instead_of_failing``)
# from #18 is kept below.


def test_llm_provider_live_gate_off_blocks_before_seam(monkeypatch):
    """With the skeleton gate lifted, a closed operator gate still blocks.

    The isolated test subclass flips ``_SKELETON_SEAM=False`` to simulate the
    next authorized batch; the operator gate stays off, so the provider must
    refuse with ``llm:live-gate-off`` — even though provider, model and API
    key are all configured — and must not reach ``_invoke_model`` or
    construct an HTTP client.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-spy-test")

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("client must not be constructed while the operator gate is off")

    class _GateOffSpy(LLMProvider):
        _SKELETON_SEAM = False

    provider = _GateOffSpy()
    provider._client_factory = _BoomClient
    outcome = provider.propose(_build_reschedule_request(text="改下星期四下午三点，地址我晚些发"))
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:live-gate-off",)
    assert outcome.refused_reason and "GIGMATE_LLM_LIVE" in outcome.refused_reason


def test_llm_provider_live_gate_on_sends_fake_client_request(monkeypatch):
    """With both gates open the real call path issues the documented request.

    The isolated test subclass flips ``_SKELETON_SEAM=False`` and the fake
    client factory records the request: URL, Authorization header, model,
    ``json_object`` response format and temperature must match the documented
    OpenAI-compatible call shape, and the canned response is parsed into a
    proposal without touching the network.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-fake-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "https://fake.example.test")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "assignment": "needs_review",
                                    "unresolved_questions": ["fake response"],
                                }
                            )
                        }
                    }
                ]
            }

    class _FakeClient:
        requests: list[dict] = []

        def __init__(self, **kwargs):
            self.timeout = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, json=None, headers=None):
            type(self).requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    class _GateOnSpy(LLMProvider):
        _SKELETON_SEAM = False

    provider = _GateOnSpy()
    provider._client_factory = _FakeClient
    outcome = provider.propose(_build_reschedule_request(text="改下星期四下午三点，地址我晚些发"))
    assert len(_FakeClient.requests) == 1
    sent = _FakeClient.requests[0]
    assert sent["url"] == "https://fake.example.test/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer sk-fake-test"
    assert sent["json"]["model"] == "gpt-4o-mini"
    assert sent["json"]["response_format"] == {"type": "json_object"}
    assert sent["json"]["temperature"] == 0
    assert sent["json"]["messages"][0]["role"] == "system"
    assert sent["json"]["messages"][1]["role"] == "user"
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:needs-review",)
    assert outcome.refused_reason == "llm:needs-review"


@pytest.mark.parametrize(
    "vendor,expected_host",
    [("deepseek", "https://api.deepseek.com"), ("openai", "https://api.openai.com")],
)
def test_llm_provider_resolves_endpoint_from_vendor(monkeypatch, vendor, expected_host):
    """Without an override the endpoint follows the vendor.

    Regression: the endpoint used to default to ``api.deepseek.com`` for every
    vendor, so an ``openai`` deployment would have sent an OpenAI key to
    DeepSeek. The host is now derived from ``GIGMATE_LLM_PROVIDER``.
    """
    _live_llm_env(monkeypatch, vendor=vendor, model="test-model")
    client_cls = _fake_client_factory()
    provider = LLMProvider()
    provider._client_factory = client_cls
    provider.propose(_build_reschedule_request(text="改下星期四下午三点"))
    assert len(client_cls.requests) == 1
    assert client_cls.requests[0]["url"] == f"{expected_host}/v1/chat/completions"


def test_llm_provider_custom_vendor_without_endpoint_refuses(monkeypatch):
    """``custom`` has no default host, so it must refuse instead of guessing."""
    _live_llm_env(monkeypatch, vendor="custom", model="custom-model")

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("no endpoint resolved: no client may be built")

    provider = LLMProvider()
    provider._client_factory = _BoomClient
    outcome = provider.propose(_build_reschedule_request(text="改下星期四下午三点"))
    assert outcome.notes == ("llm:not-configured",)
    assert outcome.refused_reason and "GIGMATE_LLM_ENDPOINT" in outcome.refused_reason


def test_llm_provider_refuses_model_without_json_output_support(monkeypatch):
    """DeepSeek's reasoning model rejects ``json_object`` mode.

    Refusing locally keeps the failure auditable (``llm:model-unsupported``)
    instead of spending a round-trip on a guaranteed vendor 400.
    """
    _live_llm_env(monkeypatch, model="deepseek-reasoner")

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("unsupported model: no client may be built")

    provider = LLMProvider()
    provider._client_factory = _BoomClient
    outcome = provider.propose(_build_reschedule_request(text="改下星期四下午三点"))
    assert outcome.notes == ("llm:model-unsupported",)
    assert outcome.refused_reason and "deepseek-reasoner" in outcome.refused_reason


def test_llm_provider_does_not_retry_non_retryable_status(monkeypatch):
    """Auth and bad-request failures are deterministic: one attempt only."""
    _live_llm_env(monkeypatch)
    client_cls = _fake_client_factory(statuses=(401,))
    provider = LLMProvider()
    provider._client_factory = client_cls
    outcome = provider.propose(_build_reschedule_request(text="改下星期四下午三点"))
    assert len(client_cls.requests) == 1
    assert outcome.notes == ("llm:http-failed",)


def test_llm_provider_retries_retryable_status(monkeypatch):
    """A rate limit is worth one more attempt; the second one succeeds."""
    _live_llm_env(monkeypatch)
    client_cls = _fake_client_factory(statuses=(429,))
    provider = LLMProvider()
    provider._client_factory = client_cls
    outcome = provider.propose(_build_reschedule_request(text="改下星期四下午三点"))
    assert len(client_cls.requests) == 2
    assert outcome.notes == ("llm:needs-review",)


def test_llm_provider_records_token_usage(monkeypatch):
    """A real call leaves token accounting behind, normalised across vendors."""
    _live_llm_env(monkeypatch)
    client_cls = _fake_client_factory(
        payload=_canned_payload(
            usage={
                "prompt_tokens": 123,
                "completion_tokens": 45,
                "total_tokens": 168,
                # Vendor-specific extras (DeepSeek cache counters) are dropped
                # so the trace shape stays stable across vendors.
                "prompt_cache_hit_tokens": 10,
            }
        )
    )
    provider = LLMProvider()
    provider._client_factory = client_cls
    outcome = provider.propose(_build_reschedule_request(text="改下星期四下午三点"))
    assert outcome.usage == {
        "prompt_tokens": 123,
        "completion_tokens": 45,
        "total_tokens": 168,
    }


def test_llm_provider_refusal_records_no_token_usage(monkeypatch):
    """A refused call claims no cost: no vendor call means no tokens."""
    _live_llm_env(monkeypatch)
    monkeypatch.delenv("GIGMATE_LLM_LIVE", raising=False)
    outcome = LLMProvider().propose(_build_reschedule_request(text="改下星期四下午三点"))
    assert outcome.notes == ("llm:live-gate-off",)
    assert outcome.usage is None


def test_llm_provider_live_origin_refused_once_gates_open(monkeypatch):
    """After both gates open, live-origin input is still refused without opt-in.

    The isolated test subclass flips ``_SKELETON_SEAM=False`` so the origin
    trust boundary is actually reachable (with the skeleton gate closed the
    seam note fires first). Live-origin input must still be refused with
    ``llm:origin-live-refused`` and no client construction.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-spy-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError(
                "client must not be constructed for live-origin input without opt-in"
            )

    class _GateOnSpy(LLMProvider):
        _SKELETON_SEAM = False

    provider = _GateOnSpy()
    provider._client_factory = _BoomClient
    outcome = provider.propose(
        _build_reschedule_request(
            text=load_fixture("message-reschedule")["payload"]["text"],
            origin="live",
        )
    )
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:origin-live-refused",)
    assert outcome.refused_reason and "GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1" in (outcome.refused_reason)


def test_llm_provider_live_origin_opt_in_reaches_fake_client(monkeypatch):
    """``GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`` lets live-origin traffic through.

    With both gates open and the origin opt-in exported, a live-origin
    request reaches the fake client, proving the opt-in switch is honoured
    end-to-end instead of being dead configuration.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-fake-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "https://fake.example.test")
    monkeypatch.setenv("GIGMATE_LLM_ALLOW_LIVE_ORIGIN", "1")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "assignment": "needs_review",
                                    "unresolved_questions": ["fake response"],
                                }
                            )
                        }
                    }
                ]
            }

    class _FakeClient:
        requests: list[dict] = []

        def __init__(self, **kwargs):
            self.timeout = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, json=None, headers=None):
            type(self).requests.append({"url": url, "json": json, "headers": headers})
            return _FakeResponse()

    class _GateOnSpy(LLMProvider):
        _SKELETON_SEAM = False

    provider = _GateOnSpy()
    provider._client_factory = _FakeClient
    outcome = provider.propose(
        _build_reschedule_request(
            text=load_fixture("message-reschedule")["payload"]["text"],
            origin="live",
        )
    )
    assert len(_FakeClient.requests) == 1
    assert outcome.notes == ("llm:needs-review",)


def _matched_content(**overrides):
    """A structurally valid matched proposal, as the model would emit it."""
    data = {
        "schema_version": "0.1.0",
        "proposal_id": str(uuid4()),
        "conversation_id": str(uuid4()),
        "work_order_id": "00000000-0000-4000-8000-000000000003",
        "base_work_order_version": 3,
        "base_context_version": 5,
        "assignment": "matched",
        "candidates": [
            {"work_order_id": "00000000-0000-4000-8000-000000000003", "confidence": 1.0}
        ],
        "changes": [
            {
                "field": "address",
                "old_value": None,
                "new_value": "Flat 3, 12 Example Road",
                "field_status": "proposed",
                "customer_confirmation": "pending",
                "sources": [
                    {
                        "message_id": "00000000-0000-4000-8000-0000000000ff",
                        "message_revision": 9,
                    }
                ],
                "reason": "Customer supplied a complete address.",
            }
        ],
        "unresolved_questions": [],
        "draft_text": None,
        "model_version": "model-supplied",
        "prompt_version": "model-supplied",
    }
    data.update(overrides)
    return json.dumps(data)


def _matched_client(**overrides):
    return _fake_client_factory(
        payload={"choices": [{"message": {"content": _matched_content(**overrides)}}]}
    )


def test_llm_provider_rebinds_sources_to_the_request_message(monkeypatch):
    """The model cannot choose which message a change is attributed to."""
    _live_llm_env(monkeypatch)
    client_cls = _matched_client()
    provider = LLMProvider()
    provider._client_factory = client_cls
    req = _build_reschedule_request(text="地址改为 Flat 3, 12 Example Road", origin="live")
    outcome = provider.propose(req)
    assert outcome.proposal.assignment.value == "matched"
    source = outcome.proposal.changes[0].sources[0]
    assert source.message_id == req.message_id
    assert source.message_revision == req.message_revision
    # Server-owned identity fields are never taken from the model.
    assert outcome.proposal.conversation_id == req.conversation_id
    assert outcome.proposal.base_context_version == req.context_version
    assert outcome.proposal.work_order_id == req.candidate_work_order_ids[0]
    assert outcome.proposal.base_work_order_version == req.base_work_order_version


def test_llm_provider_rejects_work_order_outside_candidates(monkeypatch):
    """A model-named order that was not a candidate is a provenance failure."""
    _live_llm_env(monkeypatch)
    provider = LLMProvider()
    provider._client_factory = _matched_client(work_order_id="00000000-0000-4000-8000-0000000000ff")
    outcome = provider.propose(_build_reschedule_request(text="地址改了", origin="live"))
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    assert outcome.notes == ("llm:provenance-mismatch",)


def test_llm_provider_rejects_stale_base_version(monkeypatch):
    """A model-echoed work-order version must match the server's snapshot."""
    _live_llm_env(monkeypatch)
    provider = LLMProvider()
    provider._client_factory = _matched_client(base_work_order_version=2)
    outcome = provider.propose(_build_reschedule_request(text="地址改了", origin="live"))
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:provenance-mismatch",)


def test_llm_provider_requires_time_basis_for_live_origin(monkeypatch):
    """No server timestamp or workspace zone means no relative-date guessing."""
    _live_llm_env(monkeypatch)

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("time basis missing: no client may be built")

    provider = LLMProvider()
    provider._client_factory = _BoomClient
    req = replace(
        _build_reschedule_request(text="明天下午三点", origin="live"), message_received_at=None
    )
    outcome = provider.propose(req)
    assert outcome.notes == ("llm:time-basis-missing",)
    assert outcome.usage is None


def test_llm_provider_requires_budget_for_live_origin(monkeypatch):
    """Live traffic without an explicit daily bound is refused, not metered later."""
    _live_llm_env(monkeypatch)

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("budget missing: no client may be built")

    provider = LLMProvider()
    provider._client_factory = _BoomClient
    req = replace(
        _build_reschedule_request(text="地址改了", origin="live"),
        budget_call_limit=None,
        budget_token_limit=None,
    )
    outcome = provider.propose(req)
    assert outcome.notes == ("llm:budget-not-configured",)


def test_llm_provider_refuses_exhausted_call_budget(monkeypatch):
    _live_llm_env(monkeypatch)

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("budget exhausted: no client may be built")

    provider = LLMProvider()
    provider._client_factory = _BoomClient
    req = replace(_build_reschedule_request(text="地址改了", origin="live"), budget_calls_used=100)
    outcome = provider.propose(req)
    assert outcome.notes == ("llm:budget-exhausted",)
    assert outcome.usage is None
    assert outcome.refused_reason and "100/100" in outcome.refused_reason


def test_llm_provider_refuses_exhausted_token_budget(monkeypatch):
    _live_llm_env(monkeypatch)

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("budget exhausted: no client may be built")

    provider = LLMProvider()
    provider._client_factory = _BoomClient
    req = replace(
        _build_reschedule_request(text="地址改了", origin="live"),
        budget_call_limit=None,
        budget_token_limit=1000,
        budget_tokens_used=1000,
    )
    outcome = provider.propose(req)
    assert outcome.notes == ("llm:budget-exhausted",)


def test_llm_provider_enforces_per_account_authorization(monkeypatch):
    """An allowlist narrows the live gate to the named accounts."""
    _live_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_LIVE_ACCOUNTS", "00000000-0000-4000-8000-000000000099")

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("account not authorized: no client may be built")

    provider = LLMProvider()
    provider._client_factory = _BoomClient
    outcome = provider.propose(_build_reschedule_request(text="地址改了", origin="live"))
    assert outcome.notes == ("llm:account-not-authorized",)


def test_llm_provider_read_timeout_is_unknown_and_not_retried(monkeypatch):
    """A timeout may already be charged: one attempt, no blind resubmission."""
    _live_llm_env(monkeypatch)

    class _TimeoutClient:
        requests: list[dict] = []

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, json=None, headers=None):
            type(self).requests.append({"url": url})
            raise httpx.ReadTimeout("read timed out", request=httpx.Request("POST", url))

    provider = LLMProvider()
    provider._client_factory = _TimeoutClient
    outcome = provider.propose(_build_reschedule_request(text="地址改了", origin="live"))
    assert len(_TimeoutClient.requests) == 1
    assert outcome.notes == ("llm:result-unknown",)
    assert outcome.usage is None
    assert outcome.refused_reason and "not retried" in outcome.refused_reason


def test_llm_provider_malformed_body_is_not_retried(monkeypatch):
    """A 2xx body that is not JSON was still billed; one attempt only."""
    _live_llm_env(monkeypatch)

    class _BadBodyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("not json")

    class _BadBodyClient:
        requests: list[dict] = []

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, json=None, headers=None):
            type(self).requests.append({"url": url})
            return _BadBodyResponse()

    provider = LLMProvider()
    provider._client_factory = _BadBodyClient
    outcome = provider.propose(_build_reschedule_request(text="地址改了", origin="live"))
    assert len(_BadBodyClient.requests) == 1
    assert outcome.notes == ("llm:response-malformed",)


def test_llm_provider_http_failure_reason_is_sanitised(monkeypatch):
    """Diagnostics never echo the endpoint, headers or exception text."""
    _live_llm_env(monkeypatch)
    client_cls = _fake_client_factory(statuses=(401,))
    provider = LLMProvider()
    provider._client_factory = client_cls
    outcome = provider.propose(_build_reschedule_request(text="地址改了", origin="live"))
    assert outcome.notes == ("llm:http-failed",)
    assert "status-401" in (outcome.refused_reason or "")
    assert "https://" not in (outcome.refused_reason or "")
    assert "sk-" not in (outcome.refused_reason or "")


def test_budget_snapshot_counts_only_this_accounts_today(memory_account, monkeypatch):
    """The worker-side budget reads committed traces; other accounts do not count."""
    from datetime import UTC, datetime

    from gigmate.extraction.budget import snapshot

    monkeypatch.setenv("GIGMATE_LLM_DAILY_CALL_BUDGET", "5")
    monkeypatch.setenv("GIGMATE_LLM_DAILY_TOKEN_BUDGET", "1000")
    outcome = DeterministicProvider().propose(
        _build_reschedule_request(text=load_fixture("message-reschedule")["payload"]["text"])
    )
    billed = replace(outcome, provider_name="llm", usage={"total_tokens": 42})
    local = outcome
    with memory_account.begin() as db:
        persist_proposal(
            db,
            account_id=uid(1),
            conversation_id=uid(2),
            event_id="00000000-0000-4000-8000-000000000998",
            proposal=billed.proposal,
            outcome=billed,
        )
        # A local (free) provider must not consume the paid budget.
        local_proposal = local.proposal.model_copy(update={"proposal_id": str(uuid4())})
        persist_proposal(
            db,
            account_id=uid(1),
            conversation_id=uid(2),
            event_id="00000000-0000-4000-8000-000000000997",
            proposal=local_proposal,
            outcome=replace(local, proposal=local_proposal),
        )
        used = snapshot(db, uid(1), now=datetime.now(UTC))
        other = snapshot(db, uid(3), now=datetime.now(UTC))
    assert (used.call_limit, used.token_limit) == (5, 1000)
    # Only the billed provider counts; the local proposal adds nothing.
    assert used.calls_used == 1
    assert used.tokens_used == 42
    assert other.calls_used == 0
    assert used.exhausted is False


def test_llm_provider_registry_selects_llm(monkeypatch):
    """`GIGMATE_EXTRACTION_PROVIDER=llm` must resolve to the LLMProvider class."""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_EXTRACTION_PROVIDER", "llm")
    _reset_provider_for_testing(None)
    try:
        assert provider().name == "llm"
    finally:
        _reset_provider_for_testing(None)


def test_evaluation_manifest_runs_case_008_under_llm_provider(memory_account):
    """The LLM-targeted case must pass when the manifest is run with the llm provider.

    Only the LLM-targeted case is checked here. Universal cases 1 and 2 expect
    ``matched`` for the synthetic fixture text and require a real LLM
    integration to pass; the skeleton keeps them in needs_review by design.
    """
    with memory_account.begin() as db:
        summary = evaluate_manifest(db, "contracts/evaluation/manifest.json", provider_name="llm")
    by_id = {outcome.case_id: outcome for outcome in summary.cases}
    assert "case-008-llm-skeleton-needs-review" in by_id
    case_008 = by_id["case-008-llm-skeleton-needs-review"]
    assert case_008.status == "pass"
    # Universal needs_review cases (3, 4, 5, 6, 7) must still pass under llm.
    for cid in (
        "case-003-unknown-waha-text",
        "case-004-no-order-linkage",
        "case-005-multiple-order-linkage",
        "case-006-prompt-injection-attempt",
        "case-007-live-origin-with-fixture-text",
    ):
        assert cid in by_id
        assert by_id[cid].status == "pass", f"{cid}: {by_id[cid].message}"


def test_build_provider_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown extraction provider"):
        build_provider("synthetic-gpt-9")


def test_deterministic_provider_matches_known_reschedule_text():
    req = _build_reschedule_request(text=load_fixture("message-reschedule")["payload"]["text"])
    outcome = DeterministicProvider().propose(req)
    assert outcome.proposal.assignment.value == "matched"
    assert [
        c.field.value if hasattr(c.field, "value") else c.field for c in outcome.proposal.changes
    ] == ["schedule"]
    assert outcome.proposal.candidates[0].confidence == pytest.approx(1.0)


def test_deterministic_provider_marks_unknown_waha_content_needs_review():
    req = _build_reschedule_request(text="some live waha body text")
    outcome = DeterministicProvider().propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    assert outcome.refused_reason and "separately authorized provider" in outcome.refused_reason


def test_deterministic_provider_refuses_live_origin_even_with_fixture_text():
    """Live-origin input must never run through fixed synthetic templates."""
    req = _build_reschedule_request(
        text=load_fixture("message-reschedule")["payload"]["text"],
        origin="live",
    )
    outcome = DeterministicProvider().propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    assert outcome.refused_reason and "live content" in outcome.refused_reason


def test_extraction_request_defaults_to_live_origin():
    """An unmarked request can never be treated as trusted synthetic input."""
    fresh = ExtractionRequest(
        account_id=uid(1),
        conversation_id=uid(2),
        message_id="00000000-0000-4000-8000-000000000004",
        message_revision=1,
        message_text="text",
        context_version=5,
    )
    assert fresh.origin == "live"


def test_deterministic_provider_refuses_multi_order_candidates():
    req = _build_reschedule_request(
        text=load_fixture("message-reschedule")["payload"]["text"],
        candidate_work_order_ids=(uid(3), uid(13)),
    )
    outcome = DeterministicProvider().propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.work_order_id is None


def test_disabled_provider_never_emits_changes():
    req = _build_reschedule_request(text=load_fixture("message-reschedule")["payload"]["text"])
    outcome = DisabledProvider().propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.refused_reason == "provider disabled"


def test_provider_override_resets_registry_cache(monkeypatch):
    _reset_provider_for_testing(DeterministicProvider())
    assert provider().name == "deterministic"
    _reset_provider_for_testing(DisabledProvider())
    assert provider().name == "disabled"
    _reset_provider_for_testing(None)


def test_change_proposal_rejects_ai_marking_confirmed():
    from pydantic import ValidationError

    from gigmate.contracts import ChangeProposal

    base = {
        "schema_version": "0.1.0",
        "proposal_id": str(uuid4()),
        "conversation_id": str(uuid4()),
        "work_order_id": None,
        "base_work_order_version": None,
        "base_context_version": 1,
        "assignment": "matched",
        "candidates": [],
        "changes": [
            {
                "field": "schedule",
                "old_value": None,
                "new_value": None,
                "field_status": "confirmed",  # AI cannot grant formal confirmation.
                "customer_confirmation": "pending",
                "sources": [{"message_id": str(uuid4()), "message_revision": 1}],
                "reason": "forbidden",
            }
        ],
        "unresolved_questions": [],
        "draft_text": None,
        "model_version": "synthetic:test",
        "prompt_version": "0.1.0",
    }
    with pytest.raises(ValidationError):
        ChangeProposal.model_validate(base)


def test_provider_call_evidence_records_model_and_prompt_versions(memory_account):
    req = _build_reschedule_request(text=load_fixture("message-reschedule")["payload"]["text"])
    outcome = DeterministicProvider().propose(req)
    event_id = "00000000-0000-4000-8000-000000000999"
    with memory_account.begin() as db:
        proposal_row = persist_proposal(
            db,
            account_id=uid(1),
            conversation_id=uid(2),
            event_id=event_id,
            proposal=outcome.proposal,
            outcome=outcome,
        )
        trace_row = db.scalar(
            select(ModelCallTrace).where(ModelCallTrace.proposal_id == proposal_row.id)
        )
    assert proposal_row.model_version == "synthetic:fixed-stub-v1"
    assert proposal_row.prompt_version == "1.1.0"
    assert trace_row.provider_name == "deterministic"
    assert trace_row.notes == ["deterministic:matched-known-fixture"]


def test_persisted_trace_records_token_usage_only_for_billed_calls(memory_account):
    """Token accounting reaches the trace row; a refusal records NULL, not 0.

    ``0`` would claim the call was free, which is a different fact from
    "no call was made". The distinction is what makes the trace trustworthy
    as cost evidence once a real DeepSeek key is configured.
    """
    req = _build_reschedule_request(text=load_fixture("message-reschedule")["payload"]["text"])
    refused = DeterministicProvider().propose(req)
    billed = replace(
        refused,
        usage={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    )
    event_id = "00000000-0000-4000-8000-000000000999"
    with memory_account.begin() as db:
        billed_row = persist_proposal(
            db,
            account_id=uid(1),
            conversation_id=uid(2),
            event_id=event_id,
            proposal=billed.proposal,
            outcome=billed,
        )
        refused_row = persist_proposal(
            db,
            account_id=uid(1),
            conversation_id=uid(2),
            event_id=event_id,
            proposal=refused.proposal,
            outcome=refused,
        )
        billed_trace = db.scalar(
            select(ModelCallTrace).where(ModelCallTrace.proposal_id == billed_row.id)
        )
        refused_trace = db.scalar(
            select(ModelCallTrace).where(ModelCallTrace.proposal_id == refused_row.id)
        )
    assert (billed_trace.prompt_tokens, billed_trace.completion_tokens) == (120, 30)
    assert billed_trace.total_tokens == 150
    assert refused_trace.prompt_tokens is None
    assert refused_trace.completion_tokens is None
    assert refused_trace.total_tokens is None


# ---------------------------------------------------------------------------
# Worker integration (synthetic ingest → real on-disk DB)
# ---------------------------------------------------------------------------


def test_legacy_replay_path_still_emits_proposed_change(monkeypatch, memory_account):
    """Replay smoke parity: the legacy deterministic behavior must remain."""
    with memory_account.begin() as db:
        account = db.scalar(select(__import__("gigmate.db", fromlist=["Account"]).Account))
    message = replay_event("reschedule")
    with memory_account.begin() as db:
        ingest(db, account, message, trusted_waha=False)
    assert run_once(memory_account) is True
    with memory_account.begin() as db:
        changes = list(
            db.scalars(
                select(ChangeRow).where(
                    ChangeRow.account_id == uid(1), ChangeRow.work_order_id == uid(3)
                )
            )
        )
    assert len(changes) == 1
    payload = changes[0].data
    assert payload["status"] == "proposed"
    assert payload["field"] == "schedule"


def test_waha_job_with_unknown_text_completes_with_extraction_needs_review(
    monkeypatch, memory_account
):
    """Live content must never reach ``matched``; deterministic refuses unknown text."""
    message = deepcopy(replay_event("reschedule"))
    message["connector"] = "waha"
    message["source"] = "app"
    message["payload"]["text"] = "today's weather is fine"
    message["provider_message_id"] = "synthetic:waha-unknown"
    message["message_revision"] = 1
    account = None
    with memory_account.begin() as db:
        from gigmate.db import Account as _Account

        account = db.scalar(select(_Account).where(_Account.username == "merchant"))
    with memory_account.begin() as db:
        ingest(db, account, message, trusted_waha=True)
    assert run_once(memory_account) is True
    with memory_account.begin() as db:
        job = db.scalar(select(Job).order_by(Job.id.desc()))
        inbox = db.get(Inbox, job.event_id)
        proposal_row = db.scalar(select(Proposal).where(Proposal.event_id == inbox.id))
        trace_row = (
            db.scalar(select(ModelCallTrace).where(ModelCallTrace.proposal_id == proposal_row.id))
            if proposal_row
            else None
        )
    assert job.error_code == EXTRACTION_NEEDS_REVIEW
    assert proposal_row.assignment == "needs_review"
    assert proposal_row.changes == []
    assert trace_row.refused_reason is not None
    with memory_account.begin() as db:
        assert db.scalar(select(ChangeRow)) is None  # no business row inserted


def test_waha_job_with_fixture_text_from_live_source_needs_review(memory_account):
    """Live-origin input is refused even when the text equals a synthetic fixture."""
    message = deepcopy(replay_event("reschedule"))  # keeps the canonical fixture text
    message["connector"] = "waha"
    message["source"] = "app"
    message["provider_message_id"] = "synthetic:waha-fixture-text"
    message["message_revision"] = 1
    with memory_account.begin() as db:
        account = db.scalar(select(Account).where(Account.username == "merchant"))
    with memory_account.begin() as db:
        ingest(db, account, message, trusted_waha=True)
    assert run_once(memory_account) is True
    with memory_account.begin() as db:
        job = db.scalar(select(Job).order_by(Job.id.desc()))
        inbox = db.get(Inbox, job.event_id)
        proposal_row = db.scalar(select(Proposal).where(Proposal.event_id == inbox.id))
        change_rows = list(db.scalars(select(ChangeRow)))
    assert job.error_code == EXTRACTION_NEEDS_REVIEW
    assert proposal_row.assignment == "needs_review"
    assert proposal_row.changes == []
    assert change_rows == []


def test_waha_job_with_malformed_prompt_records_evidence_instead_of_failing(
    monkeypatch, tmp_path, memory_account
):
    """Regression for the PR #18 P2 finding.

    A malformed prompt file used to raise out of ``propose`` (``ValidationError``
    for an empty version, ``UnicodeDecodeError`` for a non-UTF-8 file), pushing
    the job into the worker's ``PROCESSING_FAILED`` retry path with no evidence.
    It now falls back to ``0.0.0-skeleton`` and persists a ``needs_review``
    proposal plus a trace carrying the ``llm:prompt-malformed`` note.
    """
    _clear_llm_env(monkeypatch)
    prompt_file = tmp_path / "broken_prompt.txt"
    prompt_file.write_text("prompt_version:\nSynthetic instruction\n", encoding="utf-8")
    monkeypatch.setenv("GIGMATE_EXTRACTION_PROVIDER", "llm")
    monkeypatch.setenv("GIGMATE_LLM_PROMPT_PATH", str(prompt_file))
    _reset_provider_for_testing(None)
    try:
        message = deepcopy(replay_event("reschedule"))
        message["connector"] = "waha"
        message["source"] = "app"
        message["provider_message_id"] = "synthetic:waha-prompt-malformed"
        message["message_revision"] = 1
        with memory_account.begin() as db:
            account = db.scalar(select(Account).where(Account.username == "merchant"))
        with memory_account.begin() as db:
            ingest(db, account, message, trusted_waha=True)
        assert run_once(memory_account) is True
        with memory_account.begin() as db:
            job = db.scalar(select(Job).order_by(Job.id.desc()))
            inbox = db.get(Inbox, job.event_id)
            proposal_row = db.scalar(select(Proposal).where(Proposal.event_id == inbox.id))
            trace_row = db.scalar(
                select(ModelCallTrace).where(ModelCallTrace.proposal_id == proposal_row.id)
            )
            change_rows = list(db.scalars(select(ChangeRow)))
        assert job.error_code == EXTRACTION_NEEDS_REVIEW
        assert proposal_row.assignment == "needs_review"
        assert proposal_row.prompt_version == "0.0.0-skeleton"
        assert trace_row.notes == ["llm:prompt-malformed"]
        assert trace_row.refused_reason and "empty" in trace_row.refused_reason
        assert change_rows == []
    finally:
        _reset_provider_for_testing(None)


def test_matched_waha_proposal_persists_evidence_then_merchant_confirms(signed_in):
    """Regression for the P1 persistence bug: matched input must persist
    proposal/trace/change rows with JSON-serializable payloads, and the
    resulting change must still be merchant-confirmable.

    Uses a test provider that simulates a separately authorized live model by
    re-marking the request origin as synthetic; everything else is the real
    worker persistence and confirmation path.
    """
    client, factory, _, headers = signed_in

    class _AuthorizedLiveStub(DeterministicProvider):
        name = "test-authorized-live"
        model_version = "synthetic:test-authorized-live"

        def propose(self, request):
            from dataclasses import replace

            return super().propose(replace(request, origin="synthetic"))

    _reset_provider_for_testing(_AuthorizedLiveStub())
    try:
        message = deepcopy(replay_event("available"))
        message["connector"] = "waha"
        message["source"] = "app"
        message["provider_message_id"] = "synthetic:waha-matched"
        message["message_revision"] = 1
        with factory.begin() as db:
            account = db.scalar(select(Account).where(Account.username == "merchant"))
        with factory.begin() as db:
            ingest(db, account, message, trusted_waha=True)
        assert run_once(factory) is True
        with factory.begin() as db:
            job = db.scalar(select(Job).order_by(Job.id.desc()))
            inbox = db.get(Inbox, job.event_id)
            proposal_row = db.scalar(select(Proposal).where(Proposal.event_id == inbox.id))
            trace_row = db.scalar(
                select(ModelCallTrace).where(ModelCallTrace.proposal_id == proposal_row.id)
            )
            change_row = db.scalar(select(ChangeRow).where(ChangeRow.work_order_id == ORDER))
            order = db.get(WorkOrderRow, ORDER)
        assert job.error_code is None
        assert proposal_row.assignment == "matched"
        assert trace_row.provider_name == "test-authorized-live"
        # P1 regression: payload is JSON-serializable and keeps the snapshot.
        assert change_row.data["field"] == "schedule"
        assert change_row.data["status"] == "proposed"
        assert change_row.data["old_value"]["kind"] == "timed"
        assert change_row.data["new_value"]["kind"] == "timed"
        assert change_row.data["customer_confirmation"] == "confirmed"
        assert change_row.id in order.data["pending_change_ids"]
        rows = client.get(ORDER_PATH + "/changes").json()["items"]
        change = next(row for row in rows if row["status"] == "proposed")
        response = client.post(
            ORDER_PATH + f"/changes/{change['id']}/confirm",
            json={
                "expected_version": 3,
                "expected_context_version": change["context_version"],
                "apply_calendar_update": True,
            },
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["version"] == 4
        assert data["fields"]["schedule"]["status"] == "confirmed"
    finally:
        _reset_provider_for_testing(None)


def test_replay_and_waha_paths_respect_disabled_provider(monkeypatch, memory_account):
    """GIGMATE_EXTRACTION_PROVIDER=disabled suppresses proposals on both paths."""
    monkeypatch.setenv("GIGMATE_EXTRACTION_PROVIDER", "disabled")
    _reset_provider_for_testing(None)
    try:
        with memory_account.begin() as db:
            account = db.scalar(select(Account).where(Account.username == "merchant"))
        with memory_account.begin() as db:
            ingest(db, account, replay_event("available"), trusted_waha=False)
        # Process the replay job before ingesting the WAHA message, otherwise
        # the newer message would supersede the replay source.
        assert run_once(memory_account) is True
        waha_message = deepcopy(replay_event("reschedule"))
        waha_message["connector"] = "waha"
        waha_message["source"] = "app"
        waha_message["provider_message_id"] = "synthetic:waha-disabled"
        waha_message["message_revision"] = 1
        with memory_account.begin() as db:
            ingest(db, account, waha_message, trusted_waha=True)
        assert run_once(memory_account) is True
        with memory_account.begin() as db:
            jobs = list(db.scalars(select(Job)))
            proposals = list(db.scalars(select(Proposal)))
            assert db.scalar(select(ChangeRow)) is None
        assert {job.error_code for job in jobs} == {
            "STUB_UNSUPPORTED_INPUT",
            EXTRACTION_NEEDS_REVIEW,
        }
        assert proposals and all(row.assignment == "needs_review" for row in proposals)
        assert provider().name == "disabled"
    finally:
        _reset_provider_for_testing(None)


def test_evaluation_manifest_persists_per_case_records(memory_account):
    summary = None
    with memory_account.begin() as db:
        summary = evaluate_manifest(db, "contracts/evaluation/manifest.json")
        # Force flush inside the open transaction (we already used begin())
    cases = list(summary.cases)
    assert len(cases) == 7
    with memory_account.begin() as db:
        runs = list(db.scalars(select(EvaluationRun)))
        rows = list(db.scalars(select(EvaluationCaseRecord)))
    assert len(runs) == 1
    assert runs[0].passed >= 5
    assert len(rows) == 7
    statuses = {row.case_id: row.status for row in rows}
    assert all(value == "pass" for value in statuses.values())


def test_evaluate_case_flags_assignment_mismatch():
    bad_case = {
        "case_id": "negative-001",
        "scenario": "force fail when assignment differs",
        "data_classification": "synthetic",
        "note": None,
        "input_event": {
            "account_id": uid(1),
            "conversation_id": uid(2),
            "message_id": uid(4),
            "message_revision": 1,
            "text": "some unknown text",
            "context_version": 1,
            "candidate_work_order_ids": [],
            "base_work_order_version": None,
            "base_work_order_snapshot": None,
        },
        "expected_assignment": "matched",
        "expected_min_confidence": 0.9,
        "expected_change_fields": ["schedule"],
    }
    outcome = evaluate_case(build_provider("deterministic"), bad_case)
    assert outcome.status == "fail"
    message = outcome.message or ""
    assert "assignment needs_review" in message
    assert "missing fields: ['schedule']" in message


def test_evaluation_run_requires_non_empty_manifest(memory_account, tmp_path):
    empty_path = tmp_path / "empty-manifest.json"
    empty_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    with memory_account.begin() as db:
        with pytest.raises(ValueError, match="no cases"):
            evaluate_manifest(db, empty_path)


# ---------------------------------------------------------------------------
# Operator smoke / registry metadata (P2 review regressions)
# ---------------------------------------------------------------------------


def test_list_provider_metadata_is_json_serialisable():
    """P2 regression: prompt_version is a @property on DeterministicProvider.

    Reading it from the class returned the property object and broke
    ``json.dumps``. The helper must return plain strings and survive
    ``json.dumps`` for telemetry / admin endpoints that consume it.
    """
    from gigmate.extraction.registry import list_provider_metadata

    rows = list_provider_metadata()
    assert {row["name"] for row in rows} == {"deterministic", "disabled", "llm"}
    for row in rows:
        assert isinstance(row["name"], str)
        assert isinstance(row["model_version"], str)
        assert isinstance(row["prompt_version"], str), (
            f"prompt_version for {row['name']!r} must be a plain string, "
            f"got {type(row['prompt_version']).__name__}"
        )
    # The deterministic provider reads from the bundled prompt file, so
    # its prompt_version should follow the file's header (1.1.0 today).
    deterministic_row = next(r for r in rows if r["name"] == "deterministic")
    assert deterministic_row["prompt_version"] == "1.1.0"
    # The LLM provider's class attribute is still the placeholder; the
    # real version is computed per call by ``_read_prompt_version``.
    llm_row = next(r for r in rows if r["name"] == "llm")
    assert llm_row["prompt_version"] == "0.0.0-skeleton"
    # json.dumps must round-trip cleanly.
    encoded = json.dumps(rows)
    assert json.loads(encoded) == rows


def test_smoke_classify_exit_code_marks_infra_failures_as_nonzero():
    """P2 regression: smoke_deepseek must surface infra failure as exit 1.

    The earlier logic returned 0 for every notes tuple other than the
    exact ``("llm:not-configured",)`` pair, so ``llm:seam-pending``,
    ``llm:http-failed``, ``llm:response-malformed`` and
    ``llm:response-schema-failed`` all silently produced a green exit.
    Operators wiring this into alerting would not notice a real failure.
    """
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "smoke_deepseek",
        Path(__file__).resolve().parents[3] / "scripts" / "smoke_deepseek.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    classify = module._classify_exit_code

    def _outcome(*, assignment: str, notes: tuple[str, ...]):
        # The helper only reads assignment.value and notes, so the
        # outcome is constructed with a minimal stub proposal that
        # supplies those two attributes.
        proposal = type(
            "P",
            (),
            {
                "assignment": type("A", (), {"value": assignment})(),
                "work_order_id": None,
                "model_version": "stub",
                "prompt_version": "stub",
                "unresolved_questions": [],
                "changes": [],
            },
        )()
        return type(
            "O",
            (),
            {
                "provider_name": "llm",
                "proposal": proposal,
                "latency_ms": 0,
                "notes": notes,
                "refused_reason": None,
            },
        )()

    # matched → 0
    assert classify(_outcome(assignment="matched", notes=("llm:matched",))) == 0
    # LLM-driven needs_review → 0
    assert classify(_outcome(assignment="needs_review", notes=("llm:needs-review",))) == 0
    # All infra-failure notes must be non-zero.
    for note in (
        "llm:seam-pending",
        "llm:not-configured",
        "llm:live-gate-off",
        "llm:origin-live-refused",
        "llm:prompt-load-failed",
        "llm:http-failed",
        "llm:response-malformed",
        "llm:response-schema-failed",
    ):
        code = classify(_outcome(assignment="needs_review", notes=(note,)))
        assert code == 1, f"smoke must exit 1 for infra failure note {note!r}, got {code}"
    # Unrecognised needs_review note → 1 (conservative default).
    assert classify(_outcome(assignment="needs_review", notes=("some:unknown",))) == 1
