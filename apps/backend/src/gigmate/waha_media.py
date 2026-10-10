"""Explicit owned media reads, private blobs and lease-based A/B processing handoff."""

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from gigmate import media_processing
from gigmate import waha_controls as controls
from gigmate.contracts import WahaMediaResult
from gigmate.db import (
    Account,
    ConversationRow,
    Session,
    WahaAttachment,
    WahaChat,
    WahaMediaJob,
    WahaSnapshot,
)
from gigmate.errors import BusinessError
from gigmate.waha_adapter import AdapterError
from gigmate.waha_recovery import stamp
from gigmate.waha_sync import uid, utc

MAX_BYTES = 20 * 1024 * 1024
TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "audio/ogg",
    "audio/mpeg",
    "audio/wav",
    "audio/mp4",
    "application/pdf",
    "text/plain",
}


def fail(code, status=409):
    raise BusinessError(status, code, "Check media authorization, source and processing status")


def base_mime(value):
    return value.split(";", 1)[0].strip().lower() if isinstance(value, str) else None


def capabilities():
    directory = os.environ.get("WAHA_MEDIA_ROOT", "")
    configured = Path(directory) if directory else None
    try:
        usable = bool(
            configured
            and configured.is_absolute()
            and not configured.is_symlink()
            and (
                not configured.exists() or (configured.is_dir() and os.access(configured, os.W_OK))
            )
        )
    except OSError:
        usable = False
    return dict(
        enabled=os.environ.get("WAHA_MEDIA_ENABLED") == "true" and usable,
        processor_configured=bool(os.environ.get("GIGMATE_MEDIA_PROCESSOR_FACTORY")),
        max_bytes=MAX_BYTES,
        accepted_types=sorted(TYPES),
    )


def root():
    if not capabilities()["enabled"]:
        fail("MEDIA_STORAGE_NOT_CONFIGURED", 503)
    configured = Path(os.environ["WAHA_MEDIA_ROOT"])
    if not configured.is_absolute() or configured.is_symlink():
        fail("MEDIA_STORAGE_NOT_CONFIGURED", 503)
    try:
        configured.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        fail("MEDIA_STORAGE_NOT_CONFIGURED", 503)
    return configured.resolve()


def blob_path(key):
    if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{32}\.blob", key):
        fail("MEDIA_STORAGE_INVALID", 503)
    path = root() / key
    if path.is_symlink() or path.resolve().parent != root():
        fail("MEDIA_STORAGE_INVALID", 503)
    return path


def fingerprint(snapshot):
    # ACK/delivery updates are not content changes. Captions/edits/revokes are.
    projection = {
        k: snapshot.data.get(k)
        for k in (
            "direction",
            "kind",
            "mimetype",
            "filename",
            "text",
            "sender_id",
            "reply_reference",
        )
    }
    return hashlib.sha256(
        json.dumps(
            [snapshot.id, snapshot.revoked, stamp(snapshot.occurred_at), projection],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def source(db, row, snapshot_id, *, enabled=True):
    snapshot = db.get(WahaSnapshot, snapshot_id)
    chat = db.get(WahaChat, snapshot.chat_id) if snapshot else None
    conv = db.get(ConversationRow, chat.conversation_id) if chat else None
    if (
        not chat
        or chat.connection_id != row.id
        or not conv
        or conv.account_id != row.account_id
        or not conv.allowlisted
    ):
        fail("NOT_FOUND", 404)
    if enabled and not row.enabled:
        fail("CONSENT_REVOKED", 403)
    if snapshot.revoked:
        fail("SOURCE_REVOKED")
    if snapshot.data.get("kind") == "text" or base_mime(snapshot.data.get("mimetype")) not in TYPES:
        fail("MEDIA_TYPE_UNSUPPORTED", 422)
    if utc(snapshot.occurred_at) < datetime.now(UTC) - timedelta(days=30):
        fail("MEDIA_SOURCE_EXPIRED")
    return snapshot, chat, conv


def attachment_owned(db, row, identifier):
    asset = db.get(WahaAttachment, identifier)
    if not asset or asset.connection_id != row.id or asset.account_id != row.account_id:
        fail("NOT_FOUND", 404)
    snap, chat, conv = source(db, row, asset.snapshot_id)
    if asset.expires_at and utc(asset.expires_at) <= datetime.now(UTC):
        fail("MEDIA_SOURCE_EXPIRED")
    return asset, snap, chat, conv


def attachment_view(db, row, asset):
    _, snap, _, conv = attachment_owned(db, row, asset.id)
    valid = asset.source_fingerprint == fingerprint(snap)
    result_valid = (
        valid and asset.result and asset.result.get("context_version") == conv.context_version
    )
    review = (
        asset.review
        if result_valid
        and asset.review
        and asset.review.get("context_version") == conv.context_version
        and asset.review.get("result_job_id") == asset.result.get("job_id")
        and asset.review.get("attachment_version") == asset.version
        and asset.review.get("sha256") == asset.sha256
        else None
    )
    latest = db.scalar(
        select(WahaMediaJob)
        .where(WahaMediaJob.attachment_id == asset.id)
        .order_by(WahaMediaJob.created_at.desc(), WahaMediaJob.id.desc())
        .limit(1)
    )
    return dict(
        id=asset.id,
        snapshot_id=asset.snapshot_id,
        version=asset.version,
        context_version=conv.context_version,
        state=asset.state if valid and (not asset.result or result_valid) else "stale",
        mimetype=asset.mimetype,
        size_bytes=asset.size_bytes,
        sha256=asset.sha256,
        preview_available=valid and bool(asset.blob_key),
        source_fingerprint=asset.source_fingerprint,
        expires_at=stamp(asset.expires_at),
        result=asset.result.get("payload") if result_valid else None,
        result_job_id=asset.result.get("job_id") if result_valid else None,
        reviewed_at=review.get("at") if review else None,
        review_note=review.get("note") if review else None,
        latest_job_id=latest.id if latest else None,
        input_context=asset.result.get("input_context")
        if result_valid
        else (latest.input_context if latest else None),
    )


def job_view(job):
    return dict(
        id=job.id,
        attachment_id=job.attachment_id,
        state=job.state,
        stage=job.stage,
        attempts=job.attempts,
        error_code=job.error_code,
        updated_at=stamp(job.updated_at),
    )


def enqueue(db, row, command, key):
    body = command.model_dump(mode="json")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key):
        fail("INVALID_IDEMPOTENCY_KEY", 422)
    previous = db.scalar(
        select(WahaMediaJob).where(
            WahaMediaJob.connection_id == row.id, WahaMediaJob.request_key == key
        )
    )
    if previous:
        if {**previous.command, "timezone": previous.command.get("timezone")} != body:
            fail("IDEMPOTENCY_CONFLICT")
        attachment_owned(db, row, previous.attachment_id)
        return job_view(previous)
    controls.version(row, command.expected_version)
    root()
    snap, _, conv = source(db, row, str(command.snapshot_id))
    identifier = uid("attachment", snap.id)
    asset = db.get(WahaAttachment, identifier)
    current = fingerprint(snap)
    if asset and asset.source_fingerprint == current and utc(asset.expires_at) <= datetime.now(UTC):
        fail("MEDIA_SOURCE_EXPIRED")
    cached = bool(asset and asset.source_fingerprint == current and asset.blob_key)
    if cached:
        try:
            read_blob(asset)
        except BusinessError:
            cached = False
    if not cached:
        controls.settings(row)
    if asset:
        active = db.scalar(select(WahaMediaJob).where(WahaMediaJob.active_key == asset.id))
        if active:
            fail("MEDIA_JOB_ACTIVE_OR_UNKNOWN")
        if asset.source_fingerprint != current:
            asset.version += 1
            asset.expires_at = utc(snap.occurred_at) + timedelta(days=30)
            asset.source_fingerprint = current
            asset.state, asset.result, asset.review = "stale", None, None
            asset.blob_key, asset.sha256, asset.size_bytes, asset.mimetype = None, None, None, None
    else:
        asset = WahaAttachment(
            id=identifier,
            snapshot_id=snap.id,
            connection_id=row.id,
            account_id=row.account_id,
            source_fingerprint=current,
            version=1,
            state="pending",
            created_at=datetime.now(UTC),
            expires_at=utc(snap.occurred_at) + timedelta(days=30),
        )
        db.add(asset)
        db.flush()
    job = WahaMediaJob(
        id=str(uuid4()),
        attachment_id=asset.id,
        connection_id=row.id,
        request_key=key,
        command=body,
        input_context=dict(
            message_sent_at=stamp(snap.message_sent_at) if snap.message_sent_at else None,
            timezone=command.timezone,
            timezone_source="merchant_choice" if command.timezone else "unknown",
            source_occurred_at=stamp(snap.occurred_at),
            source_observed_at=stamp(snap.observed_at),
        ),
        version=row.control_version,
        context_version=conv.context_version,
        source_fingerprint=current,
        state="pending",
        stage="processing" if cached and command.process else "download",
        active_key=asset.id,
        attempts=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(job)
    db.flush()
    return job_view(job)


def cancel(db, row, identifier):
    job = db.get(WahaMediaJob, identifier)
    if not job or job.connection_id != row.id:
        fail("NOT_FOUND", 404)
    if job.state == "result_unknown":
        fail("MEDIA_PROCESSING_RECONCILIATION_REQUIRED")
    if job.active_key:
        job.state, job.active_key, job.lease_token = "cancelled", None, None
        job.error_code, job.updated_at = "MEDIA_CANCELLED", datetime.now(UTC)
    return job_view(job)


def revoke_jobs(db, row, chat_id=None):
    if not capabilities()["enabled"]:
        return
    try:
        with db.begin_nested():
            _revoke_jobs(db, row, chat_id)
    except SQLAlchemyError:
        # Optional media bookkeeping must not block revoking core permission.
        # Finalization and preview independently recheck authoritative consent.
        logging.getLogger(__name__).error(
            "media_revoke_hook_failed code=MEDIA_DATABASE_UNAVAILABLE"
        )


def _revoke_jobs(db, row, chat_id=None):
    for job in db.scalars(
        select(WahaMediaJob).where(
            WahaMediaJob.connection_id == row.id, WahaMediaJob.active_key.is_not(None)
        )
    ):
        asset = db.get(WahaAttachment, job.attachment_id)
        snap = db.get(WahaSnapshot, asset.snapshot_id)
        if chat_id is None or snap.chat_id == chat_id:
            # Keep uncertain model submissions blocking reissue until separate review.
            if job.state != "result_unknown":
                job.state, job.active_key, job.lease_token = "cancelled", None, None
            job.error_code, job.updated_at = "CONSENT_REVOKED", datetime.now(UTC)
            asset.review = None


def reconcile(db, row, identifier):
    job = db.get(WahaMediaJob, identifier)
    if not job or job.connection_id != row.id:
        fail("NOT_FOUND", 404)
    if job.state != "result_unknown":
        fail("MEDIA_RECONCILIATION_NOT_REQUIRED")
    _, snap, _, conv = attachment_owned(db, row, job.attachment_id)
    if fingerprint(snap) != job.source_fingerprint or conv.context_version != job.context_version:
        fail("MEDIA_SOURCE_CHANGED")
    job.version, job.stage, job.state = row.control_version, "reconciling", "pending"
    job.attempts, job.retry_at, job.error_code = 0, None, None
    job.updated_at = datetime.now(UTC)
    return job_view(job)


def validate_bytes(data, declared):
    if not data or len(data) > MAX_BYTES:
        raise AdapterError("MEDIA_SIZE_LIMIT")
    actual = None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        actual = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        actual = "image/jpeg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        actual = "image/webp"
    elif data.startswith(b"OggS"):
        actual = "audio/ogg"
    elif data.startswith(b"ID3") or (len(data) > 1 and data[0] == 255 and data[1] & 0xE0 == 0xE0):
        actual = "audio/mpeg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        actual = "audio/wav"
    elif data[4:8] == b"ftyp" and data[8:12] in {b"M4A ", b"M4B "} and declared == "audio/mp4":
        actual = "audio/mp4"
    elif data.startswith(b"%PDF-"):
        actual = "application/pdf"
    elif declared == "text/plain":
        if len(data) > 1024 * 1024:
            raise AdapterError("MEDIA_TEXT_SIZE_LIMIT")
        try:
            value = data.decode("utf-8-sig")
            if any(ord(c) < 32 and c not in "\r\n\t" for c in value):
                raise ValueError
            actual = "text/plain"
        except (UnicodeDecodeError, ValueError):
            raise AdapterError("MEDIA_TEXT_ENCODING_UNSUPPORTED") from None
    if actual != declared or actual not in TYPES:
        raise AdapterError("MEDIA_TYPE_MISMATCH")
    return actual


def read_blob(asset):
    if not asset.blob_key:
        fail("MEDIA_NOT_DOWNLOADED")
    try:
        with blob_path(asset.blob_key).open("rb") as file:
            value = file.read(MAX_BYTES + 1)
    except OSError:
        fail("MEDIA_FILE_UNAVAILABLE", 503)
    if len(value) > MAX_BYTES or hashlib.sha256(value).hexdigest() != asset.sha256:
        fail("MEDIA_INTEGRITY_FAILED", 503)
    return value


def preview(db, row, identifier):
    asset, snap, _, _ = attachment_owned(db, row, identifier)
    if asset.source_fingerprint != fingerprint(snap):
        fail("MEDIA_SOURCE_CHANGED")
    return read_blob(asset), asset.mimetype


def review(db, row, identifier, command):
    asset, snap, _, conv = attachment_owned(db, row, identifier)
    if (
        asset.version != command.expected_attachment_version
        or conv.context_version != command.expected_context_version
        or asset.source_fingerprint != fingerprint(snap)
    ):
        fail("MEDIA_SOURCE_CHANGED")
    if not asset.result:
        fail("MEDIA_RESULT_UNAVAILABLE")
    if asset.result.get("context_version") != conv.context_version:
        fail("MEDIA_SOURCE_CHANGED")
    if asset.result.get("job_id") != str(command.expected_result_job_id):
        fail("MEDIA_RESULT_CHANGED")
    read_blob(asset)
    asset.review = dict(
        at=stamp(datetime.now(UTC)),
        note=command.note,
        context_version=conv.context_version,
        source_fingerprint=asset.source_fingerprint,
        result_job_id=asset.result["job_id"],
        attachment_version=asset.version,
        sha256=asset.sha256,
    )
    return attachment_view(db, row, asset)


def evidence(db, row, identifier, attachment_version, context_version, result_job_id):
    """Read-only A/B/C handoff; consumers must revalidate before any promotion."""
    asset, _, _, conv = attachment_owned(db, row, identifier)
    view = attachment_view(db, row, asset)
    if asset.version != attachment_version or conv.context_version != context_version:
        fail("MEDIA_SOURCE_CHANGED")
    if view["result_job_id"] != result_job_id:
        fail("MEDIA_RESULT_CHANGED")
    if not view["result"] or not view["reviewed_at"]:
        fail("MEDIA_REVIEW_REQUIRED")
    read_blob(asset)
    return dict(
        schema_version="0.1.0",
        account_id=row.account_id,
        conversation_id=conv.id,
        snapshot_id=asset.snapshot_id,
        attachment_id=asset.id,
        attachment_version=asset.version,
        context_version=conv.context_version,
        result_job_id=view["result_job_id"],
        source_fingerprint=asset.source_fingerprint,
        sha256=asset.sha256,
        input_context=view["input_context"],
        result=view["result"],
        reviewed_at=view["reviewed_at"],
        review_note=view["review_note"],
        expires_at=stamp(asset.expires_at),
        business_confirmation_required=True,
    )


def run_once(
    factory=Session, *, make_client=controls.client_for, make_processor=media_processing.processor
):
    if not capabilities()["enabled"]:
        return False
    now = datetime.now(UTC)
    with factory.begin() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '3s'"))
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
        candidate = db.scalar(
            select(WahaMediaJob)
            .where(
                WahaMediaJob.active_key.is_not(None),
                or_(
                    WahaMediaJob.state.in_(["pending", "retry_wait"]),
                    and_(
                        WahaMediaJob.state == "running",
                        or_(WahaMediaJob.lease_until.is_(None), WahaMediaJob.lease_until <= now),
                    ),
                ),
                (WahaMediaJob.retry_at.is_(None)) | (WahaMediaJob.retry_at <= now),
            )
            .order_by(WahaMediaJob.created_at)
            .limit(1)
        )
        if not candidate:
            return False
        connection_id = candidate.connection_id
        from gigmate.db import WahaConnection

        connection = db.get(WahaConnection, connection_id)
        account = db.scalar(
            select(Account).where(Account.id == connection.account_id).with_for_update()
        )
        row = controls.owned(db, account, connection_id, lock=True)
        job = db.scalar(
            select(WahaMediaJob)
            .where(WahaMediaJob.id == candidate.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not job.active_key:
            return False
        if job.state == "result_unknown":
            return False
        if job.state == "running":
            if not job.lease_until or utc(job.lease_until) <= now:
                if job.stage != "download":
                    job.state, job.error_code = "result_unknown", "MEDIA_PROCESSING_INTERRUPTED"
                    job.lease_token, job.lease_until = None, None
                    return True
                job.state = "pending"
            else:
                return False
        if job.retry_at and utc(job.retry_at) > now:
            return False
        asset = db.get(WahaAttachment, job.attachment_id)
        try:
            if not account.active:
                fail("CONSENT_REVOKED", 403)
            snap, chat, conv = source(db, row, asset.snapshot_id)
            if (
                row.control_version != job.version
                or conv.context_version != job.context_version
                or job.source_fingerprint != fingerprint(snap)
            ):
                fail("MEDIA_SOURCE_CHANGED")
            if job.attempts >= 3:
                fail("MEDIA_RETRY_EXHAUSTED")
            root()
        except BusinessError as error:
            job.state, job.active_key, job.error_code = "cancelled", None, error.code
            job.updated_at = now
            return True
        token = str(uuid4())
        job.state, job.lease_token, job.lease_until = "running", token, now + timedelta(seconds=180)
        job.attempts += 1
        job.updated_at = now
        identifier, stage = job.id, job.stage
        caption, reference, peer, direction = (
            snap.data.get("text"),
            snap.provider_message_id,
            chat.provider_chat_id,
            snap.data["direction"],
        )
        expected_mime = base_mime(snap.data["mimetype"])
        asset_version, context_version, account_id, conversation_id = (
            asset.version,
            conv.context_version,
            account.id,
            conv.id,
        )
        source_id, source_fp = snap.id, job.source_fingerprint
        source_occurred_at = stamp(snap.occurred_at)
        input_context = job.input_context or {}
        try:
            cached_key = None
            content = None
            if asset.blob_key:
                try:
                    content = read_blob(asset)
                    cached_key = asset.blob_key
                except BusinessError:
                    if stage != "download":
                        raise
            client = make_client(row) if stage == "download" and not cached_key else None
            mime, digest = asset.mimetype, asset.sha256
        except (BusinessError, AdapterError) as error:
            job.state, job.active_key, job.error_code = "failed", None, error.code
            job.lease_token, job.lease_until = None, None
            return True
    # Provider/model I/O occurs after lease commit, never under business locks.
    output, key, error, unknown = None, None, None, False
    try:
        if stage == "download":
            if client:
                content, mime = client.attachment_bytes(
                    peer, reference, direction, max_bytes=MAX_BYTES
                )
            mime = base_mime(mime)
            if mime != expected_mime:
                raise AdapterError("MEDIA_TYPE_MISMATCH")
            validate_bytes(content, mime)
            digest = hashlib.sha256(content).hexdigest()
            if not cached_key:
                key = uuid4().hex + ".blob"
                target = blob_path(key)
                with target.open("xb") as file:
                    file.write(content)
                try:
                    target.chmod(0o600)
                except OSError:
                    pass  # Windows ACLs/private volume remain the host boundary.
        else:
            model = make_processor()
            request = media_processing.MediaInput(
                identifier,
                account_id,
                conversation_id,
                source_id,
                job.attachment_id,
                asset_version,
                context_version,
                source_fp,
                digest,
                mime,
                source_occurred_at,
                content,
                caption,
                message_sent_at=input_context.get("message_sent_at"),
                timezone=input_context.get("timezone"),
                timezone_source=input_context.get("timezone_source", "unknown"),
                source_observed_at=input_context.get("source_observed_at"),
            )
            if stage == "reconciling":
                lookup = getattr(model, "reconcile", None)
                if not callable(lookup):
                    raise media_processing.ProcessingUncertain
                raw_result = lookup(identifier)
                if raw_result is None:
                    raise media_processing.ProcessingUncertain
            else:
                raw_result = model.process(request)
            output = WahaMediaResult.model_validate(
                raw_result.model_dump(mode="json")
                if isinstance(raw_result, WahaMediaResult)
                else raw_result
            ).model_dump(mode="json")
    except media_processing.ProcessingUnavailable:
        error = "MEDIA_PROCESSOR_NOT_CONFIGURED"
        unknown = stage == "reconciling"
    except media_processing.ProcessingUncertain:
        error, unknown = "MEDIA_PROCESSING_RESULT_UNKNOWN", True
    except (AdapterError, BusinessError) as exc:
        error = exc.code if stage == "download" else "MEDIA_PROCESSOR_REJECTED"
        unknown = stage == "reconciling"
    except ValidationError:
        error = "MEDIA_PROCESSOR_INVALID_RESULT"
        unknown = stage == "reconciling"
    except Exception:
        error, unknown = (
            ("MEDIA_DOWNLOAD_FAILED", False)
            if stage == "download"
            else ("MEDIA_PROCESSING_RESULT_UNKNOWN", True)
        )
    finally:
        if client:
            client.close()
    keep = False
    try:
        with factory.begin() as db:
            account = db.scalar(select(Account).where(Account.id == account_id).with_for_update())
            row = controls.owned(db, account, connection_id, lock=True)
            job = db.get(WahaMediaJob, identifier)
            asset = db.get(WahaAttachment, job.attachment_id)
            if job.state != "running" or job.lease_token != token:
                return True
            try:
                if not account.active:
                    fail("CONSENT_REVOKED", 403)
                snap, _, conv = source(db, row, asset.snapshot_id)
                if (
                    row.control_version != job.version
                    or conv.context_version != job.context_version
                    or fingerprint(snap) != job.source_fingerprint
                    or asset.version != asset_version
                ):
                    fail("MEDIA_SOURCE_CHANGED")
            except BusinessError as exc:
                error, unknown = exc.code, False
                job.state = "cancelled"
            if error:
                job.error_code = error
                if job.state != "cancelled":
                    if unknown:
                        job.state = "result_unknown"
                    elif (
                        stage == "download"
                        and job.attempts < 3
                        and error
                        in {
                            "WAHA_UNAVAILABLE",
                            "WAHA_NOT_CONNECTED",
                            "MEDIA_DOWNLOAD_FAILED",
                            "WAHA_MEDIA_UNAVAILABLE",
                        }
                    ):
                        job.state, job.retry_at = (
                            "retry_wait",
                            datetime.now(UTC) + timedelta(seconds=2**job.attempts),
                        )
                    else:
                        job.state = "failed"
            elif stage == "download":
                changed_bytes = asset.sha256 is not None and asset.sha256 != digest
                if changed_bytes:
                    asset.version += 1
                asset.blob_key, asset.sha256, asset.mimetype, asset.size_bytes = (
                    key or cached_key,
                    digest,
                    mime,
                    len(content),
                )
                if not asset.result or changed_bytes:
                    asset.state, asset.result, asset.review = "downloaded", None, None
                if job.command["process"]:
                    job.stage, job.state, job.attempts = "processing", "pending", 0
                else:
                    job.state = "succeeded"
            else:
                asset.result, asset.review, asset.state = (
                    {
                        "payload": output,
                        "context_version": job.context_version,
                        "source_fingerprint": job.source_fingerprint,
                        "job_id": job.id,
                        "input_context": job.input_context,
                    },
                    None,
                    "processed",
                )
                job.state = "succeeded"
            if job.state in {"succeeded", "failed", "cancelled"}:
                job.active_key = None
            job.lease_token, job.lease_until, job.updated_at = None, None, datetime.now(UTC)
        keep = key is not None and error is None
    except SQLAlchemyError:
        # A lost commit acknowledgement may already reference this blob. Preserve
        # it; bounded orphan cleanup checks database references before deletion.
        keep = True
        raise
    finally:
        if key and not keep:
            blob_path(key).unlink(missing_ok=True)
    return True


def purge(factory=Session):
    """Expire derivative content; remove only owned blobs and old orphan staging files."""
    if not capabilities()["enabled"]:
        return
    now = datetime.now(UTC)
    removed = []
    with factory.begin() as db:
        for asset in db.scalars(select(WahaAttachment).where(WahaAttachment.expires_at <= now)):
            if asset.blob_key:
                removed.append(asset.blob_key)
            asset.blob_key, asset.result, asset.review = None, None, None
            asset.sha256, asset.mimetype, asset.size_bytes, asset.state = (
                None,
                None,
                None,
                "expired",
            )
            for job in db.scalars(select(WahaMediaJob).where(WahaMediaJob.active_key == asset.id)):
                job.state, job.active_key, job.lease_token = "cancelled", None, None
                job.error_code = "MEDIA_SOURCE_EXPIRED"
        live = set(
            db.scalars(select(WahaAttachment.blob_key).where(WahaAttachment.blob_key.is_not(None)))
        )
    for key in removed:
        blob_path(key).unlink(missing_ok=True)
    for file in root().glob("*.blob"):
        if re.fullmatch(r"[a-f0-9]{32}\.blob", file.name) and file.name not in live:
            if datetime.fromtimestamp(file.stat().st_mtime, UTC) < now - timedelta(hours=1):
                blob_path(file.name).unlink(missing_ok=True)
