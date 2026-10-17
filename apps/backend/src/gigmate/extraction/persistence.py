"""Persist provider proposals and trace evidence durably.

The worker calls :func:`persist_proposal` once per AI call inside the same
transaction as the job outcome. The function is the single seam that turns an
``ExtractionOutcome`` into rows in ``proposals``, ``model_call_traces`` and
optional ``requirement_changes``. All rows are append-only.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Iterable
from uuid import uuid4

from sqlalchemy.orm import Session as SessionFactory

from gigmate.contracts import (
    ChangeProposal,
    DateOnly,
    FieldStatus,
    RequirementChange,
    TimedSchedule,
)
from gigmate.db import ChangeRow, ModelCallTrace, Proposal

from .types import ExtractionOutcome


def review_schedule_shapes(outcome: ExtractionOutcome) -> ExtractionOutcome:
    """Preserve partial time evidence without treating it as a calendar interval.

    FieldValue intentionally also admits scalar values. A model can therefore
    return a valid proposal containing only a start timestamp. Do not invent an
    end time, lose unrelated address changes, or let draft generation crash.
    """
    changes = []
    incomplete = False
    for change in outcome.proposal.changes:
        if (
            change.field == "schedule"
            and change.field_status == "proposed"
            and not isinstance(change.new_value, (TimedSchedule, DateOnly))
        ):
            change = change.model_copy(update={"field_status": FieldStatus.needs_review})
            incomplete = True
        changes.append(change)
    if not incomplete:
        return outcome
    question = "请核对时间并补充结束时间或时长；不完整的时间不能加入日历。"
    questions = list(outcome.proposal.unresolved_questions)
    if question not in questions:
        questions.append(question)
    return replace(
        outcome,
        proposal=outcome.proposal.model_copy(
            update={"changes": changes, "unresolved_questions": questions}
        ),
        notes=(*outcome.notes, "schedule:incomplete-value"),
    )


def persist_proposal(
    db: SessionFactory,
    *,
    account_id: str,
    conversation_id: str,
    event_id: str,
    proposal: ChangeProposal,
    outcome: ExtractionOutcome,
) -> Proposal:
    """Persist one ``Proposal`` row plus its ``ModelCallTrace``.

    The function never raises; the caller controls transaction boundaries.
    """
    now = datetime.now(UTC)
    serialized = json.loads(proposal.model_dump_json())
    proposal_row = Proposal(
        id=str(uuid4()),
        account_id=account_id,
        conversation_id=conversation_id,
        event_id=event_id,
        work_order_id=proposal.work_order_id,
        assignment=proposal.assignment.value,
        context_version=proposal.base_context_version,
        base_work_order_version=proposal.base_work_order_version,
        proposal=serialized,
        changes=serialized.get("changes", []),
        unresolved_questions=serialized.get("unresolved_questions", []),
        model_version=proposal.model_version,
        prompt_version=proposal.prompt_version,
        draft_text=proposal.draft_text,
        created_at=now,
    )
    db.add(proposal_row)
    db.flush()
    db.add(
        ModelCallTrace(
            id=str(uuid4()),
            proposal_id=proposal_row.id,
            account_id=account_id,
            provider_name=outcome.provider_name,
            model_version=proposal.model_version,
            prompt_version=proposal.prompt_version,
            latency_ms=outcome.latency_ms,
            refused_reason=outcome.refused_reason,
            notes=list(outcome.notes),
            request_id=outcome.request_id,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            cost_usd=outcome.cost_usd,
            created_at=now,
        )
    )
    return proposal_row


def persist_changes_for(
    db: SessionFactory,
    *,
    proposal_row: Proposal,
    proposal: ChangeProposal,
    account_id: str,
    conversation_id: str,
    work_order_id: str,
    base_work_order_version: int,
    work_order_field: dict,
) -> list[str]:
    """Materialize each proposed change as a ``RequirementChange`` ``ChangeRow``.

    Returns the list of inserted change IDs. Caller is responsible for appending
    them to the work order's ``pending_change_ids``. Each row's
    ``context_version`` matches the proposal so that
    ``messaging.ingest``'s demotion rule keeps history coherent.
    """
    if proposal.assignment.value != "matched":
        return []
    change_ids: list[str] = []
    for change in proposal.changes:
        change_id = str(uuid4())
        # Construct the model directly instead of round-tripping through
        # json.dumps: change.field is a plain Literal string (no .value) and
        # old_value/new_value may hold Pydantic models (TimedSchedule etc.)
        # that json.dumps cannot serialize. model_dump(mode="json") is the
        # canonical JSON-safe serialization.
        validated = RequirementChange(
            id=change_id,
            account_id=account_id,
            work_order_id=work_order_id,
            field=change.field,
            old_value=change.old_value,
            new_value=change.new_value,
            status=change.field_status,
            customer_confirmation=change.customer_confirmation,
            proposer="customer",
            sources=list(change.sources),
            base_work_order_version=base_work_order_version,
        )
        payload = validated.model_dump(mode="json")
        db.add(
            ChangeRow(
                id=change_id,
                account_id=account_id,
                work_order_id=work_order_id,
                conversation_id=conversation_id,
                context_version=proposal.base_context_version,
                data=payload,
            )
        )
        change_ids.append(change_id)
    # work_order_field is intentionally unused here: requirement_changes.c.data
    # already pins the immutable snapshot. Kept on the signature to make caller
    # contract obvious in code review without re-deriving it from row.data.
    del work_order_field
    return change_ids


def candidate_change_fields(proposal: ChangeProposal) -> Iterable[str]:
    return [str(change.field) for change in proposal.changes]


__all__ = ["persist_proposal", "persist_changes_for", "candidate_change_fields"]
