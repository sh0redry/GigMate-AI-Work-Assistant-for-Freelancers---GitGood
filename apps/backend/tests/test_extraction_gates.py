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
def test_gate1_sources_must_reference_the_issued_message(monkeypatch, sources):
    payload = _schedule_payload()
    payload["changes"][0]["sources"] = sources
    outcome, _ = _run(monkeypatch, payload, _grounded_request())
    assert outcome.notes == ("llm:response-provenance-failed",)
    assert outcome.refused_reason.startswith("llm:response-provenance-failed:source-")


def test_gate1_correctly_bound_response_still_matches(monkeypatch):
    outcome, _ = _run(monkeypatch, _schedule_payload(), _grounded_request())
    assert outcome.notes == ("llm:matched",)
    assert outcome.proposal.assignment.value == "matched"
    assert outcome.proposal.work_order_id == CANDIDATE
    assert outcome.refused_reason is None


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


def test_gate3_exhausted_time_budget_stops_retrying(monkeypatch):
    monkeypatch.setattr(llm_module, "_TOTAL_DEADLINE_S", 0.0)
    _, client = _run_with_status(monkeypatch, 500)
    assert len(client.requests) == 1


# ---------------------------------------------------------------------------
# Gate 4 — date interpretation needs a real time basis
# ---------------------------------------------------------------------------


def test_gate4_schedule_without_a_time_basis_is_refused(monkeypatch):
    outcome, _ = _run(monkeypatch, _schedule_payload(), _request())
    assert outcome.notes == ("llm:time-basis-missing",)
    assert outcome.refused_reason == "llm:time-basis-missing:schedule"
    assert outcome.proposal.assignment.value == "needs_review"


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
