"""Role B pre-activation batch 3 acceptance suite.

Covers the three B-side follow-ups from issue #29 that can be delivered
without opening the seam, as recorded in ``docs/en/role-b-extraction.md``
under "Batch 3":

* the ``new_work_order`` recognition contract — a structured, source-bound
  *suggestion* for a new work order (never a created order, never a
  confirmation, never alongside a matched change proposal);
* the unknown-vendor-outcome stance for text extraction — one bounded retry
  with the same persistent request id, then a refused proposal with the id
  kept for reconciliation, never a blind resubmit;
* the evaluation surface for the new contract: ``expected_new_work_order``
  plus the classification evidence a run records now.

Every provider test runs against a gate-open subclass of
:class:`LLMProvider`, so ``_SKELETON_SEAM`` stays closed and no network
call, real credential, real vendor or real model is involved.
"""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gigmate.contracts import ChangeProposal, NewWorkOrderSuggestion
from gigmate.db import Base, ModelCallTrace, Proposal
from gigmate.extraction.evaluator import evaluate_case
from gigmate.extraction.llm import _REQUEST_ID_HEADER, LLMProvider
from gigmate.extraction.persistence import persist_changes_for, persist_proposal
from gigmate.extraction.types import ExtractionOutcome, ExtractionRequest
from gigmate.seed import uid

ACCOUNT_ID = uid(1)
CONVERSATION_ID = "00000000-0000-4000-8000-000000000002"
CANDIDATE = "00000000-0000-4000-8000-000000000003"
MESSAGE_ID = "00000000-0000-4000-8000-000000000004"

RECEIVED_AT = "2026-10-07T00:00:00Z"
TIMEZONE = "Asia/Hong_Kong"

_BASE_PROPOSAL = {
    "schema_version": "0.1.0",
    "conversation_id": CONVERSATION_ID,
    "work_order_id": None,
    "base_work_order_version": None,
    "base_context_version": 1,
    "assignment": "needs_review",
    "candidates": [],
    "changes": [],
    "unresolved_questions": [],
    "draft_text": None,
    "model_version": "openai:gpt-4o-mini",
    "prompt_version": "1.2.0",
}


def _env(monkeypatch) -> None:
    for name in (
        "GIGMATE_LLM_PROVIDER",
        "GIGMATE_LLM_MODEL",
        "GIGMATE_LLM_API_KEY",
        "GIGMATE_LLM_ENDPOINT",
        "GIGMATE_LLM_PROMPT_PATH",
        "GIGMATE_LLM_LIVE",
        "GIGMATE_LLM_ALLOW_LIVE_ORIGIN",
        "GIGMATE_WORKSPACE_TIMEZONE",
        "GIGMATE_LLM_COST_BUDGET_USD",
        "GIGMATE_LLM_COST_INPUT_USD_PER_1K",
        "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K",
    ):
        monkeypatch.delenv(name, raising=False)


def _configure(monkeypatch, *, vendor: str = "openai", model: str = "gpt-4o-mini") -> None:
    _env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", vendor)
    monkeypatch.setenv("GIGMATE_LLM_MODEL", model)
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-fake-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", "https://fake.example.test")


def _scripted_client(raw: dict):
    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            # No ``usage`` block: the vendor omits it, which batch 2 records
            # as ``llm:cost-usage-missing`` and never as a cost of zero.
            return {"choices": [{"message": {"content": json.dumps(raw)}}]}

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


def _timeout_client():
    """Client that always times out, so the vendor outcome stays unknown."""

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
            raise httpx.ReadTimeout("synthetic timeout", request=httpx.Request("POST", url))

    return _Client


def _gate_open_provider(client):
    class _GateOpen(LLMProvider):
        _SKELETON_SEAM = False

    provider = _GateOpen()
    provider._client_factory = client
    return provider


def _request(**overrides) -> ExtractionRequest:
    values = {
        "account_id": ACCOUNT_ID,
        "conversation_id": CONVERSATION_ID,
        "message_id": MESSAGE_ID,
        "message_revision": 1,
        "message_text": "你好，我想新约一个上门维修。",
        "context_version": 1,
        "candidate_work_order_ids": (),
        "base_work_order_version": None,
        "base_work_order_snapshot": None,
        "message_received_at": RECEIVED_AT,
        "workspace_timezone": TIMEZONE,
        "origin": "synthetic",
    }
    values.update(overrides)
    return ExtractionRequest(**values)


def _suggestion_payload(**overrides) -> dict:
    """A needs_review response carrying a new-work-order suggestion."""
    payload = {
        **_BASE_PROPOSAL,
        "new_work_order": {
            "summary": "Customer asks for a new on-site repair visit.",
            "fields": [
                {
                    "field": "address",
                    "value": "中环德辅道中 88 号",
                    "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
                    "reason": "Customer stated the address in this message.",
                }
            ],
            "missing_fields": ["schedule"],
            "unresolved_questions": ["Customer has not proposed a time yet."],
            "confidence": 0.8,
        },
    }
    payload.update(overrides)
    return payload


def _validate(payload: dict) -> ChangeProposal:
    return ChangeProposal.model_validate({**payload, "proposal_id": str(uuid4())})


# ---------------------------------------------------------------------------
# Section A - new_work_order recognition contract
# ---------------------------------------------------------------------------


def test_suggestion_is_valid_with_needs_review():
    proposal = _validate(_suggestion_payload())
    assert proposal.assignment.value == "needs_review"
    assert isinstance(proposal.new_work_order, NewWorkOrderSuggestion)
    assert proposal.new_work_order.missing_fields == ["schedule"]


def test_suggestion_is_refused_alongside_matched():
    """A suggestion may never ride a matched change proposal."""
    payload = _suggestion_payload(
        assignment="matched",
        work_order_id=CANDIDATE,
        base_work_order_version=3,
        candidates=[{"work_order_id": CANDIDATE, "confidence": 1.0}],
        changes=[],
    )
    with pytest.raises(ValueError, match="requires needs_review"):
        _validate(payload)


def test_suggestion_is_refused_with_a_target_work_order():
    """A suggestion is for the absence of an order, never for an existing one."""
    with pytest.raises(ValueError, match="cannot target an existing work order"):
        _validate(_suggestion_payload(work_order_id=CANDIDATE))


def test_suggestion_field_may_hold_no_value():
    """Unknown stays missing: a null value is allowed but never invented."""
    payload = _suggestion_payload()
    payload["new_work_order"]["fields"] = [
        {
            "field": "summary",
            "value": None,
            "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
            "reason": "Customer described the job without fixed wording.",
        }
    ]
    proposal = _validate(payload)
    assert proposal.new_work_order is not None
    assert proposal.new_work_order.fields[0].value is None


def test_suggestion_rejects_unknown_keys():
    """A suggestion carries no authority fields; extras are forbidden."""
    payload = _suggestion_payload()
    payload["new_work_order"]["confirmed"] = True
    with pytest.raises(ValueError):
        _validate(payload)


def test_proposals_without_a_suggestion_still_validate():
    """Batch 3 is additive: older responses need no change."""
    proposal = _validate({**_BASE_PROPOSAL, "unresolved_questions": ["No matching order"]})
    assert proposal.new_work_order is None


# ---------------------------------------------------------------------------
# Section B - provider parse path for a suggestion
# ---------------------------------------------------------------------------


def test_suggestion_is_parsed_and_never_becomes_a_change(monkeypatch):
    """A suggestion is recognition output: needs_review, no change rows."""
    _configure(monkeypatch)
    provider = _gate_open_provider(_scripted_client(_suggestion_payload()))
    outcome = provider.propose(_request())
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    suggestion = outcome.proposal.new_work_order
    assert suggestion is not None
    assert suggestion.fields[0].sources[0].message_id == MESSAGE_ID
    assert "llm:needs-review" in outcome.notes


def test_suggestion_is_persisted_without_requirement_changes(monkeypatch, tmp_path):
    """The suggestion rides the proposal JSON; it never creates change rows."""
    _configure(monkeypatch)
    provider = _gate_open_provider(_scripted_client(_suggestion_payload()))
    outcome = provider.propose(_request())
    engine = create_engine(f"sqlite:///{tmp_path / 'batch3.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        row = persist_proposal(
            db,
            account_id=ACCOUNT_ID,
            conversation_id=CONVERSATION_ID,
            event_id=str(uuid4()),
            proposal=outcome.proposal,
            outcome=outcome,
        )
        proposal_row_id = row.id
        change_ids = persist_changes_for(
            db,
            proposal_row=row,
            proposal=outcome.proposal,
            account_id=ACCOUNT_ID,
            conversation_id=CONVERSATION_ID,
            work_order_id=CANDIDATE,
            base_work_order_version=1,
            work_order_field={},
        )
        db.commit()
    assert change_ids == []
    with factory() as db:
        # The column is a JSON type: SQLAlchemy returns the decoded object.
        stored = db.scalar(select(Proposal.proposal).where(Proposal.id == proposal_row_id))
    assert stored["new_work_order"]["summary"].startswith("Customer asks")
    assert stored["changes"] == []


# ---------------------------------------------------------------------------
# Section C - unknown vendor outcome (no blind resend)
# ---------------------------------------------------------------------------


def test_unknown_outcome_retries_once_with_the_same_id_then_refuses(monkeypatch):
    """A timed-out call is unknown, not failed-and-forgotten: one bounded retry.

    Both attempts carry the same persistent request id so the vendor's own
    log can be correlated afterwards, and the run stops after the budget is
    spent instead of resubmitting until something answers.
    """
    _configure(monkeypatch)
    client = _timeout_client()
    provider = _gate_open_provider(client)
    outcome = provider.propose(_request())
    assert len(client.requests) == 2  # one initial attempt + one bounded retry
    sent_ids = {call["headers"][_REQUEST_ID_HEADER] for call in client.requests}
    assert len(sent_ids) == 1
    assert outcome.request_id in sent_ids
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    assert outcome.refused_reason == "llm:http-failed:timeout"
    assert "llm:http-failed" in outcome.notes


def test_unknown_outcome_keeps_the_request_id_for_reconciliation(monkeypatch, tmp_path):
    """The trace row keeps the id, so an operator can reconcile, not resend."""
    _configure(monkeypatch)
    provider = _gate_open_provider(_timeout_client())
    outcome = provider.propose(_request())
    engine = create_engine(f"sqlite:///{tmp_path / 'batch3-unknown.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        persist_proposal(
            db,
            account_id=ACCOUNT_ID,
            conversation_id=CONVERSATION_ID,
            event_id=str(uuid4()),
            proposal=outcome.proposal,
            outcome=outcome,
        )
        db.commit()
    with factory() as db:
        trace = db.scalar(select(ModelCallTrace))
    assert trace.request_id == outcome.request_id
    assert trace.refused_reason == "llm:http-failed:timeout"


# ---------------------------------------------------------------------------
# Section D - evaluation surface for the new contract
# ---------------------------------------------------------------------------


class _StubProvider:
    """Minimal provider that returns a scripted outcome for one case."""

    name = "stub:suggestion"
    model_version = "stub:1"
    prompt_version = "1.2.0"

    def __init__(self, proposal: ChangeProposal, *, refused_reason: str | None = None):
        self._proposal = proposal
        self._refused_reason = refused_reason

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome:
        return ExtractionOutcome(
            provider_name=self.name,
            proposal=self._proposal,
            latency_ms=1,
            notes=("stub",),
            refused_reason=self._refused_reason,
        )


def _case(**overrides) -> dict:
    payload = {
        "case_id": "case-b3-001-suggestion",
        "scenario": "needs_review: new job request with no matching work order",
        "data_classification": "synthetic",
        "input_event": {
            "account_id": ACCOUNT_ID,
            "conversation_id": CONVERSATION_ID,
            "message_id": MESSAGE_ID,
            "message_revision": 1,
            "text": "你好，我想新约一个上门维修。",
            "context_version": 1,
            "candidate_work_order_ids": [],
        },
        "expected_assignment": "needs_review",
    }
    payload.update(overrides)
    return payload


def test_evaluator_accepts_a_suggestion_when_expected():
    proposal = _validate(_suggestion_payload())
    outcome = evaluate_case(_StubProvider(proposal), _case(expected_new_work_order=True))
    assert outcome.status == "pass"
    assert outcome.actual_new_work_order is True
    assert outcome.expected_new_work_order is True


def test_evaluator_flags_a_missing_suggestion():
    proposal = _validate({**_BASE_PROPOSAL, "unresolved_questions": ["No matching order"]})
    outcome = evaluate_case(_StubProvider(proposal), _case(expected_new_work_order=True))
    assert outcome.status == "fail"
    assert "expected True" in (outcome.message or "")


def test_evaluator_flags_an_unexpected_suggestion():
    proposal = _validate(_suggestion_payload())
    outcome = evaluate_case(_StubProvider(proposal), _case(expected_new_work_order=False))
    assert outcome.status == "fail"
    assert "expected False" in (outcome.message or "")


def test_evaluator_records_the_refusal_reason():
    proposal = _validate({**_BASE_PROPOSAL, "unresolved_questions": ["Vendor call failed"]})
    outcome = evaluate_case(
        _StubProvider(proposal, refused_reason="llm:http-failed:timeout"),
        _case(),
    )
    assert outcome.status == "pass"
    assert outcome.refused_reason == "llm:http-failed:timeout"
    assert outcome.notes == ["stub"]
