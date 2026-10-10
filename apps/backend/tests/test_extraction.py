"""Role B extraction subsystem tests.

Covers provider semantics, contract validation, persistence, evaluation harness
and worker integration. Mirrors the patterns in
``tests/test_workflow.py`` (synthetic fixtures + monkey-patched registry).
"""

from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

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
    ):
        monkeypatch.delenv(name, raising=False)


def test_llm_provider_returns_needs_review_without_configuration(monkeypatch):
    """The skeleton never emits a proposal until the real-model batch is wired in.

    The class flag ``_SKELETON_SEAM`` is the first gate: with no env vars
    the provider still records the not-yet-live state and refuses before
    reading configuration. The trace therefore never claims a real call was
    attempted.
    """
    _clear_llm_env(monkeypatch)
    req = _build_reschedule_request(text="今天天气不错")
    outcome = LLMProvider().propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    assert outcome.refused_reason and "_SKELETON_SEAM" in outcome.refused_reason
    assert outcome.proposal.model_version == "skeleton:pending"
    # Prompt version is read from the bundled file by default.
    assert outcome.proposal.prompt_version == "1.0.0"
    assert outcome.notes == ("llm:seam-pending",)


def test_llm_provider_refuses_live_origin_even_with_configuration(monkeypatch):
    """Live-origin input must never reach matched under the skeleton.

    The skeleton flag fires before the live-origin guard, so a misconfigured
    deployment that exports ``GIGMATE_LLM_PROVIDER/GIGMATE_LLM_MODEL`` still
    refuses every call. Once the seam flag is flipped the live-origin guard
    kicks in for ``case-009-llm-live-origin-refused``.
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
    # The skeleton flag is still the first line of defence, so the trace
    # says "skeleton seam" — not "live-origin" — until the next batch flips
    # the flag.
    assert outcome.refused_reason and "_SKELETON_SEAM" in outcome.refused_reason
    assert outcome.proposal.model_version == "openai:gpt-4o-mini"
    assert outcome.notes == ("llm:seam-pending",)


def test_llm_provider_live_gate_returns_seam_pending_without_calling(monkeypatch):
    """The live gate must never silently fall back to a real call.

    With the seam flag still ``True`` the provider records a
    ``needs_review`` outcome with a clear ``llm:seam-pending`` note and an
    explanatory ``refused_reason``; the worker still records the trace row.
    A separate test (``test_llm_provider_off_gate_blocks_at_provider_layer``)
    proves the off-switch also refuses after the seam flag is flipped.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    req = _build_reschedule_request(text="改下星期四下午三点，地址我晚些发")
    outcome = LLMProvider().propose(req)
    assert outcome.proposal.assignment.value == "needs_review"
    assert outcome.proposal.changes == []
    assert outcome.refused_reason and "_SKELETON_SEAM" in outcome.refused_reason
    assert outcome.proposal.model_version == "openai:gpt-4o-mini"
    assert outcome.notes == ("llm:seam-pending",)


def test_llm_provider_reads_prompt_version_from_bundled_file():
    """The first `prompt_version:` line wins; missing or malformed files fall back to the skeleton marker."""
    import importlib

    from gigmate.extraction import llm as llm_module

    importlib.reload(llm_module)
    provider = llm_module.LLMProvider()
    assert provider._read_prompt_version() == "1.0.0"
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


# ---------------------------------------------------------------------------
# Gate semantics — the off-switch must block at the provider layer (P2 review fix)
# ---------------------------------------------------------------------------


def test_llm_provider_off_gate_blocks_at_provider_layer(monkeypatch):
    """Gate off + configured + origin=synthetic must NOT enter _invoke_model.

    Regression for the P2 review finding: the original gate logic returned
    ``None`` from ``_refusal_reason`` when the provider was configured and
    the live gate was off, so a future implementation of ``_invoke_model``
    could have silently routed real content to the network. The
    ``_SKELETON_SEAM`` class flag is the second line of defence that holds
    even after the next batch flips the on-switch open.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-spy-test")

    class _Spy(LLMProvider):
        _SKELETON_SEAM = False  # pretend the next batch already lifted the skeleton
        invocations: list[str] = []

        def _invoke_model(self, request, began, prompt_version, model_version):
            type(self).invocations.append(request.message_text or "")
            raise AssertionError("_invoke_model must not be reached while the gate is off")

    try:
        provider = _Spy()
        req = _build_reschedule_request(text="改下星期四下午三点，地址我晚些发")
        outcome = provider.propose(req)
        assert outcome.proposal.assignment.value == "needs_review"
        assert outcome.notes == ("llm:seam-pending",)
        assert outcome.refused_reason and "GIGMATE_LLM_LIVE=1 is required" in outcome.refused_reason
        assert _Spy.invocations == []
    finally:
        _Spy._SKELETON_SEAM = True
        _Spy.invocations = []


def test_llm_provider_on_gate_blocks_at_provider_layer_when_seam_unimplemented(monkeypatch):
    """Gate on + configured must NOT enter _invoke_model while the skeleton flag is still True.

    Regression for the P2 review finding: the original gate logic returned
    ``None`` from ``_refusal_reason`` when the live gate was on and the
    configuration was complete, so a misconfigured deployment could have
    entered the network call path. The skeleton flag refuses at the
    provider layer so the next batch must flip BOTH the flag and the seam.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-spy-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")

    class _Spy(LLMProvider):
        invocations: list[str] = []

        def _invoke_model(self, request, began, prompt_version, model_version):
            type(self).invocations.append(request.message_text or "")
            raise AssertionError(
                "_invoke_model must not be reached while the seam is unimplemented"
            )

    try:
        provider = _Spy()
        assert provider._SKELETON_SEAM is True
        req = _build_reschedule_request(text="改下星期四下午三点，地址我晚些发")
        outcome = provider.propose(req)
        assert outcome.proposal.assignment.value == "needs_review"
        assert outcome.notes == ("llm:seam-pending",)
        assert outcome.refused_reason and "_SKELETON_SEAM" in outcome.refused_reason
        assert _Spy.invocations == []
    finally:
        _Spy.invocations = []


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
        _ReachingSpy._SKELETON_SEAM = True
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
    assert proposal_row.prompt_version == "1.0.0"
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
