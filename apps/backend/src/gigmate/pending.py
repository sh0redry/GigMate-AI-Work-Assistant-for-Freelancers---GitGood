"""Keep pending AI proposals valid across unrelated customer messages.

Every message advances the conversation's context version, and a proposal can
only be confirmed at the version it was written for. Previously each new
message therefore turned every open proposal into ``needs_review`` — even a
"thanks" made the merchant redo the work.

Now the decision is the AI's, made per message after it has read it:

* the message changes order X's field F → only the open proposal for (X, F)
  is superseded (``needs_review``);
* the message is unrelated to any order (greeting, thanks, sticker) or is a
  different, new job → no open proposal is affected;
* the AI could not tell, failed, or was never asked → nothing can be assumed
  and every open proposal is superseded, exactly as before.

A proposal that survives is moved to the new context version, so it stays
confirmable. Only proposals written for the *immediately preceding* version
can move: if an earlier message was never analysed (superseded before its
job ran), nobody has checked it, so older proposals are superseded.

Edits and revocations are handled at ingest (``on_source_changed``): a
proposal whose own source message changed loses its basis immediately.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select

from gigmate.db import ChangeRow

CLEAN = "clean"
UNKNOWN = "unknown"


def _open(db, conversation):
    return [
        change
        for change in db.scalars(
            select(ChangeRow).where(
                ChangeRow.conversation_id == conversation.id,
                ChangeRow.account_id == conversation.account_id,
            )
        )
        if change.data["status"] == "proposed"
    ]


def reconcile(
    db,
    conversation,
    analyzed_version: int,
    verdict: str,
    touched: Iterable[tuple[str, str]] = (),
    created: Iterable[str] = (),
) -> dict[str, list[str]]:
    """Apply the AI's relevance judgement for the message at ``analyzed_version``.

    ``touched`` lists ``(work_order_id, field)`` pairs the message spoke
    about (including fields the AI tried to change but could not read).
    ``created`` are change ids written for this very message; they are left
    alone. Returns the ids that were carried forward and superseded.
    """
    touched = set(touched)
    created = set(created)
    kept: list[str] = []
    superseded: list[str] = []
    if conversation.context_version != analyzed_version:
        # A newer message arrived meanwhile; its own analysis decides.
        return {"kept": kept, "superseded": superseded}
    for change in _open(db, conversation):
        if change.id in created or change.context_version == analyzed_version:
            continue
        carry = (
            verdict == CLEAN
            and change.context_version == analyzed_version - 1
            and (change.work_order_id, change.data["field"]) not in touched
        )
        if carry:
            change.context_version = analyzed_version
            kept.append(change.id)
        else:
            change.data = {**change.data, "status": "needs_review"}
            superseded.append(change.id)
    db.flush()
    return {"kept": kept, "superseded": superseded}


def on_source_changed(db, conversation, message_id: str, revoked: bool, new_version: int):
    """An existing message was edited or revoked (called at ingest).

    Proposals quoting that message lose their basis now. After a revocation
    no new text needs reading, so the others move forward directly; after an
    edit the worker reads the new text and ``reconcile`` decides.
    """
    for change in _open(db, conversation):
        if any(source["message_id"] == message_id for source in change.data["sources"]):
            change.data = {**change.data, "status": "needs_review"}
    db.flush()
    if revoked:
        reconcile(db, conversation, new_version, CLEAN)


def touched_by(outcome, work_order_id: str | None) -> set[tuple[str, str]]:
    """Order/field pairs an extraction outcome spoke about, read or not."""
    pairs: set[tuple[str, str]] = set()
    if work_order_id is None:
        return pairs
    for change in outcome.proposal.changes:
        pairs.add((work_order_id, change.field))
    for note in outcome.notes:
        if note.startswith("llm:partial-dropped:"):
            pairs.add((work_order_id, note.rsplit(":", 1)[1]))
    return pairs


def verdict_for(outcome) -> str:
    """Whether the AI actually judged this message, and found it harmless.

    ``matched`` (one known order, its fields listed in ``touched_by``), an
    explicit "unrelated to any order", or a clean new-job suggestion count as
    judged. Ambiguity, refusals and failures do not.
    """
    proposal = outcome.proposal
    if proposal.assignment.value == "matched" and outcome.refused_reason is None:
        return CLEAN
    if outcome.refused_reason != "llm:needs-review":
        return UNKNOWN
    if getattr(outcome, "unrelated", False) and not proposal.changes:
        return CLEAN
    if proposal.new_work_order is not None and not proposal.changes:
        return CLEAN
    return UNKNOWN
