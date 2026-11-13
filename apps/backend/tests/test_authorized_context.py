"""Ordinary merchant-authorized synthetic chats; no activity or demo configuration."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_waha_ingress import ingress as ingress
from test_waha_ingress import raw

from gigmate.db import ConversationRow, WahaChat
from gigmate.waha_ingress import receive


@pytest.fixture
def authorized_context(ingress):
    _, factory, engine, _, binding, _ = ingress
    return SimpleNamespace(
        ingress=ingress,
        factory=factory,
        engine=engine,
        binding=binding,
        anchor=datetime.now(UTC) - timedelta(seconds=20),
    )


def authorize(ctx, *, peer="syntheticguest1@lid"):
    with ctx.factory.begin() as db:
        chat = db.scalar(select(WahaChat).where(WahaChat.provider_chat_id == peer))
        if chat:
            return chat.conversation_id
        identifier = str(uuid4())
        db.add(
            ConversationRow(
                id=identifier,
                account_id=ctx.binding.account_id,
                allowlisted=True,
                context_version=0,
            )
        )
        db.flush()
        db.add(
            WahaChat(
                id=str(uuid4()),
                connection_id=ctx.binding.connection_id,
                provider_chat_id=peer,
                conversation_id=identifier,
            )
        )
        return identifier


def event(
    ctx,
    *,
    peer="syntheticguest1@lid",
    body="Fictional repair request",
    seconds=3,
    kind="message.any",
    reference="synthetic:order-1",
):
    at = ctx.anchor + timedelta(seconds=seconds)
    value = raw(
        kind, event_id="synthetic:event-" + uuid4().hex, timestamp=int(at.timestamp() * 1000)
    )
    details = value["payload"].get("after") if kind == "message.revoked" else value["payload"]
    details.update({"from": peer, "timestamp": int(at.timestamp()), "body": body})
    if kind == "message.edited":
        value["payload"]["editedMessageId"] = reference
    elif kind == "message.revoked":
        value["payload"]["revokedMessageId"] = reference
    else:
        details["id"] = reference
    return value, at


def submit(ctx, value, at):
    with ctx.factory.begin() as db:
        return receive(db, ctx.binding, value, now=at)


def test_regrant_records_boundary_and_excludes_old_text(authorized_context, monkeypatch):
    from gigmate import waha_controls
    from gigmate.contracts import WahaSelectionCommand
    from gigmate.db import MessageRow, WahaConnection
    from gigmate.message_context import source_allowed

    ctx = authorized_context
    conversation_id = authorize(ctx)
    submit(ctx, *event(ctx, body="Old private detail"))
    monkeypatch.setattr(waha_controls, "settings", lambda row: None)
    with ctx.factory.begin() as db:
        connection = db.get(WahaConnection, ctx.binding.connection_id)
        conversation = db.get(ConversationRow, conversation_id)
        chat = db.scalar(select(WahaChat).where(WahaChat.conversation_id == conversation_id))
        old = db.scalar(select(MessageRow).where(MessageRow.conversation_id == conversation_id))
        assert source_allowed(db, conversation, old)
        waha_controls.select_chats(
            db,
            connection,
            WahaSelectionCommand(expected_version=0, selected_ids=[], consent=True),
        )
        assert not source_allowed(db, conversation, old)
        waha_controls.select_chats(
            db,
            connection,
            WahaSelectionCommand(expected_version=1, selected_ids=[chat.id], consent=True),
        )
        assert conversation.consent_context_version == conversation.context_version == 3
        assert conversation.allowlisted and not source_allowed(db, conversation, old)
        assert old.data["text"] == "Old private detail"
    submit(ctx, *event(ctx, body="New authorized detail", seconds=6, reference="synthetic:new"))
    with ctx.factory() as db:
        conversation = db.get(ConversationRow, conversation_id)
        latest = db.scalar(
            select(MessageRow).where(
                MessageRow.conversation_id == conversation_id,
                MessageRow.data["text"].as_string() == "New authorized detail",
            )
        )
        assert source_allowed(db, conversation, latest)
