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
