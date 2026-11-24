"""Bounded model context may use only current, owned, consented source revisions."""

from sqlalchemy import select

from gigmate.db import Account, Inbox


def source_allowed(db, conversation, message):
    """A reauthorization does not reopen previously stored text to new model calls."""
    account = db.get(Account, conversation.account_id)
    if (
        not account
        or not account.active
        or not conversation.allowlisted
        or message.account_id != conversation.account_id
        or message.conversation_id != conversation.id
        or message.data.get("revoked")
        or message.data.get("direction") != "incoming"
        or message.data.get("source") != "app"
        or not isinstance(message.data.get("text"), str)
    ):
        return False
    return (
        db.scalar(
            select(Inbox.id)
            .where(
                Inbox.account_id == conversation.account_id,
                Inbox.payload["conversation_id"].as_string() == conversation.id,
                Inbox.payload["payload"]["message_id"].as_string() == message.id,
                Inbox.payload["message_revision"].as_integer() == message.revision,
                Inbox.context_version > (conversation.consent_context_version or 0),
                Inbox.context_version <= conversation.context_version,
            )
            .limit(1)
        )
        is not None
    )


# Same bounds as extraction context (ADR 0011 owner decision O2).
CONTEXT_WINDOW_MINUTES = 5
CONTEXT_MAX_MESSAGES = 8
CONTEXT_MAX_BYTES = 8000


def bounded_incoming(db, conversation, anchor=None, *, scan=40):
    """Current incoming revisions of one conversation allowed into model context.

    Takes the newest allowed message (or ``anchor``) and walks back at most five
    minutes, eight messages and 8000 UTF-8 bytes. Only internal message UUIDs,
    revisions, times and text are returned: no provider IDs or phone numbers.
    """
    import json
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from gigmate.db import MessageRow

    latest = (
        select(MessageRow.id.label("message_id"), func.max(MessageRow.revision).label("revision"))
        .where(
            MessageRow.account_id == conversation.account_id,
            MessageRow.conversation_id == conversation.id,
        )
        .group_by(MessageRow.id)
        .subquery()
    )
    rows = db.scalars(
        select(MessageRow)
        .join(
            latest,
            (MessageRow.id == latest.c.message_id) & (MessageRow.revision == latest.c.revision),
        )
        .where(
            MessageRow.account_id == conversation.account_id,
            MessageRow.conversation_id == conversation.id,
        )
        .order_by(MessageRow.data["occurred_at"].as_string().desc(), MessageRow.id)
        .limit(scan)
    )
    allowed = []
    for row in rows:
        text = row.data.get("text")
        if (
            not isinstance(text, str)
            or not text.strip()
            or not source_allowed(db, conversation, row)
        ):
            continue
        try:
            at = datetime.fromisoformat(row.data["occurred_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if at.tzinfo is None:
            continue
        allowed.append((at, row))
    if not allowed:
        return ()
    allowed.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    top = anchor or allowed[0][0]
    floor = top - timedelta(minutes=CONTEXT_WINDOW_MINUTES)
    chosen, size = [], 0
    for at, row in allowed:
        if not floor <= at <= top:
            continue
        message = {
            "message_id": row.id,
            "message_revision": row.revision,
            "occurred_at": row.data["occurred_at"],
            "text": row.data["text"],
        }
        cost = len(json.dumps(message, ensure_ascii=False).encode())
        if len(chosen) >= CONTEXT_MAX_MESSAGES or size + cost > CONTEXT_MAX_BYTES:
            break
        chosen.append(message)
        size += cost
    chosen.reverse()
    return tuple(chosen)
