"""Bounded provider reads and observation evidence; never fabricate source revisions."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4, uuid5

from sqlalchemy import delete, select, text

from gigmate import waha_controls as controls
from gigmate.db import (
    Account,
    ConversationRow,
    Inbox,
    Job,
    MessageRow,
    Session,
    WahaChat,
    WahaConnection,
    WahaExclusion,
    WahaMessage,
    WahaObservationReceipt,
    WahaRecoveryIssue,
    WahaSnapshot,
    WahaSourceGap,
    WahaSyncJob,
)
from gigmate.errors import BusinessError
from gigmate.waha_adapter import IDENTITY_NAMESPACE, AdapterError
from gigmate.waha_recovery import stamp


def uid(*values):
    return str(uuid5(IDENTITY_NAMESPACE, json.dumps(values, separators=(",", ":"))))


def utc(value):
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def fail(code, status=409):
    raise BusinessError(status, code, "Refresh authorization or review synchronization")


def identifier(value):
    value = value.get("_serialized") if isinstance(value, dict) else value
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(x) < 32 for x in value):
        raise AdapterError("INVALID_MESSAGE_REFERENCE")
    return value


def metadata(chat, item):
    """Allowlisted fields only: no URLs, embedded quoted bodies, _data or binary payloads."""
    reference = identifier(item.get("id"))
    outgoing = item.get("fromMe")
    media = item.get("hasMedia")
    if type(outgoing) is not bool or type(media) is not bool:
        raise AdapterError("INVALID_PROVIDER_SHAPE")
    peer = identifier(item.get("to") if outgoing else item.get("from"))
    if peer != chat.provider_chat_id:
        raise AdapterError("CONVERSATION_MAPPING_MISMATCH")
    body = item.get("body")
    if body is not None and (not isinstance(body, str) or len(body) > 8000):
        raise AdapterError("TEXT_LIMIT_EXCEEDED")
    attachment = item.get("media") if media else None
    attachment = attachment if isinstance(attachment, dict) else {}
    mime = attachment.get("mimetype")
    filename = attachment.get("filename")
    if mime is not None and (
        not isinstance(mime, str) or len(mime) > 128 or any(ord(x) < 32 for x in mime)
    ):
        raise AdapterError("INVALID_MEDIA_METADATA")
    if filename is not None and (
        not isinstance(filename, str) or len(filename) > 256 or any(ord(x) < 32 for x in filename)
    ):
        raise AdapterError("INVALID_MEDIA_METADATA")
    kind = "text"
    if media:
        kind = next(
            (k for k in ("image", "audio", "video") if (mime or "").startswith(k + "/")),
            "document" if mime else "other",
        )
    sender = item.get("participant")
    sender = uid("sender", chat.id, identifier(sender)) if sender else None
    reply = item.get("replyTo")
    reply = identifier(reply["id"]) if isinstance(reply, dict) and reply.get("id") else None
    return reference, dict(
        direction="outgoing" if outgoing else "incoming",
        text=body,
        kind=kind,
        mimetype=mime,
        filename=filename,
        sender_id=sender,
        reply_reference=reply,
        attachment_reading="deferred" if media else "not_applicable",
    )


def snapshot(db, chat, item, occurred, *, source, now, revoked=False):
    reference, data = metadata(chat, item)
    key = uid("snapshot", chat.id, reference)
    existing = db.get(WahaSnapshot, key)
    if existing:
        # Provider history is a current snapshot, not proof of the historical revisions.
        # It must never regress evidence received live (especially tombstones).
        if (
            existing.revoked
            or (
                source == "history"
                and (existing.source == "live" or utc(existing.observed_at) > now)
            )
            or (source == "live" and utc(existing.occurred_at) > occurred)
        ):
            return existing, False
        if existing.data.get("delivery_rank") is not None:
            data = {
                **data,
                "delivery_rank": existing.data["delivery_rank"],
                "delivery_status": existing.data["delivery_status"],
            }
        if existing.data == data and existing.revoked == revoked:
            return existing, False
        existing.data, existing.source = data, source
        existing.occurred_at, existing.observed_at, existing.revoked = occurred, now, revoked
        return existing, True
    row = WahaSnapshot(
        id=key,
        chat_id=chat.id,
        provider_message_id=reference,
        source=source,
        occurred_at=occurred,
        observed_at=now,
        revoked=revoked,
        data=data,
    )
    from gigmate.waha_ingress import stanza_id

    row.stanza_id = stanza_id(reference, chat.provider_chat_id, data["direction"] == "outgoing")
    db.add(row)
    db.flush()
    return row, True


def receive_media(db, connection, chat, conversation, raw, *, now):
    if "source" in raw and raw["source"] != "app":
        fail("SOURCE_MAPPING_MISMATCH", 422)
    payload = raw["payload"]
    kind = raw["event"]
    details = payload.get("after", {}) if kind == "message.revoked" else payload
    target = payload.get("revokedMessageId" if kind == "message.revoked" else "editedMessageId")
    target = target or details.get("id")
    existing = db.scalar(
        select(WahaSnapshot).where(
            WahaSnapshot.chat_id == chat.id, WahaSnapshot.provider_message_id == target
        )
    )
    if (
        not existing
        and isinstance(target, str)
        and "_" not in target
        and kind in {"message.ack", "message.edited", "message.revoked"}
    ):
        matches = list(
            db.scalars(
                select(WahaSnapshot).where(
                    WahaSnapshot.chat_id == chat.id, WahaSnapshot.stanza_id == target
                )
            )
        )
        matches = [
            s
            for s in matches
            if s.data["direction"] == ("outgoing" if details.get("fromMe") else "incoming")
        ]
        if len(matches) > 1:
            fail("SOURCE_MESSAGE_AMBIGUOUS")
        existing = matches[0] if matches else None
    if kind == "message.ack" and existing and existing.data["kind"] != "text":
        from gigmate.waha_adapter import ACK_NAMES, ACK_STATES

        ack = payload.get("ack")
        if type(ack) is not int or ack not in ACK_STATES:
            fail("UNSUPPORTED_ACK", 422)
        if "ackName" in payload and payload["ackName"] != ACK_NAMES[ack]:
            fail("ACK_MAPPING_MISMATCH", 422)
        if type(details.get("fromMe")) is not bool or existing.data["direction"] != (
            "outgoing" if details["fromMe"] else "incoming"
        ):
            fail("SOURCE_MAPPING_MISMATCH", 422)
        key = uid(connection.instance_id, connection.account_id, connection.session_id, raw["id"])
        digest = hashlib.sha256(
            json.dumps([kind, raw["timestamp"], target, ack], separators=(",", ":")).encode()
        ).hexdigest()
        previous = db.get(WahaObservationReceipt, key)
        if previous:
            if previous.connection_id != connection.id or previous.digest != digest:
                fail("IDEMPOTENCY_CONFLICT")
            connection.duplicates += 1
            return dict(
                event_id=key,
                duplicate=True,
                context_version=conversation.context_version,
                durable_acceptance=True,
                acceptance_kind="observation",
            )
        if db.get(Inbox, key):
            fail("IDEMPOTENCY_CONFLICT")
        rank = max(ack, existing.data.get("delivery_rank", 0))
        existing.data = {
            **existing.data,
            "delivery_rank": rank,
            "delivery_status": ACK_STATES[rank],
        }
        db.add(
            WahaObservationReceipt(
                id=key,
                connection_id=connection.id,
                snapshot_id=existing.id,
                digest=digest,
                received_at=now,
            )
        )
        connection.accepted += 1
        return dict(
            event_id=key,
            duplicate=False,
            context_version=conversation.context_version,
            durable_acceptance=True,
            acceptance_kind="observation",
        )
    if details.get("hasMedia") is not True and not (
        existing and existing.data.get("kind") != "text"
    ):
        return None
    if kind not in {"message", "message.any", "message.edited", "message.revoked"}:
        return None
    occurred = datetime.fromtimestamp(raw["timestamp"] / 1000, UTC)
    if existing and kind != "message.revoked" and existing.revoked:
        fail("SOURCE_REVOKED")
    normalized = {**details, "id": target}
    if existing:
        normalized["id"] = existing.provider_message_id
        if kind == "message.edited" and existing.data["kind"] != "text":
            normalized["hasMedia"] = True
            normalized["media"] = {
                "mimetype": existing.data.get("mimetype"),
                "filename": existing.data.get("filename"),
                **(details.get("media") if isinstance(details.get("media"), dict) else {}),
            }
    if kind == "message.revoked" and existing:
        normalized = dict(
            id=existing.provider_message_id,
            fromMe=existing.data["direction"] == "outgoing",
            hasMedia=True,
            body=None,
            media={
                "mimetype": existing.data.get("mimetype"),
                "filename": existing.data.get("filename"),
            },
        )
        normalized["to" if normalized["fromMe"] else "from"] = chat.provider_chat_id
    reference, data = metadata(chat, normalized)
    event_id = uid(connection.instance_id, connection.account_id, connection.session_id, raw["id"])
    digest = hashlib.sha256(
        json.dumps(
            [kind, raw["timestamp"], reference, data], sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    previous = db.get(WahaObservationReceipt, event_id)
    if previous:
        if previous.connection_id != connection.id or previous.digest != digest:
            fail("IDEMPOTENCY_CONFLICT")
        connection.duplicates += 1
        return dict(
            event_id=event_id,
            duplicate=True,
            context_version=conversation.context_version,
            durable_acceptance=True,
            acceptance_kind="observation",
        )
    if db.get(Inbox, event_id):
        fail("IDEMPOTENCY_CONFLICT")
    if (
        existing
        and occurred <= utc(existing.occurred_at)
        and kind in {"message.edited", "message.revoked"}
    ):
        fail("SOURCE_ORDER_NEEDS_RECONCILIATION")
    row, changed = snapshot(
        db, chat, normalized, occurred, source="live", now=now, revoked=kind == "message.revoked"
    )
    db.add(
        WahaObservationReceipt(
            id=event_id,
            connection_id=connection.id,
            snapshot_id=row.id,
            digest=digest,
            received_at=now,
        )
    )
    if changed:
        from gigmate.db import ChangeRow

        conversation.context_version += 1
        for change in db.scalars(
            select(ChangeRow).where(ChangeRow.conversation_id == conversation.id)
        ):
            if change.data["status"] == "proposed":
                change.data = {**change.data, "status": "needs_review"}
    connection.accepted += 1
    if not changed:
        connection.duplicates += 1
    connection.last_sync_at = now
    db.flush()
    return dict(
        event_id=event_id,
        duplicate=not changed,
        context_version=conversation.context_version,
        durable_acceptance=True,
        acceptance_kind="observation",
    )


def observe_text(db, chat, raw, now):
    if raw["event"] not in {"message", "message.any", "message.edited"}:
        return
    item = dict(raw["payload"])
    item["id"] = item.get("editedMessageId") or item.get("id")
    # Live text remains canonical in message_revisions; only extended provenance here.
    item["body"] = None
    snapshot(
        db, chat, item, datetime.fromtimestamp(raw["timestamp"] / 1000, UTC), source="live", now=now
    )


def authorization_changed(db, connection, chat_id, denied, now=None):
    now = now or datetime.now(UTC)
    condition = (
        WahaExclusion.chat_id.is_(None) if chat_id is None else WahaExclusion.chat_id == chat_id
    )
    opened = db.scalar(
        select(WahaExclusion).where(
            WahaExclusion.connection_id == connection.id,
            condition,
            WahaExclusion.ended_at.is_(None),
        )
    )
    if denied and opened is None:
        db.add(
            WahaExclusion(
                id=str(uuid4()), connection_id=connection.id, chat_id=chat_id, started_at=now
            )
        )
    elif not denied and opened:
        opened.ended_at = now
    if denied:
        from gigmate.waha_media import revoke_jobs

        revoke_jobs(db, connection, chat_id)
        for job in db.scalars(select(WahaSyncJob).where(WahaSyncJob.active_key == connection.id)):
            job.state, job.active_key, job.lease_token = "cancelled", None, None
            job.updated_at, job.error_code = now, "CONSENT_REVOKED"


def chat_owned(db, row, identifier, *, require_consent=True):
    chat = db.scalar(
        select(WahaChat).where(WahaChat.id == identifier, WahaChat.connection_id == row.id)
    )
    conv = db.get(ConversationRow, chat.conversation_id) if chat else None
    if not conv or conv.account_id != row.account_id or (require_consent and not conv.allowlisted):
        fail("NOT_FOUND", 404)
    return chat


def capture_gap(db, binding, raw, code):
    if code != "SOURCE_MESSAGE_UNRESOLVED" or not isinstance(raw, dict):
        return
    if raw.get("source", "app") != "app":
        return
    connection = db.get(WahaConnection, binding.connection_id)
    account = db.get(Account, binding.account_id)
    if (
        not connection
        or not connection.enabled
        or not account
        or not account.active
        or raw.get("session") != binding.session_id
    ):
        return
    p = raw.get("payload", {})
    if not isinstance(p, dict):
        return
    details = p.get("after", {}) if raw.get("event") == "message.revoked" else p
    if not isinstance(details, dict) or type(details.get("fromMe")) is not bool:
        return
    try:
        peer = identifier(details.get("to") if details["fromMe"] else details.get("from"))
        target = identifier(
            p.get(
                "revokedMessageId" if raw.get("event") == "message.revoked" else "editedMessageId"
            )
            or p.get("id")
        )
    except AdapterError:
        return
    chat = db.scalar(
        select(WahaChat).where(
            WahaChat.connection_id == connection.id, WahaChat.provider_chat_id == peer
        )
    )
    conv = db.get(ConversationRow, chat.conversation_id) if chat else None
    if not conv or not conv.allowlisted or conv.account_id != account.id:
        return
    direction = "outgoing" if details["fromMe"] else "incoming"
    key = uid("source-gap", chat.id, target, direction)
    if not db.get(WahaSourceGap, key):
        db.add(
            WahaSourceGap(
                id=key,
                chat_id=chat.id,
                provider_reference=target,
                direction=direction,
                observed_at=datetime.now(UTC),
                state="needs_lookup",
            )
        )


def job_view(job):
    p = job.progress
    return dict(
        id=job.id,
        connection_id=job.connection_id,
        state=job.state,
        chat_ids=job.command["chat_ids"],
        since=job.command["since"],
        until=job.command["until"],
        max_records=job.command["max_records"],
        issue_id=job.command.get("issue_id"),
        source_gap_id=job.command.get("source_gap_id"),
        imported=p.get("imported", 0),
        duplicates=p.get("duplicates", 0),
        skipped=p.get("skipped", 0),
        pages=p.get("pages", 0),
        attempts=p.get("read_attempts", job.attempts),
        coverage=p.get("coverage", "in_progress"),
        complete_history=False,
        error_code=job.error_code,
        created_at=stamp(job.created_at),
        updated_at=stamp(job.updated_at),
    )


def enqueue(db, row, command, key):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key):
        fail("INVALID_IDEMPOTENCY_KEY", 422)
    body = command.model_dump(mode="json")
    previous = db.scalar(
        select(WahaSyncJob).where(
            WahaSyncJob.connection_id == row.id, WahaSyncJob.request_key == key
        )
    )
    if previous:
        if previous.command != body:
            fail("IDEMPOTENCY_CONFLICT")
        return job_view(previous)
    controls.version(row, command.expected_version)
    controls.settings(row)
    if not row.enabled:
        fail("CONNECTOR_PAUSED", 403)
    if command.consent is not True or len(set(command.chat_ids)) != len(command.chat_ids):
        fail("EXPLICIT_SYNC_CONSENT_REQUIRED", 422)
    now = datetime.now(UTC)
    start, end = (
        datetime.fromisoformat(x.replace("Z", "+00:00")) for x in (command.since, command.until)
    )
    if not now - timedelta(days=30) <= start < end <= now:
        fail("INVALID_SYNC_RANGE", 422)
    for chat in command.chat_ids:
        chat_owned(db, row, chat)
    if command.issue_id and command.source_gap_id:
        fail("INVALID_SYNC_TARGET", 422)
    if command.issue_id:
        issue = db.get(WahaRecoveryIssue, command.issue_id)
        if not issue or issue.connection_id != row.id:
            fail("NOT_FOUND", 404)
        if not issue.recovered_at or start < utc(issue.started_at) or end > utc(issue.recovered_at):
            fail("INVALID_GAP_RANGE", 422)
    if command.source_gap_id:
        gap = db.get(WahaSourceGap, command.source_gap_id)
        if not gap or command.chat_ids != [gap.chat_id]:
            fail("NOT_FOUND", 404)
    if db.scalar(select(WahaSyncJob.id).where(WahaSyncJob.active_key == row.id)):
        fail("SYNC_ALREADY_ACTIVE")
    job = WahaSyncJob(
        id=str(uuid4()),
        account_id=row.account_id,
        connection_id=row.id,
        request_key=key,
        version=row.control_version,
        state="pending",
        active_key=row.id,
        command=body,
        progress={},
        attempts=0,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()
    return job_view(job)


def cancel(db, row, identifier):
    job = db.scalar(
        select(WahaSyncJob)
        .where(WahaSyncJob.id == identifier, WahaSyncJob.connection_id == row.id)
        .with_for_update()
    )
    if not job:
        fail("NOT_FOUND", 404)
    if job.state in {"pending", "running"}:
        job.state, job.active_key, job.lease_token = "cancelled", None, None
        job.updated_at, job.error_code = datetime.now(UTC), "USER_CANCELLED"
        job.progress = {**job.progress, "coverage": "incomplete"}
    return job_view(job)


def excluded(db, row, chat, at):
    return (
        db.scalar(
            select(WahaExclusion.id).where(
                WahaExclusion.connection_id == row.id,
                (WahaExclusion.chat_id.is_(None)) | (WahaExclusion.chat_id == chat.id),
                WahaExclusion.started_at <= at,
                (WahaExclusion.ended_at.is_(None)) | (WahaExclusion.ended_at > at),
            )
        )
        is not None
    )


def run_once(factory=Session, make_client=controls.client_for):
    now = datetime.now(UTC)
    with factory.begin() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '3s'"))
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
        candidate = db.scalar(
            select(WahaSyncJob)
            .where(WahaSyncJob.active_key.is_not(None))
            .order_by(WahaSyncJob.created_at)
            .limit(1)
        )
        if not candidate:
            return False
        account = db.scalar(
            select(Account).where(Account.id == candidate.account_id).with_for_update()
        )
        row = db.scalar(
            select(WahaConnection)
            .where(WahaConnection.id == candidate.connection_id)
            .with_for_update()
        )
        job = db.scalar(
            select(WahaSyncJob)
            .where(WahaSyncJob.id == candidate.id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if not job or not job.active_key:
            return False
        if job.state == "running" and job.lease_until and utc(job.lease_until) > now:
            return False
        if not account.active or not row.enabled or row.control_version != job.version:
            job.state, job.active_key, job.error_code = "cancelled", None, "WAHA_SETUP_CHANGED"
            job.progress = {**job.progress, "coverage": "incomplete"}
            job.updated_at = now
            return True
        if job.attempts >= 3:
            job.state, job.active_key, job.error_code = "failed", None, "SYNC_RETRIES_EXHAUSTED"
            job.progress = {**job.progress, "coverage": "incomplete"}
            job.updated_at = now
            return True
        p = dict(job.progress)
        if p.get("retry_at") and datetime.fromisoformat(p["retry_at"].replace("Z", "+00:00")) > now:
            return False
        try:
            chat = chat_owned(db, row, job.command["chat_ids"][p.get("chat_index", 0)])
        except BusinessError:
            job.state, job.active_key, job.error_code = "cancelled", None, "CONSENT_REVOKED"
            job.progress = {**job.progress, "coverage": "incomplete"}
            job.updated_at = now
            return True
        start, end = (
            datetime.fromisoformat(job.command[x].replace("Z", "+00:00"))
            for x in ("since", "until")
        )
        if start < now - timedelta(days=30):
            job.state, job.active_key, job.error_code = "failed", None, "SYNC_RANGE_EXPIRED"
            job.progress = {**job.progress, "coverage": "incomplete"}
            job.updated_at = now
            return True
        remaining = job.command["max_records"] - p.get("scanned", 0)
        limit = min(50, remaining)
        gap = (
            db.get(WahaSourceGap, job.command["source_gap_id"])
            if job.command.get("source_gap_id")
            else None
        )
        reference = gap.provider_reference if gap else None
        expected_direction = gap.direction if gap else None
        if job.command.get("source_gap_id") and (gap is None or gap.chat_id != chat.id):
            job.state, job.active_key, job.error_code = "failed", None, "SOURCE_TARGET_UNAVAILABLE"
            job.progress = {**job.progress, "coverage": "incomplete"}
            job.updated_at = now
            return True
        token = str(uuid4())
        job.state, job.lease_token, job.lease_until = "running", token, now + timedelta(seconds=120)
        job.attempts += 1
        p["read_attempts"] = p.get("read_attempts", 0) + 1
        job.progress = p
        job.updated_at = now
        job_id, connection_id, account_id, chat_id, peer = (
            job.id,
            row.id,
            account.id,
            chat.id,
            chat.provider_chat_id,
        )
        try:
            client = make_client(row)
        except (AdapterError, BusinessError):
            job.state, job.active_key, job.error_code = (
                "failed",
                None,
                "WAHA_CONTROL_CONFIG_INVALID",
            )
            return True
    error = None
    try:
        items = (
            [client.message_snapshot(peer, reference)]
            if reference
            else client.history_page(
                peer,
                since=int(start.timestamp()),
                until=int(end.timestamp()),
                offset=p.get("offset", 0),
                limit=limit,
            )
        )
    except (AdapterError, BusinessError) as exc:
        error = exc.code
        items = []
    except Exception:
        error = "SYNC_PROVIDER_READ_FAILED"
        items = []
    finally:
        client.close()
    with factory.begin() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '3s'"))
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
        account = db.scalar(select(Account).where(Account.id == account_id).with_for_update())
        row = db.scalar(
            select(WahaConnection).where(WahaConnection.id == connection_id).with_for_update()
        )
        job = db.scalar(select(WahaSyncJob).where(WahaSyncJob.id == job_id).with_for_update())
        if job.state != "running" or job.lease_token != token:
            return True
        if not account.active or not row.enabled or row.control_version != job.version:
            job.state, job.active_key, job.error_code = "cancelled", None, "WAHA_SETUP_CHANGED"
            job.progress = {**job.progress, "coverage": "incomplete"}
        else:
            chat = chat_owned(db, row, chat_id)
            if error:
                job.state = "pending" if job.attempts < 3 else "failed"
                job.error_code = error
                job.progress = {
                    **job.progress,
                    "retry_at": stamp(datetime.now(UTC) + timedelta(seconds=2**job.attempts)),
                }
                if job.state == "failed":
                    job.active_key = None
                    job.progress = {**job.progress, "coverage": "incomplete"}
                    if job.command.get("source_gap_id") and error == "WAHA_RESOURCE_NOT_FOUND":
                        db.get(WahaSourceGap, job.command["source_gap_id"]).state = "unavailable"
            else:
                for item in items:
                    p["scanned"] = p.get("scanned", 0) + 1
                    try:
                        ts = item.get("timestamp")
                        if type(ts) is not int or ts < 0:
                            raise AdapterError("INVALID_TIMESTAMP")
                        at = datetime.fromtimestamp(ts / 1000 if ts > 10**12 else ts, UTC)
                        if not start <= at <= end or excluded(db, row, chat, at):
                            p["skipped"] = p.get("skipped", 0) + 1
                            continue
                        ref = identifier(item.get("id"))
                        if (
                            reference
                            and ("outgoing" if item.get("fromMe") else "incoming")
                            != expected_direction
                        ):
                            raise AdapterError("SOURCE_MAPPING_MISMATCH")
                        known = db.scalar(
                            select(MessageRow)
                            .where(
                                MessageRow.account_id == account.id,
                                MessageRow.conversation_id == chat.conversation_id,
                                MessageRow.provider_message_id == ref,
                            )
                            .order_by(MessageRow.revision.desc())
                            .limit(1)
                        )
                        if known and known.data["revoked"]:
                            p["skipped"] = p.get("skipped", 0) + 1
                            continue
                        if known:
                            item = {**item, "body": None}
                        if reference and ref != reference:
                            # A short reference may be resolved only to one canonical ID in this owned chat.
                            from gigmate.waha_ingress import stanza_id

                            if stanza_id(ref, peer, item.get("fromMe")) != reference:
                                raise AdapterError("MESSAGE_MAPPING_MISMATCH")
                        _, changed = snapshot(
                            db,
                            chat,
                            item,
                            at,
                            source="history",
                            now=now,
                            revoked=False,
                        )
                        count = "imported" if changed else "duplicates"
                        p[count] = p.get(count, 0) + 1
                        if reference:
                            db.get(
                                WahaSourceGap, job.command["source_gap_id"]
                            ).state = "snapshot_found"
                    except (AdapterError, ValueError, OverflowError, OSError):
                        p["skipped"] = p.get("skipped", 0) + 1
                p["pages"] = p.get("pages", 0) + 1
                if reference or not items:
                    p["chat_index"] = p.get("chat_index", 0) + 1
                    p["offset"] = 0
                else:
                    p["offset"] = p.get("offset", 0) + limit
                done = p.get("chat_index", 0) >= len(job.command["chat_ids"])
                capped = (
                    p.get("scanned", 0) >= job.command["max_records"] or p["pages"] >= 100
                ) and not done
                job.state = "succeeded" if done or capped else "pending"
                p["coverage"] = (
                    "limit_reached" if capped else "provider_exhausted" if done else "in_progress"
                )
                if p.get("skipped", 0) > 0 and done:
                    p["coverage"] = "incomplete"
                job.attempts = 0
                job.error_code = None
                if done or capped:
                    job.active_key = None
                job.progress = p
        job.lease_until, job.lease_token = None, None
        job.updated_at = datetime.now(UTC)
    return True


def timeline(db, row, chat_id):
    chat = chat_owned(db, row, chat_id)
    latest = {}
    for message in db.scalars(
        select(MessageRow)
        .where(
            MessageRow.account_id == row.account_id,
            MessageRow.conversation_id == chat.conversation_id,
        )
        .order_by(MessageRow.revision)
    ):
        latest[message.provider_message_id] = message
    snapshots = {
        s.provider_message_id: s
        for s in db.scalars(select(WahaSnapshot).where(WahaSnapshot.chat_id == chat.id))
    }
    jobs = {}
    for job, message_id in db.execute(
        select(Job, Inbox.payload["payload"]["message_id"].as_string())
        .join(Inbox, Inbox.id == Job.event_id)
        .where(
            Inbox.account_id == row.account_id,
            Inbox.payload["conversation_id"].as_string() == chat.conversation_id,
        )
        .order_by(Inbox.received_at.desc())
    ):
        jobs.setdefault(message_id, job)
    deliveries = {
        m.provider_message_id: m.delivery_rank
        for m in db.scalars(select(WahaMessage).where(WahaMessage.chat_id == chat.id))
    }
    result = []
    for ref in latest.keys() | snapshots.keys():
        message = latest.get(ref)
        snap = snapshots.get(ref)
        data = message.data if message else snap.data
        meta = snap.data if snap else {}
        reply = meta.get("reply_reference")
        linked = latest.get(reply) or snapshots.get(reply)
        job = jobs.get(message.id) if message else None
        from gigmate.waha_adapter import ACK_STATES

        result.append(
            dict(
                id=uid("snapshot", chat.id, ref),
                chat_id=chat.id,
                conversation_id=chat.conversation_id,
                source_message_id=message.id if message else None,
                occurred_at=data["occurred_at"] if message else stamp(snap.occurred_at),
                observed_at=stamp(snap.observed_at) if snap else data["occurred_at"],
                origin="live" if message or snap.source == "live" else "history",
                evidence="revision" if message else "snapshot",
                revision=message.revision if message else None,
                direction=data["direction"],
                text=None
                if data.get("revoked", False) or (snap and snap.revoked)
                else data.get("text"),
                revoked=bool(data.get("revoked", False) or (snap and snap.revoked)),
                kind=meta.get("kind", "text"),
                mimetype=meta.get("mimetype"),
                filename=meta.get("filename"),
                sender_id=meta.get("sender_id"),
                reply_to_id=uid("snapshot", chat.id, reply) if linked else None,
                attachment_reading=meta.get("attachment_reading", "not_applicable"),
                processing_state=job.state if job else None,
                delivery_status=ACK_STATES.get(deliveries.get(ref))
                if message
                else meta.get("delivery_status"),
            )
        )
    return result


def purge(db, connection_id, cutoff):
    chats = select(WahaChat.id).where(WahaChat.connection_id == connection_id)
    db.execute(
        delete(WahaObservationReceipt).where(
            WahaObservationReceipt.connection_id == connection_id,
            WahaObservationReceipt.received_at < cutoff,
        )
    )
    # Scrub content and metadata even when live revisions/identity must remain.
    for item in db.scalars(
        select(WahaSnapshot).where(
            WahaSnapshot.chat_id.in_(chats), WahaSnapshot.occurred_at < cutoff
        )
    ):
        item.data = {
            **item.data,
            "text": None,
            "filename": None,
            "sender_id": None,
            "reply_reference": None,
        }
    db.execute(
        delete(WahaSyncJob).where(
            WahaSyncJob.connection_id == connection_id,
            WahaSyncJob.active_key.is_(None),
            WahaSyncJob.updated_at < cutoff,
        )
    )
    db.execute(
        delete(WahaSourceGap).where(
            WahaSourceGap.chat_id.in_(chats), WahaSourceGap.observed_at < cutoff
        )
    )
