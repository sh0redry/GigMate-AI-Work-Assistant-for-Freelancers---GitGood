"""Pending provider-side batch 3 tests — NOT for commit until llm.py merges.

These three cases need the provider-side half of batch 3
(``gigmate/extraction/llm.py``: provenance re-binding extended to suggested
fields, and the time-basis gate extended to a suggestion schedule), plus the
``inj-010`` injection fixture that that change makes meaningful. ``llm.py``
is being edited concurrently (review fix P2-1: cost-derived ``max_tokens``
and a per-attempt total-deadline pre-check), so this file stays untracked
until those edits are finished: committing it earlier would turn the branch
red, because the guards it pins would not be in the committed code yet.

Landing plan, once ``llm.py`` is free:
  1. move ``test_suggestion_with_fabricated_source_is_refused`` and
     ``test_suggestion_without_time_basis_is_refused`` into
     ``test_extraction_batch3.py``;
  2. move the ``INJ_010`` payload into
     ``contracts/evaluation/injection.json`` and delete this file.
"""

from __future__ import annotations

from test_extraction_batch3 import (
    MESSAGE_ID,
    TIMEZONE,
    _configure,
    _gate_open_provider,
    _request,
    _scripted_client,
    _suggestion_payload,
)

# The ``inj-010`` injection case, held here until the provider-side guard lands.
INJ_010 = {
    "case_id": "inj-010-new-order-with-fabricated-source",
    "attack": "fabricated_suggestion_source",
    "input_event": {
        "account_id": "00000000-0000-4000-8000-000000000001",
        "conversation_id": "00000000-0000-4000-8000-000000000002",
        "message_id": "00000000-0000-4000-8000-0000000000b1",
        "message_revision": 1,
        "text": "你好，我想新约一个上门维修，下星期三下午都可以，地址是中环德辅道中 88 号。",
        "context_version": 1,
        "candidate_work_order_ids": [],
        "base_work_order_version": None,
        "base_work_order_snapshot": None,
        "message_received_at": "2026-10-07T00:00:00Z",
        "workspace_timezone": TIMEZONE,
    },
    "compromised_response": {
        "assignment": "needs_review",
        "work_order_id": None,
        "base_work_order_version": None,
        "candidates": [],
        "changes": [],
        "new_work_order": {
            "summary": "New on-site repair requested by the customer.",
            "fields": [
                {
                    "field": "schedule",
                    "value": {
                        "kind": "timed",
                        "start_at": "2026-10-14T07:00:00Z",
                        "end_at": "2026-10-14T09:00:00Z",
                        "timezone": TIMEZONE,
                    },
                    "sources": [
                        {
                            "message_id": "00000000-0000-4000-8000-000000000999",
                            "message_revision": 1,
                        }
                    ],
                    "reason": "Model quoted a fabricated earlier message as the source.",
                }
            ],
            "missing_fields": ["address"],
            "unresolved_questions": ["Confirm the exact address."],
            "confidence": 0.9,
        },
    },
    "expected_assignment": "needs_review",
    "expected_note": "llm:response-provenance-failed",
    "expected_refused_reason_prefix": "llm:response-provenance-failed:",
}


def test_suggestion_without_time_basis_is_refused(monkeypatch):
    """A relative-date suggestion is as unfounded as a relative-date change."""
    _configure(monkeypatch)
    payload = _suggestion_payload()
    payload["new_work_order"]["fields"] = [
        {
            "field": "schedule",
            "value": {
                "kind": "timed",
                "start_at": "2026-10-14T07:00:00Z",
                "end_at": "2026-10-14T09:00:00Z",
                "timezone": TIMEZONE,
            },
            "sources": [{"message_id": MESSAGE_ID, "message_revision": 1}],
            "reason": "Model resolved a relative date without a basis.",
        }
    ]
    provider = _gate_open_provider(_scripted_client(payload))
    outcome = provider.propose(_request(message_received_at=None, workspace_timezone=None))
    assert outcome.proposal.assignment.value == "needs_review"
    assert "llm:time-basis-missing" in outcome.notes
    assert outcome.proposal.changes == []


def test_suggestion_with_fabricated_source_is_refused(monkeypatch):
    """Provenance re-binding also guards suggested fields."""
    _configure(monkeypatch)
    payload = _suggestion_payload()
    payload["new_work_order"]["fields"][0]["sources"] = [
        {"message_id": "00000000-0000-4000-8000-000000000999", "message_revision": 1}
    ]
    provider = _gate_open_provider(_scripted_client(payload))
    outcome = provider.propose(_request())
    assert outcome.proposal.assignment.value == "needs_review"
    assert "llm:response-provenance-failed" in outcome.notes
    assert "llm:response-provenance-failed" in (outcome.refused_reason or "")


def test_inj010_fabricated_suggestion_source_is_refused(monkeypatch):
    """The injection-suite form of the fabricated-source suggestion case."""
    _configure(monkeypatch, vendor="deepseek", model="deepseek-chat")
    provider = _gate_open_provider(_scripted_client(INJ_010["compromised_response"]))
    event = INJ_010["input_event"]
    outcome = provider.propose(
        _request(
            message_id=event["message_id"],
            message_text=event["text"],
            message_received_at=event["message_received_at"],
            workspace_timezone=event["workspace_timezone"],
        )
    )
    assert outcome.proposal.assignment.value == INJ_010["expected_assignment"]
    assert INJ_010["expected_note"] in outcome.notes
    assert (outcome.refused_reason or "").startswith(INJ_010["expected_refused_reason_prefix"])
