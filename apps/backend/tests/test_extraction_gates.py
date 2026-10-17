"""Pre-activation acceptance gates for the Role B real-text activation batch.

The five guards are listed in ``docs/en/role-b-extraction.md`` under
"Pre-activation acceptance gates". They must be cleared before
``LLMProvider._SKELETON_SEAM`` may be flipped. Every test here drives the
provider through the injected ``_client_factory`` seam, so no network call,
real credential or real model is involved and the seam itself stays closed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gigmate.contracts import ChangeProposal
from gigmate.db import (
    Account,
    Base,
    ConversationOrder,
    ConversationRow,
    Inbox,
    ModelCallTrace,
    Proposal,
    WorkOrderRow,
)
from gigmate.extraction import llm as llm_module
from gigmate.extraction.llm import LLMProvider
from gigmate.extraction.persistence import persist_proposal
from gigmate.extraction.registry import _reset_provider_for_testing
from gigmate.extraction.types import ExtractionOutcome, ExtractionRequest
from gigmate.seed import uid
from gigmate.worker import _route_through_provider, _workspace_timezone

ACCOUNT_ID = uid(1)
CONVERSATION_ID = "00000000-0000-4000-8000-000000000002"
CANDIDATE = "00000000-0000-4000-8000-000000000003"
MESSAGE_ID = "00000000-0000-4000-8000-000000000004"

RECEIVED_AT = "2026-10-07T00:00:00Z"
TIMEZONE = "Asia/Hong_Kong"


# ---------------------------------------------------------------------------
# Helpers
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
    }
    values.update(overrides)
    return ExtractionRequest(**values)


def _grounded_request(**overrides) -> ExtractionRequest:
    """A request that carries the gate-4 time basis."""
    values = {"message_received_at": RECEIVED_AT, "workspace_timezone": TIMEZONE}
    values.update(overrides)
    return _request(**values)


def _schedule_payload(**overrides) -> dict:
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


def _address_payload() -> dict:
    return _schedule_payload(
        changes=[
            {
                "field": "address",
                "old_value": None,
                "new_value": "中环德辅道中 88 號",
                "field_status": "proposed",
                "customer_confirmation": "confirmed",
                "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
                "reason": "Customer supplied the meeting address.",
            }
        ]
    )


def _instant_payload(**overrides) -> dict:
    """A ``deadline`` change carrying the ``InstantDeadline`` (kind=instant) shape."""
    payload = _schedule_payload()
    payload["changes"] = [
        {
            "field": "deadline",
            "old_value": None,
            "new_value": {
                "kind": "instant",
                "at": "2026-10-18T07:00:00Z",
                "timezone": TIMEZONE,
            },
            "field_status": "proposed",
            "customer_confirmation": "pending",
            "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
            "reason": "Customer promised to deliver tomorrow.",
        }
    ]
    payload.update(overrides)
    return payload


class _FakeClock:
    """Monotonic test clock. The fake clients advance it as they "spend" time."""

    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _timeout_client(clock: _FakeClock):
    """A client that always times out, spending the whole budget it was granted.

    The budget is the **sum** of the ``httpx`` timeout components: a scalar
    timeout is copied into every operation, so granting "30 s" used to allow
    30 s of connecting plus 30 s of reading inside one attempt.
    """

    class _Client:
        requests: list[dict] = []

        def __init__(self, **kwargs):
            self.timeout = kwargs.get("timeout")
            self.budget = llm_module._timeout_budget_s(self.timeout)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, json=None, headers=None):
            type(self).requests.append({"timeout": self.timeout, "budget": self.budget})
            clock.advance(self.budget)
            raise httpx.ReadTimeout("timed out")

        def stream(self, method, url, json=None, headers=None):
            return _StreamedResponse(self.post(url, json=json, headers=headers))

    return _Client


def _slow_success_client(clock: _FakeClock, payload: dict, *, seconds: float):
    """A client that answers, but only after ``seconds`` of wall clock."""

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    class _Client:
        requests: list[dict] = []

        def __init__(self, **kwargs):
            self.timeout = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, json=None, headers=None):
            type(self).requests.append({"timeout": self.timeout})
            clock.advance(seconds)
            return _Response()

        def stream(self, method, url, json=None, headers=None):
            return _StreamedResponse(self.post(url, json=json, headers=headers))

    return _Client


def _run_with_clock(monkeypatch, clock, client, request=None, **env):
    """Drive the provider with the fake clock installed as the deadline basis."""
    _configure(monkeypatch, **env)
    monkeypatch.setattr(llm_module, "_now", clock)
    provider = _gate_open_provider(client)
    return provider.propose(request or _grounded_request())


def _scripted_client(payload, *, status_code=200):
    """Fake ``httpx`` client replaying ``payload``, or failing with ``status_code``."""

    class _Response:
        def __init__(self):
            self.status_code = status_code

        def raise_for_status(self):
            if status_code >= 400:
                request = httpx.Request("POST", "https://fake.example.test/v1/chat/completions")
                raise httpx.HTTPStatusError("bad status", request=request, response=self)

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

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


def _configure(monkeypatch, *, vendor="openai", **extra):
    for name in (
        "GIGMATE_LLM_PROVIDER",
        "GIGMATE_LLM_MODEL",
        "GIGMATE_LLM_API_KEY",
        "GIGMATE_LLM_ENDPOINT",
        "GIGMATE_LLM_PROMPT_PATH",
        "GIGMATE_LLM_LIVE",
        "GIGMATE_LLM_ALLOW_LIVE_ORIGIN",
        "GIGMATE_WORKSPACE_TIMEZONE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", vendor)
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-fake-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "https://fake.example.test")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def _run(monkeypatch, payload, request, *, vendor="openai", **env):
    """Drive the provider with both gates open and a scripted vendor response."""
    _configure(monkeypatch, vendor=vendor, **env)
    client = _scripted_client(payload)
    provider = _gate_open_provider(client)
    outcome = provider.propose(request)
    return outcome, client


def _gate_open_provider(client):
    class _GateOpen(LLMProvider):
        _SKELETON_SEAM = False

    provider = _GateOpen()
    provider._client_factory = client
    return provider


# ---------------------------------------------------------------------------
# Gate 1 — trusted identity and provenance must not be decided by the model
# ---------------------------------------------------------------------------


def test_gate1_work_order_id_outside_candidates_is_refused(monkeypatch):
    payload = _schedule_payload(work_order_id="00000000-0000-4000-8000-000000000099")
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == "llm:response-provenance-failed:work_order_id"


def test_gate1_foreign_conversation_id_is_refused(monkeypatch):
    payload = _schedule_payload(conversation_id="00000000-0000-4000-8000-000000000009")
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == "llm:response-provenance-failed:conversation_id"


def test_gate1_stale_base_work_order_version_is_refused(monkeypatch):
    payload = _schedule_payload(base_work_order_version=9)
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == "llm:response-provenance-failed:base_work_order_version"


@pytest.mark.parametrize(
    "sources",
    [
        [{"message_id": "00000000-0000-4000-8000-00000000000a", "message_revision": 1}],
        [{"message_id": MESSAGE_ID, "message_revision": 2}],
    ],
)
def test_gate1_sources_are_rebound_to_the_issued_message(monkeypatch, sources):
    """A source identifier is server-owned, not whatever the vendor echoed.

    Real vendors echo the wrong identifier routinely (observed: DeepSeek wrote
    the work-order id into ``sources[].message_id``). Because a request carries
    exactly one message, the server writes its own value instead of trusting the
    echo — and says so on the trace. An empty ``sources`` list is still refused:
    a change with no origin at all is not a proposal, it is a guess.
    """

    request = _grounded_request()
    payload = _schedule_payload()
    payload["changes"][0]["sources"] = sources
    outcome, _ = _run(monkeypatch, payload, request)
    assert outcome.refused_reason is None
    assert outcome.proposal.assignment.value == "matched"
    bound = outcome.proposal.changes[0].sources[0]
    assert bound.message_id == request.message_id
    assert bound.message_revision == request.message_revision
    # The correction is visible on the trace whenever the vendor echoed a
    # different identifier.
    assert ("llm:source-rebound" in outcome.notes) == (
        sources[0]["message_id"] != request.message_id
    )


@pytest.mark.parametrize("sources", [[], None])
def test_gate1_change_without_any_source_is_refused(monkeypatch, sources):
    payload = _schedule_payload()
    payload["changes"][0]["sources"] = sources
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == "llm:response-provenance-failed:source-missing"


def test_gate1_correctly_bound_response_still_matches(monkeypatch):
    outcome, _ = _run(monkeypatch, _schedule_payload(), _grounded_request())
    assert outcome.notes == ("llm:matched",)
    assert outcome.proposal.assignment.value == "matched"
    assert outcome.proposal.work_order_id == CANDIDATE
    assert outcome.refused_reason is None


def test_gate1_foreign_base_context_version_is_refused(monkeypatch):
    """The model must not be able to move a proposal onto another context version."""
    outcome, _ = _run(
        monkeypatch,
        _schedule_payload(base_context_version=999),
        _grounded_request(context_version=7),
    )
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == "llm:response-provenance-failed:base_context_version"


def test_gate1_server_context_version_is_always_bound(monkeypatch):
    """The context version of the emitted proposal is the request's, never the model's."""
    outcome, _ = _run(
        monkeypatch,
        _schedule_payload(base_context_version=7),
        _grounded_request(context_version=7),
    )
    assert outcome.notes == ("llm:matched",)
    assert outcome.proposal.base_context_version == 7


@pytest.mark.parametrize("echoed", [7.0, "7", True, "7.0"])
def test_gate1_coerced_context_version_is_refused(monkeypatch, echoed):
    """Review round 2: a value that merely *compares* equal is still the model's.

    ``7.0 == 7`` and ``True == 1`` in Python, so an equality check alone let a
    non-integer echo through; the request's context version is an integer and
    anything else the model says about it is a mismatch.
    """
    outcome, _ = _run(
        monkeypatch,
        _schedule_payload(base_context_version=echoed),
        _grounded_request(context_version=7),
    )
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == "llm:response-provenance-failed:base_context_version"


@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        ("candidates", "llm:response-provenance-failed:candidates-shape"),
        ("unresolved_questions", "llm:response-provenance-failed:unresolved-questions-shape"),
    ],
)
def test_gate1_proposal_level_collections_are_shape_checked(monkeypatch, shape, expected):
    """Review round 2: every collection the guard reads is checked before use."""
    payload = _schedule_payload()
    payload[shape] = 17
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == expected


@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        ("missing_fields", "llm:response-provenance-failed:missing-fields-shape"),
        ("unresolved_questions", "llm:response-provenance-failed:suggested-questions-shape"),
    ],
)
def test_gate1_suggestion_collections_are_shape_checked(monkeypatch, shape, expected):
    payload = {
        "assignment": "needs_review",
        "work_order_id": None,
        "base_work_order_version": None,
        "candidates": [],
        "changes": [],
        "unresolved_questions": [],
        "new_work_order": {
            "summary": "new job",
            "fields": [],
            "missing_fields": [],
            "unresolved_questions": [],
            "confidence": 0.5,
        },
    }
    payload["new_work_order"][shape] = 17
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == expected


@pytest.mark.parametrize("changes", [17, True, "not-a-list"])
def test_gate1_non_list_changes_are_refused(monkeypatch, changes):
    """Legal JSON that is not a list must not raise out of ``propose``."""
    outcome, _ = _run(monkeypatch, _schedule_payload(changes=changes), _grounded_request())
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == "llm:response-provenance-failed:changes-shape"


@pytest.mark.parametrize("sources", [7, True])
def test_gate1_non_list_sources_are_refused(monkeypatch, sources):
    payload = _schedule_payload()
    payload["changes"][0]["sources"] = sources
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason == "llm:response-provenance-failed:source-shape"


# ---------------------------------------------------------------------------
# Gate 2 — vendor / endpoint semantics must be explicit
# ---------------------------------------------------------------------------


def test_gate2_unknown_vendor_is_refused(monkeypatch):
    _configure(monkeypatch, vendor="anthropic")
    provider = _gate_open_provider(_boom_client())
    outcome = provider.propose(_grounded_request())
    assert outcome.notes == ("llm:vendor-unknown",)
    assert "deepseek" in outcome.refused_reason


def test_gate2_custom_vendor_requires_an_endpoint(monkeypatch):
    _configure(monkeypatch, vendor="custom")
    monkeypatch.delenv("GIGMATE_LLM_ENDPOINT", raising=False)
    provider = _gate_open_provider(_boom_client())
    outcome = provider.propose(_grounded_request())
    assert outcome.notes == ("llm:endpoint-required",)


def test_gate2_override_matching_another_vendor_default_is_refused(monkeypatch):
    _configure(monkeypatch, vendor="openai")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "https://api.deepseek.com")
    provider = _gate_open_provider(_boom_client())
    outcome = provider.propose(_grounded_request())
    assert outcome.notes == ("llm:vendor-endpoint-mismatch",)


def test_gate2_non_url_endpoint_is_refused(monkeypatch):
    _configure(monkeypatch, vendor="custom")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "api.deepseek.com")
    provider = _gate_open_provider(_boom_client())
    outcome = provider.propose(_grounded_request())
    assert outcome.notes == ("llm:endpoint-invalid",)


@pytest.mark.parametrize("zero_priced", [False, True])
def test_gate2_zero_budget_never_reaches_the_vendor(monkeypatch, zero_priced):
    """Review round 2: "no money may be spent" is not a budget to fit into.

    A zero-priced worst case (a free local model, or an override of ``0``)
    compared as "within" a zero budget, so the call was still issued; the
    ceiling now refuses a non-positive budget before any pricing arithmetic.
    ``_boom_client`` turns an attempted call into a test failure.
    """
    extra = {}
    if zero_priced:
        extra = {
            "GIGMATE_LLM_COST_INPUT_USD_PER_1K": "0",
            "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K": "0",
        }
    _configure(monkeypatch, GIGMATE_LLM_COST_BUDGET_USD="0", **extra)
    provider = _gate_open_provider(_boom_client())
    outcome = provider.propose(_grounded_request())
    assert outcome.notes == ("llm:cost-budget-exceeded",)
    assert outcome.proposal.assignment.value == "needs_review"
    assert "llm:cost-budget-exceeded" in (outcome.refused_reason or "")


def test_gate2_negative_budget_is_reported_by_the_startup_audit(monkeypatch):
    _configure(monkeypatch, GIGMATE_LLM_COST_BUDGET_USD="-0.01")
    assert "llm:cost-budget-invalid" in llm_module.validate_provider_config()
    _configure(monkeypatch, GIGMATE_LLM_COST_BUDGET_USD="0")
    assert "llm:cost-budget-invalid" not in llm_module.validate_provider_config()


def test_gate2_known_vendor_uses_its_own_default_endpoint(monkeypatch):
    _configure(monkeypatch, vendor="openai")
    monkeypatch.delenv("GIGMATE_LLM_ENDPOINT", raising=False)
    client = _scripted_client({"assignment": "needs_review"})
    provider = _gate_open_provider(client)
    provider.propose(_grounded_request())
    assert client.requests[0]["url"] == "https://api.openai.com/v1/chat/completions"


# ---------------------------------------------------------------------------
# Gate 3 — retry must be designed with the worker lock and lease
# ---------------------------------------------------------------------------


def test_gate3_request_id_is_sent_and_returned(monkeypatch):
    outcome, client = _run(monkeypatch, _schedule_payload(), _grounded_request())
    assert outcome.request_id
    sent = client.requests[0]["headers"][llm_module._REQUEST_ID_HEADER]
    assert sent == outcome.request_id


def test_gate3_request_id_is_persisted_with_the_trace(memory_factory):
    db = memory_factory()
    db.add(Account(id=ACCOUNT_ID, username="gate3", password_hash="x", active=True))
    receipt = Inbox(
        id=str(uuid4()),
        account_id=ACCOUNT_ID,
        payload={},
        digest="d",
        received_at=datetime.now(UTC),
        context_version=5,
    )
    db.add(receipt)
    db.flush()
    proposal = ChangeProposal.model_validate(
        {
            "schema_version": "0.1.0",
            "proposal_id": str(uuid4()),
            "conversation_id": CONVERSATION_ID,
            "work_order_id": None,
            "base_work_order_version": None,
            "base_context_version": 5,
            "assignment": "needs_review",
            "candidates": [],
            "changes": [],
            "unresolved_questions": ["stub"],
            "draft_text": None,
            "model_version": "stub:1",
            "prompt_version": "1.1.0",
        }
    )
    row = persist_proposal(
        db,
        account_id=ACCOUNT_ID,
        conversation_id=CONVERSATION_ID,
        event_id=receipt.id,
        proposal=proposal,
        outcome=ExtractionOutcome(
            provider_name="stub",
            proposal=proposal,
            latency_ms=1,
            notes=("stub",),
            request_id="abc123",
        ),
    )
    db.flush()
    trace = db.scalar(select(ModelCallTrace).where(ModelCallTrace.proposal_id == row.id))
    assert trace.request_id == "abc123"


def test_gate3_client_error_is_not_retried(monkeypatch):
    outcome, client = _run(monkeypatch, {}, _grounded_request())
    del outcome
    assert len(client.requests) == 1


def _run_with_status(monkeypatch, status_code):
    _configure(monkeypatch)
    client = _scripted_client({}, status_code=status_code)
    provider = _gate_open_provider(client)
    outcome = provider.propose(_grounded_request())
    return outcome, client


def test_gate3_server_error_is_retried_once_within_budget(monkeypatch):
    outcome, client = _run_with_status(monkeypatch, 500)
    assert len(client.requests) == 2
    assert outcome.notes == ("llm:http-failed",)
    assert outcome.refused_reason == "llm:http-failed:status-5xx"


def test_gate3_client_error_is_not_retried_within_budget(monkeypatch):
    outcome, client = _run_with_status(monkeypatch, 400)
    assert len(client.requests) == 1
    assert outcome.refused_reason == "llm:http-failed:status-4xx"


def test_gate3_each_attempt_inherits_the_remaining_deadline(monkeypatch):
    """The retry must ask for the remaining budget, not the full per-attempt timeout.

    Counter-case from review: a 30 s timeout that consumed the first 30 s used
    to be followed by another 30 s request, so one extraction ran 60 s against
    its declared deadline. The total budget is now deliberately smaller than the
    worker lease (see ``test_gate3_total_deadline_fits_inside_the_worker_lease``),
    so the per-attempt ceiling is scaled down here as well: two attempts still
    fit inside the budget and the second one is shown to inherit only the rest.
    """
    clock = _FakeClock()
    client = _timeout_client(clock)
    monkeypatch.setattr(llm_module, "_REQUEST_TIMEOUT_S", 4.0)
    outcome = _run_with_clock(monkeypatch, clock, client)
    granted = [request["budget"] for request in client.requests]
    assert len(client.requests) == 2
    # Each attempt is granted only what is left, and together they never exceed
    # the declared total — the exact property that used to be 30 s + 30 s.
    assert granted[0] <= llm_module._TOTAL_DEADLINE_S
    assert granted[1] < granted[0]
    assert sum(granted) == pytest.approx(llm_module._TOTAL_DEADLINE_S)
    assert clock.value - 1000.0 == pytest.approx(llm_module._TOTAL_DEADLINE_S)
    assert outcome.refused_reason == "llm:http-failed:timeout"


def test_gate3_one_attempt_cannot_spend_the_budget_twice(monkeypatch):
    """Review round 2: a scalar timeout bounds each httpx operation separately.

    ``httpx`` copies one timeout value into connect / read / write / pool, so a
    request granted "30 s" could spend 30 s connecting and then 30 s reading.
    The granted components must therefore sum to at most the remaining budget.
    """
    clock = _FakeClock()
    client = _timeout_client(clock)
    _run_with_clock(monkeypatch, clock, client)
    for request in client.requests:
        timeout = request["timeout"]
        assert isinstance(timeout, httpx.Timeout)
        assert request["budget"] <= llm_module._TOTAL_DEADLINE_S
        assert timeout.read is not None and timeout.read <= llm_module._REQUEST_TIMEOUT_S


def test_gate3_attempt_grant_shrinks_with_the_remaining_budget(monkeypatch):
    """A small remaining budget can never be granted twice over."""
    assert llm_module._timeout_budget_s(llm_module._attempt_timeout(45.0)) <= 45.0
    assert llm_module._timeout_budget_s(llm_module._attempt_timeout(10.0)) <= 10.0
    assert llm_module._timeout_budget_s(llm_module._attempt_timeout(3.0)) <= 3.0
    # Below the minimum read budget no attempt is issued at all.
    assert llm_module._attempt_timeout(2.0) is None
    assert llm_module._attempt_timeout(0.0) is None
    assert llm_module._attempt_timeout(-1.0) is None


def test_gate3_total_deadline_fits_inside_the_worker_lease():
    """One extraction must not be able to outlive the worker's job lease.

    Review fix P2-1 (second round). ``gigmate.worker`` takes a 30 s lease and
    does **not** renew it while a job is running — it even drops the result if
    the lease already expired (``worker.py`` re-reads ``lease_until`` after the
    call). A total budget longer than the lease therefore lets a second worker
    reclaim and re-run the same extraction while the first is still talking to
    the vendor, which is the duplicate-cost scenario the budget exists to
    prevent. Hence 20 s, not the 45 s this module used to declare.
    """
    assert llm_module._WORKER_LEASE_S == 30.0
    assert llm_module._TOTAL_DEADLINE_S < llm_module._WORKER_LEASE_S


def test_gate3_no_request_is_issued_when_the_budget_is_already_gone(monkeypatch):
    monkeypatch.setattr(llm_module, "_TOTAL_DEADLINE_S", 0.0)
    clock = _FakeClock()
    client = _timeout_client(clock)
    outcome = _run_with_clock(monkeypatch, clock, client)
    assert client.requests == []
    assert outcome.notes == ("llm:deadline-exceeded",)
    assert outcome.refused_reason == "llm:deadline-exceeded"


def test_gate3_a_response_arriving_after_the_deadline_is_refused(monkeypatch):
    """A late success is as unusable as a timeout: the worker's lease is gone."""
    clock = _FakeClock()
    client = _slow_success_client(clock, _schedule_payload(), seconds=50.0)
    outcome = _run_with_clock(monkeypatch, clock, client)
    assert len(client.requests) == 1  # the deadline is never retried
    assert outcome.notes == ("llm:deadline-exceeded",)
    assert outcome.refused_reason == "llm:deadline-exceeded"
    assert outcome.proposal.assignment.value == "needs_review"


def test_gate3_a_response_inside_the_deadline_is_still_accepted(monkeypatch):
    clock = _FakeClock()
    client = _slow_success_client(clock, _schedule_payload(), seconds=1.0)
    outcome = _run_with_clock(monkeypatch, clock, client)
    assert outcome.notes == ("llm:matched",)
    assert outcome.refused_reason is None


# ---------------------------------------------------------------------------
# Gate 4 — date interpretation needs a real time basis
# ---------------------------------------------------------------------------


def test_gate4_schedule_without_a_time_basis_is_refused(monkeypatch):
    outcome, _ = _run(monkeypatch, _schedule_payload(), _request())
    assert outcome.notes == ("llm:time-basis-missing",)
    assert outcome.refused_reason == "llm:time-basis-missing:schedule"
    assert outcome.proposal.assignment.value == "needs_review"


def test_gate4_instant_deadline_without_a_time_basis_is_refused(monkeypatch):
    """``kind: instant`` ("明天交稿") is a date too, so it needs the same basis."""
    outcome, _ = _run(monkeypatch, _instant_payload(), _request())
    assert outcome.notes == ("llm:time-basis-missing",)
    assert outcome.refused_reason == "llm:time-basis-missing:schedule"
    assert outcome.proposal.assignment.value == "needs_review"


def test_gate4_instant_deadline_with_a_time_basis_is_accepted(monkeypatch):
    outcome, _ = _run(monkeypatch, _instant_payload(), _grounded_request())
    assert outcome.notes == ("llm:matched",)
    assert outcome.refused_reason is None


@pytest.mark.parametrize("value", ["明天下午三点", "2026-10-18", 7, True])
def test_gate4_scalar_date_value_without_a_basis_is_refused(monkeypatch, value):
    """Review round 2: a date-bearing field is guarded by field, not by shape.

    ``FieldValue`` also admits free text and numbers, so a model that wrote
    "明天下午三点" into a ``deadline`` produced a date the customer never
    stated — and the kind-based check let it through as ``matched``.
    """
    payload = _schedule_payload()
    payload["changes"] = [
        {
            "field": "deadline",
            "old_value": None,
            "new_value": value,
            "field_status": "proposed",
            "customer_confirmation": "pending",
            "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
            "reason": "Customer promised to deliver tomorrow.",
        }
    ]
    outcome, _ = _run(monkeypatch, payload, _request())
    assert outcome.notes == ("llm:time-basis-missing",)
    assert outcome.refused_reason == "llm:time-basis-missing:schedule"
    assert outcome.proposal.assignment.value == "needs_review"


def test_gate4_a_missing_date_value_without_a_basis_is_allowed(monkeypatch):
    """ "The customer has not said yet" states no date, so it needs no basis."""
    payload = _schedule_payload()
    payload["changes"] = [
        {
            "field": "deadline",
            "old_value": None,
            "new_value": None,
            "field_status": "missing",
            "customer_confirmation": "pending",
            "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
            "reason": "No deadline was mentioned.",
        }
    ]
    outcome, _ = _run(monkeypatch, payload, _request())
    assert outcome.notes == ("llm:matched",)


@pytest.mark.parametrize("received", ["not-a-date", "2026-10-07T00:00:00"])
def test_gate4_unusable_received_at_is_refused(monkeypatch, received):
    """A basis that cannot be parsed (or carries no zone) is not a basis."""
    outcome, _ = _run(
        monkeypatch,
        _schedule_payload(),
        _request(message_received_at=received, workspace_timezone=TIMEZONE),
    )
    assert outcome.notes == ("llm:time-basis-missing",)
    assert outcome.refused_reason == "llm:time-basis-invalid:received-at"


def test_gate4_relative_date_is_resolved_against_the_attached_basis(monkeypatch):
    """Real relative-date regression: 下星期四 is only 2026-10-15 given this basis.

    RECEIVED_AT is 2026-10-07 (a Wednesday) in Asia/Hong_Kong, so "next
    Thursday 15:00" resolves to 2026-10-15T07:00:00Z. The provider cannot
    check the arithmetic, but it must hand the model that basis and refuse the
    same answer when the basis is absent.
    """
    payload = _instant_payload()
    payload["changes"][0]["new_value"] = {
        "kind": "instant",
        "at": "2026-10-15T07:00:00Z",
        "timezone": TIMEZONE,
    }
    outcome, client = _run(monkeypatch, payload, _grounded_request())
    assert outcome.notes == ("llm:matched",)
    sent = json.loads(client.requests[0]["json"]["messages"][1]["content"])
    assert sent["time_basis"] == {"received_at": RECEIVED_AT, "timezone": TIMEZONE}
    assert sent["relative_dates_allowed"] is True
    # The same answer without a basis is refused instead of guessed.
    ungrounded, _ = _run(monkeypatch, payload, _request())
    assert ungrounded.refused_reason == "llm:time-basis-missing:schedule"


def test_gate4_invalid_timezone_is_refused(monkeypatch):
    outcome, _ = _run(
        monkeypatch,
        _schedule_payload(),
        _request(message_received_at=RECEIVED_AT, workspace_timezone="Mars/Olympus"),
    )
    assert outcome.notes == ("llm:time-basis-missing",)
    assert outcome.refused_reason == "llm:time-basis-invalid:timezone"


def test_gate4_schedule_with_a_time_basis_is_accepted(monkeypatch):
    outcome, client = _run(monkeypatch, _schedule_payload(), _grounded_request())
    assert outcome.notes == ("llm:matched",)
    sent = json.loads(client.requests[0]["json"]["messages"][1]["content"])
    assert sent["time_basis"]["received_at"] == RECEIVED_AT
    assert sent["time_basis"]["timezone"] == TIMEZONE
    assert sent["relative_dates_allowed"] is True


def test_gate4_missing_basis_still_allows_non_date_changes(monkeypatch):
    """The guard is scoped to date-bearing fields; an address stays usable."""
    outcome, client = _run(monkeypatch, _address_payload(), _request())
    assert outcome.notes == ("llm:matched",)
    sent = json.loads(client.requests[0]["json"]["messages"][1]["content"])
    assert sent["time_basis"] is None
    assert sent["relative_dates_allowed"] is False


def test_workspace_timezone_helper_validates_operator_config(monkeypatch):
    monkeypatch.delenv("GIGMATE_WORKSPACE_TIMEZONE", raising=False)
    assert _workspace_timezone() is None
    monkeypatch.setenv("GIGMATE_WORKSPACE_TIMEZONE", "  ")
    assert _workspace_timezone() is None
    monkeypatch.setenv("GIGMATE_WORKSPACE_TIMEZONE", "Mars/Olympus")
    assert _workspace_timezone() is None
    monkeypatch.setenv("GIGMATE_WORKSPACE_TIMEZONE", "Asia/Hong_Kong")
    assert _workspace_timezone() == "Asia/Hong_Kong"


# ---------------------------------------------------------------------------
# Gate 3 (worker half) — a result for a stale snapshot is discarded
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_factory(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "gates.db").as_posix())
    try:
        Base.metadata.create_all(engine)
        yield sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()


def _stub_provider(on_propose=None):
    def _proposal():
        return ChangeProposal.model_validate(
            {
                "schema_version": "0.1.0",
                "proposal_id": str(uuid4()),
                "conversation_id": CONVERSATION_ID,
                "work_order_id": None,
                "base_work_order_version": None,
                "base_context_version": 5,
                "assignment": "needs_review",
                "candidates": [],
                "changes": [],
                "unresolved_questions": ["stub"],
                "draft_text": None,
                "model_version": "stub:1",
                "prompt_version": "1.1.0",
            }
        )

    class _Stub:
        name = "stub"
        model_version = "stub:1"
        prompt_version = "1.1.0"

        def propose(self, request):
            if on_propose is not None:
                on_propose()
            return ExtractionOutcome(
                provider_name="stub",
                proposal=_proposal(),
                latency_ms=1,
                notes=("stub",),
            )

    return _Stub()


def _seed(memory_factory):
    db = memory_factory()
    db.add(Account(id=ACCOUNT_ID, username="gate3b", password_hash="x", active=True))
    db.add(
        ConversationRow(
            id=CONVERSATION_ID, account_id=ACCOUNT_ID, context_version=5, allowlisted=True
        )
    )
    db.add(
        WorkOrderRow(
            id=CANDIDATE,
            account_id=ACCOUNT_ID,
            data={"id": CANDIDATE, "version": 3, "pending_change_ids": []},
        )
    )
    db.add(ConversationOrder(conversation_id=CONVERSATION_ID, work_order_id=CANDIDATE))
    receipt = Inbox(
        id=str(uuid4()),
        account_id=ACCOUNT_ID,
        payload={},
        digest="d",
        received_at=datetime.now(UTC),
        context_version=5,
    )
    db.add(receipt)
    db.flush()
    return db, receipt


def _event(receipt):
    return {
        "occurred_at": RECEIVED_AT,
        "message_revision": 1,
        "payload": {"message_id": MESSAGE_ID, "text": "改下星期四下午三点"},
    }


def test_worker_persists_evidence_when_snapshot_is_current(memory_factory):
    db, receipt = _seed(memory_factory)
    _reset_provider_for_testing(_stub_provider())
    try:
        matched = _route_through_provider(
            db,
            account=db.get(Account, ACCOUNT_ID),
            inbox=receipt,
            event=_event(receipt),
            conversation=db.get(ConversationRow, CONVERSATION_ID),
            linked=[CANDIDATE],
        )
    finally:
        _reset_provider_for_testing(None)
    assert matched is False
    assert db.scalar(select(Proposal).limit(1)) is not None


def test_worker_discards_result_when_context_advanced_during_the_call(memory_factory):
    db, receipt = _seed(memory_factory)
    conversation = db.get(ConversationRow, CONVERSATION_ID)

    def advance():
        conversation.context_version = 6
        db.flush()

    _reset_provider_for_testing(_stub_provider(on_propose=advance))
    try:
        matched = _route_through_provider(
            db,
            account=db.get(Account, ACCOUNT_ID),
            inbox=receipt,
            event=_event(receipt),
            conversation=conversation,
            linked=[CANDIDATE],
        )
    finally:
        _reset_provider_for_testing(None)
    assert matched is False
    # The stale result must not be promoted: no proposal/trace evidence is
    # written for a snapshot that is no longer current.
    assert db.scalar(select(Proposal).limit(1)) is None


# ---------------------------------------------------------------------------
# Gate 5 — stable, sanitised error codes
# ---------------------------------------------------------------------------


def test_gate5_failure_reasons_carry_no_endpoint_or_credential(monkeypatch):
    outcome, _ = _run_with_status(monkeypatch, 500)
    assert outcome.refused_reason == "llm:http-failed:status-5xx"
    assert "fake.example.test" not in outcome.refused_reason
    assert "sk-fake-test" not in outcome.refused_reason


def test_gate5_schema_failure_reports_the_field_path_only(monkeypatch):
    payload = _schedule_payload()
    payload["changes"][0]["field_status"] = "confirmed"
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.notes == ("llm:response-schema-failed",)
    assert outcome.refused_reason.startswith("llm:response-schema-failed:")
    assert "改下星期四" not in outcome.refused_reason


def test_gate5_prompt_load_failure_is_a_stable_code(monkeypatch, tmp_path):
    _configure(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROMPT_PATH", str(tmp_path / "missing.txt"))
    # A malformed prompt short-circuits before the vendor call with the
    # auditable prompt-malformed outcome; no path text leaks into the note.
    provider = _gate_open_provider(_boom_client())
    outcome = provider.propose(_grounded_request())
    assert outcome.notes == ("llm:prompt-malformed",)
    assert "missing.txt" not in outcome.notes[0]
