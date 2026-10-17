"""Bounded agent drafts: follow-up and polish text a merchant can review.

Issue #29 asks for "wider agent suggestion drafts / polishing" **and** for the
constrained rules that come with it. This module is deliberately the narrow
shape of that idea:

* No free-form question answering. A draft is only ever created from text the
  extraction seam already produced under its own gates (budget, provenance,
  time basis) or from the merchant's own input. There is no "ask the model
  anything" path.
* No execution authority. A draft is text. It is never sent, never confirms a
  field and never creates or changes a work order; sending still goes through
  the existing approval path.
* Bounded by construction: a daily ceiling, a TTL, revocation, quiet hours and
  one-time consumption. A draft that outlived its bindings reads as ``expired``
  or is revoked instead of being silently reused.

The rules are configuration-driven and default to permissive-but-recorded
values, so a deployment that never tunes them still cannot create an unbounded
number of drafts.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from gigmate.contracts import AgentDraftCommand
from gigmate.db import (
    AgentDraftRow,
    ConversationOrder,
    ConversationRow,
    Proposal,
    WorkOrderRow,
)
from gigmate.errors import BusinessError

_DAILY_LIMIT_ENV = "GIGMATE_AGENT_DRAFT_DAILY_LIMIT"
_TTL_MINUTES_ENV = "GIGMATE_AGENT_DRAFT_TTL_MINUTES"
_QUIET_HOURS_ENV = "GIGMATE_AGENT_QUIET_HOURS"

DEFAULT_DAILY_LIMIT = 20
DEFAULT_TTL_MINUTES = 1440


def _limit() -> int:
    raw = os.environ.get(_DAILY_LIMIT_ENV, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_DAILY_LIMIT
    return value if value > 0 else DEFAULT_DAILY_LIMIT


def _ttl() -> timedelta:
    raw = os.environ.get(_TTL_MINUTES_ENV, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return timedelta(minutes=DEFAULT_TTL_MINUTES)
    if value <= 0:
        return timedelta(minutes=DEFAULT_TTL_MINUTES)
    return timedelta(minutes=min(value, 60 * 24 * 7))


def _quiet_now(now: datetime) -> bool:
    """Whether ``now`` falls inside the configured quiet window (UTC hours).

    ``GIGMATE_AGENT_QUIET_HOURS`` is ``"start-end"`` in UTC hours, e.g.
    ``"22-07"`` for 22:00 until 07:00. Unset means no quiet window: the rule is
    opt-in so a deployment without an operator decision is not silently gated.
    """

    raw = os.environ.get(_QUIET_HOURS_ENV, "").strip()
    if not raw or "-" not in raw:
        return False
    try:
        start_text, end_text = raw.split("-", 1)
        start, end = int(start_text), int(end_text)
    except ValueError:
        return False
    hour = now.astimezone(UTC).hour
    return (hour >= start or hour < end) if start > end else (start <= hour < end)


def _owned_order(db, account, order_id: str) -> WorkOrderRow:
    order = db.get(WorkOrderRow, order_id)
    if not order or order.account_id != account.id:
        raise BusinessError(404, "NOT_FOUND", "Work order not found")
    return order


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _effective_status(row: AgentDraftRow, now: datetime) -> str:
    if row.status in {"revoked", "consumed"}:
        return row.status
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return "expired" if expires <= now else row.status


def view(db, row: AgentDraftRow, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    status = _effective_status(row, now)
    return {
        "id": row.id,
        "work_order_id": row.work_order_id,
        "conversation_id": row.conversation_id,
        "kind": row.kind,
        "text": row.text,
        "context_version": row.context_version,
        "base_work_order_version": row.base_work_order_version,
        "proposal_id": row.proposal_id,
        "status": status,
        "expires_at": _iso(row.expires_at),
        "revoked_at": _iso(row.revoked_at),
        "consumed_at": _iso(row.consumed_at),
        "note": row.note,
        "created_at": _iso(row.created_at),
        "execution_authority": False,
    }


def create(db, account, order_id: str, command: AgentDraftCommand) -> dict:
    """Create one draft, bounded by the configured rules."""

    now = datetime.now(UTC)
    order = _owned_order(db, account, order_id)
    link = db.scalar(select(ConversationOrder).where(ConversationOrder.work_order_id == order_id))
    if link is None:
        raise BusinessError(
            409,
            "CONVERSATION_LINK_REQUIRED",
            "This work order is not linked to a conversation",
        )
    conversation = db.get(ConversationRow, link.conversation_id)
    if conversation is None:
        raise BusinessError(404, "NOT_FOUND", "Conversation not found")

    if _quiet_now(now):
        raise BusinessError(
            409,
            "AGENT_QUIET_HOURS",
            "Drafts are not created during the configured quiet hours.",
        )
    created_today = db.scalar(
        select(func.count())
        .select_from(AgentDraftRow)
        .where(
            AgentDraftRow.account_id == account.id,
            AgentDraftRow.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
        )
    )
    if created_today >= _limit():
        raise BusinessError(
            429,
            "AGENT_DRAFT_LIMIT_REACHED",
            "The daily draft ceiling is reached; revoke an unused draft first.",
        )

    text = command.text
    proposal_id = None
    context_version = conversation.context_version
    base_version = order.data.get("version") if order.data else None
    if command.base_proposal_id is not None:
        proposal = db.get(Proposal, command.base_proposal_id)
        if proposal is None or proposal.account_id != account.id:
            raise BusinessError(404, "NOT_FOUND", "Proposal not found")
        if proposal.conversation_id != link.conversation_id:
            raise BusinessError(
                409,
                "AGENT_DRAFT_PROPOSAL_MISMATCH",
                "The proposal belongs to another conversation",
            )
        if proposal.context_version != conversation.context_version:
            raise BusinessError(
                409,
                "AGENT_DRAFT_STALE",
                "The source advanced since this proposal; create a fresh draft.",
            )
        if not (proposal.draft_text or "").strip():
            raise BusinessError(
                409,
                "AGENT_DRAFT_NO_TEXT",
                "This proposal carries no merchant-facing draft text",
            )
        text = proposal.draft_text
        proposal_id = proposal.id
        context_version = proposal.context_version
        base_version = proposal.base_work_order_version
        existing = db.scalar(
            select(AgentDraftRow).where(
                AgentDraftRow.account_id == account.id,
                AgentDraftRow.proposal_id == proposal.id,
            )
        )
        if existing is not None:
            return view(db, existing, now)

    row = AgentDraftRow(
        id=str(uuid4()),
        account_id=account.id,
        work_order_id=order_id,
        conversation_id=link.conversation_id,
        kind=command.kind,
        text=(text or "").strip(),
        context_version=context_version,
        base_work_order_version=base_version,
        proposal_id=proposal_id,
        status="proposed",
        note=command.note,
        expires_at=now + _ttl(),
        created_at=now,
    )
    db.add(row)
    db.flush()
    return view(db, row, now)


def list_for_order(db, account, order_id: str) -> list[AgentDraftRow]:
    _owned_order(db, account, order_id)
    return list(
        db.scalars(
            select(AgentDraftRow)
            .where(
                AgentDraftRow.account_id == account.id,
                AgentDraftRow.work_order_id == order_id,
            )
            .order_by(AgentDraftRow.created_at.desc())
        )
    )


def _draft(db, account, draft_id: str) -> AgentDraftRow:
    row = db.get(AgentDraftRow, draft_id)
    if not row or row.account_id != account.id:
        raise BusinessError(404, "NOT_FOUND", "Draft not found")
    return row


def revoke(db, account, draft_id: str) -> dict:
    row = _draft(db, account, draft_id)
    if row.status == "consumed":
        raise BusinessError(
            409,
            "AGENT_DRAFT_ALREADY_CONSUMED",
            "A consumed draft cannot be revoked retroactively",
        )
    row.status = "revoked"
    row.revoked_at = datetime.now(UTC)
    db.flush()
    return view(db, row)


def consume(db, account, draft_id: str) -> dict:
    """Take the text into the merchant's own approval flow, exactly once.

    Consuming returns the text; it does not send anything. Repeated calls are
    refused so the same draft cannot become two outbound messages.
    """

    now = datetime.now(UTC)
    row = _draft(db, account, draft_id)
    if _effective_status(row, now) != "proposed":
        raise BusinessError(
            409,
            "AGENT_DRAFT_NOT_USABLE",
            f"Draft is {_effective_status(row, now)}; it cannot be consumed",
        )
    row.status = "consumed"
    row.consumed_at = now
    db.flush()
    return view(db, row, now)


__all__ = ["create", "consume", "list_for_order", "revoke", "view"]
