"""Role B extraction subsystem tests.

Covers provider semantics, contract validation, persistence, evaluation harness
and worker integration. Mirrors the patterns in
``tests/test_workflow.py`` (synthetic fixtures + monkey-patched registry).
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from gigmate.db import (
    Base,
    ChangeRow,
    EvaluationCaseRecord,
    EvaluationRun,
    Inbox,
    Job,
    ModelCallTrace,
    Proposal,
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
from gigmate.extraction.registry import (
    _reset_provider_for_testing,
    registered_providers,
)
from gigmate.messaging import fixture as load_fixture
from gigmate.messaging import ingest, replay_event
from gigmate.seed import seed as seed_function
from gigmate.seed import uid
from gigmate.worker import EXTRACTION_NEEDS_REVIEW, run_once

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_factory():
    with tempfile.NamedTemporaryFile(suffix=".db") as handle:
        url = f"sqlite:///{handle.name}"
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        yield factory
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
    )


# ---------------------------------------------------------------------------
# Provider contracts
# ---------------------------------------------------------------------------


def test_registered_providers_includes_deterministic_and_disabled():
    assert {"deterministic", "disabled"} <= set(registered_providers())


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
    assert proposal_row.prompt_version == "0.1.0"
    assert trace_row.provider_name == "deterministic"
    assert trace_row.notes == ["deterministic:matched-known-fixture"]


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


def test_evaluation_manifest_persists_per_case_records(memory_account):
    summary = None
    with memory_account.begin() as db:
        summary = evaluate_manifest(db, "contracts/evaluation/manifest.json")
        # Force flush inside the open transaction (we already used begin())
    cases = list(summary.cases)
    assert len(cases) == 6
    with memory_account.begin() as db:
        runs = list(db.scalars(select(EvaluationRun)))
        rows = list(db.scalars(select(EvaluationCaseRecord)))
    assert len(runs) == 1
    assert runs[0].passed >= 5
    assert len(rows) == 6
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


def test_evaluation_run_requires_non_empty_manifest(memory_account):
    empty_path = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
    try:
        with open(empty_path, "w", encoding="utf-8") as handle:
            json.dump({"cases": []}, handle)
        with memory_account.begin() as db:
            with pytest.raises(ValueError, match="no cases"):
                evaluate_manifest(db, empty_path)
    finally:
        os.unlink(empty_path)
