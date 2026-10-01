import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from sqlalchemy import select

from gigmate.config import ROOT
from gigmate.db import ChangeRow, ConversationRow, Inbox, Job, MessageRow
from gigmate.errors import BusinessError


def fixture(name):
    return json.loads((ROOT / "contracts/examples" / f"{name}.json").read_text(encoding="utf-8"))


def event_validator():
    registry = Registry()
    for path in (ROOT / "contracts").glob("**/*.schema.json"):
        registry = registry.with_resource(
            path.as_uri(), Resource.from_contents(json.loads(path.read_text(encoding="utf-8")))
        )
    return Draft202012Validator(
        {"$ref": (ROOT / "contracts/events/message-event.schema.json").as_uri()},
        registry=registry,
        format_checker=FormatChecker(),
    )


VALIDATOR = event_validator()


def replay_event(scenario):
    event = fixture("message-reschedule")
    if scenario == "available":
        event.update(
            event_id="00000000-0000-4000-8000-000000000017",
            provider_message_id="synthetic:available-time",
        )
        event["payload"] = {
            "message_id": "00000000-0000-4000-8000-000000000016",
            "text": "确认下星期四下午四点半到五点半，地址晚些发",
        }
    return event


def ingest(db, account, event):
    if list(VALIDATOR.iter_errors(event)):
        raise BusinessError(422, "VALIDATION_FAILED", "Invalid normalized replay event")
    if event["account_id"] != account.id:
        raise BusinessError(404, "NOT_FOUND", "Conversation not found")
    if (
        event["connector"] != "replay"
        or event["source"] != "replay"
        or event["event_type"] not in {"message.created", "message.edited", "message.revoked"}
    ):
        raise BusinessError(
            422,
            "VALIDATION_FAILED",
            "Skeleton replay supports synthetic text/edit/revoke events only",
        )
    conversation = db.scalar(
        select(ConversationRow)
        .where(
            ConversationRow.id == event["conversation_id"], ConversationRow.account_id == account.id
        )
        .with_for_update()
    )
    if not conversation or not conversation.allowlisted:
        raise BusinessError(404, "NOT_FOUND", "Conversation not found")
    encoded = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    previous = db.get(Inbox, event["event_id"])
    if previous:
        if previous.account_id != account.id or previous.digest != digest:
            raise BusinessError(
                409, "IDEMPOTENCY_CONFLICT", "Event identity was reused with different content"
            )
        return {
            "event_id": previous.id,
            "duplicate": True,
            "context_version": conversation.context_version,
        }
    message_id, revision = event["payload"]["message_id"], event["message_revision"]
    # Application message IDs cannot be reused to overwrite another account/conversation.
    versions = list(
        db.scalars(
            select(MessageRow)
            .where(MessageRow.id == message_id)
            .order_by(MessageRow.revision.desc())
        )
    )
    if versions and (
        versions[0].account_id != account.id or versions[0].conversation_id != conversation.id
    ):
        raise BusinessError(404, "NOT_FOUND", "Source message not found")
    same_identity = db.scalar(
        select(MessageRow).where(
            MessageRow.account_id == account.id,
            MessageRow.conversation_id == conversation.id,
            MessageRow.provider_message_id == event["provider_message_id"],
            MessageRow.revision == revision,
        )
    )
    if same_identity:
        if (
            same_identity.id != message_id
            or same_identity.data["text"] != event["payload"].get("text")
            or same_identity.data["revoked"] != (event["event_type"] == "message.revoked")
        ):
            raise BusinessError(409, "IDEMPOTENCY_CONFLICT", "Message revision identity conflicts")
        return {
            "event_id": event["event_id"],
            "duplicate": True,
            "context_version": conversation.context_version,
        }
    if event["event_type"] == "message.created" and (versions or revision != 1):
        raise BusinessError(409, "VERSION_CONFLICT", "Message creation must start at revision 1")
    if event["event_type"] != "message.created" and (
        not versions
        or revision != versions[0].revision + 1
        or versions[0].provider_message_id != event["provider_message_id"]
    ):
        raise BusinessError(409, "VERSION_CONFLICT", "Source revisions must advance in order")
    now = datetime.now(UTC)
    db.add(
        Inbox(
            id=event["event_id"],
            account_id=account.id,
            payload=event,
            digest=digest,
            received_at=now,
            context_version=conversation.context_version + 1,
        )
    )
    db.add(
        MessageRow(
            id=message_id,
            revision=revision,
            account_id=account.id,
            conversation_id=conversation.id,
            provider_message_id=event["provider_message_id"],
            data={
                "id": message_id,
                "account_id": account.id,
                "conversation_id": conversation.id,
                "provider_message_id": event["provider_message_id"],
                "revision": revision,
                "direction": event["direction"],
                "source": event["source"],
                "occurred_at": event["occurred_at"],
                "text": event["payload"].get("text"),
                "revoked": event["event_type"] == "message.revoked",
            },
        )
    )
    conversation.context_version += 1
    for change in db.scalars(
        select(ChangeRow).where(
            ChangeRow.conversation_id == conversation.id, ChangeRow.account_id == account.id
        )
    ):
        if change.data["status"] == "proposed":
            change.data = {**change.data, "status": "needs_review"}
    db.flush()
    db.add(
        Job(
            id=str(uuid4()),
            event_id=event["event_id"],
            account_id=account.id,
            state="pending",
            attempts=0,
            available_at=now,
        )
    )
    return {
        "event_id": event["event_id"],
        "duplicate": False,
        "context_version": conversation.context_version,
    }
