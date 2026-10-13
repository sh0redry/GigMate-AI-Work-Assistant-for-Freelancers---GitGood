"""Owned multi-type sending: immutable approval, durable outbox, no blind resend."""

import base64
import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from gigmate import waha_controls as controls
from gigmate import waha_media as media
from gigmate.contracts import WahaSendPayload
from gigmate.db import (
    Account,
    ConversationOrder,
    ConversationRow,
    MessageRow,
    Session,
    WahaChat,
    WahaConnection,
    WahaSendAction,
    WahaSendPermission,
    WahaSendPolicy,
    WahaSendRequestFence,
    WahaSendUpload,
    WahaSnapshot,
    WorkOrderRow,
)
from gigmate.errors import BusinessError
from gigmate.waha_adapter import AdapterError
from gigmate.waha_recovery import stamp
from gigmate.waha_sync import utc

KINDS = list(WahaSendPayload.model_fields["kind"].annotation.__args__)
MAX_BYTES = 20 * 1024 * 1024
MAX_STORAGE = 100 * 1024 * 1024
DAY_LIMIT = 100
INTERVAL_SECONDS = 5
LEASE_SECONDS = 60
log = logging.getLogger("gigmate.waha_send")
FILE_TYPES = {
    "application/pdf": {".pdf"},
    "text/plain": {".txt"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {".pptx"},
}
EXTENSIONS = FILE_TYPES | {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "audio/ogg": {".ogg", ".opus"},
    "audio/mpeg": {".mp3"},
    "audio/wav": {".wav"},
    "audio/mp4": {".m4a"},
    "video/mp4": {".mp4"},
    "text/csv": {".csv"},
}


def fail(code, status=409):
    raise BusinessError(status, code, "Check send permission, exact content and task outcome")


def now():
    return datetime.now(UTC)


def enabled():
    if os.environ.get("WAHA_SEND_ENABLED") != "true":
        fail("WAHA_SEND_DISABLED", 503)


def capabilities():
    return dict(
        enabled=os.environ.get("WAHA_SEND_ENABLED") == "true",
        kinds=KINDS,
        max_upload_bytes=MAX_BYTES,
        automatic_mode="exact_preapproved_payload",
        real_agent_configured=False,
    )


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def permission_view(db, row):
    p = db.get(WahaSendPermission, row.id)
    return dict(
        version=p.version if p else 0,
        enabled=p.enabled if p else False,
        chat_ids=p.chat_ids if p else [],
        expires_at=stamp(p.expires_at) if p and p.expires_at else None,
    )


def chat_owned(db, row, identifier):
    chat = db.get(WahaChat, identifier)
    conv = db.get(ConversationRow, chat.conversation_id) if chat else None
    if not chat or chat.connection_id != row.id or not conv or conv.account_id != row.account_id:
        fail("NOT_FOUND", 404)
    if not conv.allowlisted:
        fail("CONVERSATION_NOT_ALLOWED", 403)
    # Broadcasts/channels are not implicit recipients of merchant sending authority.
    if not chat.provider_chat_id.endswith(("@c.us", "@lid", "@g.us")):
        fail("SEND_RECIPIENT_UNSUPPORTED", 422)
    return chat, conv


def set_permission(db, row, command):
    # Revocation works even if private provider configuration or feature flag is broken.
    p = db.get(WahaSendPermission, row.id)
    if command.expected_version != (p.version if p else 0):
        fail("SEND_PERMISSION_VERSION_CONFLICT")
    if command.enabled:
        enabled()
        if (
            not command.chat_ids
            or not command.expires_at
            or not now()
            < utc(datetime.fromisoformat(command.expires_at.replace("Z", "+00:00")))
            <= now() + timedelta(days=30)
        ):
            fail("SEND_PERMISSION_EXPIRY_REQUIRED", 422)
        for identifier in command.chat_ids:
            chat_owned(db, row, identifier)
    elif command.chat_ids:
        fail("SEND_REVOKE_REQUIRES_EMPTY_CHATS", 422)
    if not p:
        p = WahaSendPermission(connection_id=row.id, version=0)
        db.add(p)
    p.version += 1
    p.enabled, p.chat_ids = command.enabled, sorted(set(command.chat_ids))
    p.expires_at = (
        datetime.fromisoformat(command.expires_at.replace("Z", "+00:00"))
        if command.enabled
        else None
    )
    for action in db.scalars(
        select(WahaSendAction).where(
            WahaSendAction.connection_id == row.id,
            WahaSendAction.state.in_(["draft", "queued", "preparing"]),
        )
    ):
        action.state, action.error_code, action.dispatch_key = (
            "cancelled",
            "SEND_PERMISSION_CHANGED",
            None,
        )
        action.lease_token, action.lease_until = None, None
    db.flush()
    return permission_view(db, row)


def require_permission(db, row, chat, version):
    enabled()
    p = db.get(WahaSendPermission, row.id)
    if (
        not row.enabled
        or not p
        or not p.enabled
        or chat.id not in p.chat_ids
        or not p.expires_at
        or utc(p.expires_at) <= now()
    ):
        fail("SEND_NOT_AUTHORIZED", 403)
    if p.version != version:
        fail("SEND_PERMISSION_VERSION_CONFLICT")
    return p


def storage_path(key):
    if not re.fullmatch(r"[a-f0-9]{32}\.blob", key):
        fail("SEND_STORAGE_INVALID", 503)
    directory = media.root() / "outgoing"
    if directory.is_symlink():
        fail("SEND_STORAGE_INVALID", 503)
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / key
    if path.is_symlink() or path.resolve().parent != directory.resolve():
        fail("SEND_STORAGE_INVALID", 503)
    return path


def validate_upload(content, mime, filename):
    if (
        not 0 < len(content) <= MAX_BYTES
        or not filename
        or len(filename) > 128
        or re.search(r'[\x00-\x1f\x7f/\\"]', filename)
        or filename in {".", ".."}
    ):
        fail("SEND_UPLOAD_INVALID", 422)
    if mime not in EXTENSIONS or Path(filename).suffix.lower() not in EXTENSIONS[mime]:
        fail("SEND_UPLOAD_UNSUPPORTED", 422)
    if mime == "text/csv":
        try:
            media.validate_bytes(content, "text/plain")
        except AdapterError:
            fail("SEND_UPLOAD_INVALID", 422)
        return
    if mime in media.TYPES:
        try:
            media.validate_bytes(content, mime)
        except AdapterError:
            fail("SEND_UPLOAD_INVALID", 422)
    elif mime == "video/mp4":
        if len(content) < 12 or content[4:8] != b"ftyp":
            fail("SEND_UPLOAD_INVALID", 422)
    elif (
        mime in FILE_TYPES
        and Path(filename).suffix.lower() in FILE_TYPES[mime]
        and content.startswith(b"PK\x03\x04")
    ):
        pass  # Office is opaque delivery, never decompressed or executed here.
    else:
        fail("SEND_UPLOAD_UNSUPPORTED", 422)


def upload(db, row, content, mime, filename):
    # The route holds account/connection locks and reauthenticates after streaming.
    # Recheck chat authorization here before any durable bytes or row are written.
    upload_permission(db, row)
    mime = media.base_mime(mime)
    validate_upload(content, mime, filename)
    usage = (
        db.scalar(
            select(func.sum(WahaSendUpload.size_bytes)).where(
                WahaSendUpload.connection_id == row.id, WahaSendUpload.blob_key.is_not(None)
            )
        )
        or 0
    )
    if usage + len(content) > MAX_STORAGE:
        fail("SEND_STORAGE_LIMIT", 429)
    key = uuid4().hex + ".blob"
    target = storage_path(key)
    with target.open("xb") as f:
        f.write(content)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    asset = WahaSendUpload(
        id=str(uuid4()),
        connection_id=row.id,
        filename=filename,
        mimetype=mime,
        blob_key=key,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        created_at=now(),
        expires_at=now() + timedelta(hours=24),
    )
    db.add(asset)
    db.flush()
    return upload_view(asset)


def upload_permission(db, row):
    enabled()
    p = db.get(WahaSendPermission, row.id)
    if not row.enabled or not p or not p.enabled or not p.expires_at or utc(p.expires_at) <= now():
        fail("SEND_NOT_AUTHORIZED", 403)
    authorized = db.scalar(
        select(WahaChat.id)
        .join(ConversationRow, ConversationRow.id == WahaChat.conversation_id)
        .where(
            WahaChat.id.in_(p.chat_ids),
            WahaChat.connection_id == row.id,
            ConversationRow.account_id == row.account_id,
            ConversationRow.allowlisted.is_(True),
        )
        .limit(1)
    )
    if not authorized:
        fail("SEND_NOT_AUTHORIZED", 403)


def upload_view(asset):
    return {
        k: getattr(asset, k) for k in ("id", "filename", "mimetype", "size_bytes", "sha256")
    } | {"expires_at": stamp(asset.expires_at)}


def read_upload(db, row, identifier):
    asset = db.get(WahaSendUpload, identifier)
    if not asset or asset.connection_id != row.id:
        fail("NOT_FOUND", 404)
    if utc(asset.expires_at) <= now() or not asset.blob_key:
        fail("SEND_UPLOAD_EXPIRED")
    try:
        path = storage_path(asset.blob_key)
        if path.stat().st_size != asset.size_bytes or asset.size_bytes > MAX_BYTES:
            fail("SEND_UPLOAD_INTEGRITY_FAILED", 503)
        content = path.read_bytes()
    except OSError:
        fail("SEND_UPLOAD_UNAVAILABLE", 503)
    if hashlib.sha256(content).hexdigest() != asset.sha256:
        fail("SEND_UPLOAD_INTEGRITY_FAILED", 503)
    return asset, content


def bind_payload(db, row, chat, payload):
    binding = {"recipient": chat.provider_chat_id, "sources": {}}
    orders = db.scalars(
        select(WorkOrderRow)
        .join(ConversationOrder, ConversationOrder.work_order_id == WorkOrderRow.id)
        .where(ConversationOrder.conversation_id == chat.conversation_id)
    )
    versions = {}
    for order in orders:
        if order.account_id != row.account_id:
            fail("NOT_FOUND", 404)
        version = order.data.get("version") if isinstance(order.data, dict) else None
        if type(version) is not int or version < 1:
            fail("SEND_BUSINESS_CONTEXT_INVALID")
        versions[order.id] = version
    # No single-order guess. Pin every linked business version so C-only changes
    # cannot silently leave a generic/automatic approval current.
    binding["work_order_versions"] = versions
    if payload.upload_id:
        asset, _ = read_upload(db, row, payload.upload_id)
        expected = {
            "image": "image/",
            "audio": "audio/",
            "voice": "audio/ogg",
            "video": "video/mp4",
            "sticker": "image/webp",
        }.get(payload.kind)
        if expected and not (
            asset.mimetype == expected
            if "/" in expected and not expected.endswith("/")
            else asset.mimetype.startswith(expected)
        ):
            fail("SEND_UPLOAD_KIND_MISMATCH", 422)
        if payload.kind == "voice":
            _, content = read_upload(db, row, payload.upload_id)
            if b"OpusHead" not in content[:512]:
                fail("SEND_VOICE_OPUS_REQUIRED", 422)
        binding["upload_sha256"] = asset.sha256
        binding["upload_metadata"] = upload_view(asset)
    for field in ("reply_snapshot_id", "target_snapshot_id"):
        identifier = getattr(payload, field)
        if identifier:
            snapshot = db.get(WahaSnapshot, identifier)
            if not snapshot or snapshot.chat_id != chat.id or snapshot.revoked:
                fail("SEND_SOURCE_INVALID", 422)
            canonical = db.scalar(
                select(MessageRow)
                .where(
                    MessageRow.account_id == row.account_id,
                    MessageRow.conversation_id == chat.conversation_id,
                    MessageRow.provider_message_id == snapshot.provider_message_id,
                )
                .order_by(MessageRow.revision.desc())
                .limit(1)
            )
            if canonical and canonical.data["revoked"]:
                fail("SEND_SOURCE_INVALID", 422)
            binding["sources"][identifier] = {
                "fingerprint": media.fingerprint(snapshot),
                "provider_message_id": snapshot.provider_message_id,
                "canonical_revision": canonical.revision if canonical else None,
            }
    return binding


def policy_view(p):
    return dict(
        id=p.id,
        chat_id=p.chat_id,
        version=p.version,
        enabled=p.enabled,
        payload=p.payload,
        expires_at=stamp(p.expires_at),
        maximum_uses=p.maximum_uses,
        uses=p.uses,
        work_order_id=p.bindings.get("target_work_order_id"),
        work_order_version=p.bindings.get("target_work_order_version"),
    )


def create_policy(db, row, account, command):
    controls.version(row, command.expected_control_version)
    chat, _ = chat_owned(db, row, command.chat_id)
    require_permission(db, row, chat, command.expected_permission_version)
    expiry = datetime.fromisoformat(command.expires_at.replace("Z", "+00:00"))
    if not now() < expiry <= now() + timedelta(days=7):
        fail("SEND_POLICY_EXPIRY_INVALID", 422)
    bindings = bind_payload(db, row, chat, command.payload)
    if (
        command.work_order_id
        and bindings["work_order_versions"].get(command.work_order_id)
        != command.expected_work_order_version
    ):
        fail("SEND_WORK_ORDER_CHANGED")
    bindings["target_work_order_id"] = command.work_order_id
    bindings["target_work_order_version"] = command.expected_work_order_version
    p = WahaSendPolicy(
        id=str(uuid4()),
        connection_id=row.id,
        chat_id=chat.id,
        version=1,
        enabled=True,
        payload=command.payload.model_dump(mode="json"),
        bindings=bindings,
        permission_version=command.expected_permission_version,
        control_version=row.control_version,
        approved_by=account.id,
        expires_at=expiry,
        maximum_uses=command.maximum_uses,
        uses=0,
    )
    db.add(p)
    db.flush()
    return policy_view(p)


def policy_owned(db, row, identifier):
    p = db.get(WahaSendPolicy, identifier)
    if not p or p.connection_id != row.id:
        fail("NOT_FOUND", 404)
    return p


def validate_action(db, row, action):
    cmd = action.command
    chat, conv = chat_owned(db, row, action.chat_id)
    require_permission(db, row, chat, cmd["expected_permission_version"])
    controls.version(row, cmd["expected_control_version"])
    if utc(action.expires_at) <= now():
        fail("SEND_APPROVAL_EXPIRED")
    if conv.context_version != cmd["expected_context_version"]:
        fail("SEND_CONTEXT_CHANGED")
    current = bind_payload(db, row, chat, WahaSendPayload.model_validate(cmd["payload"]))
    current["target_work_order_id"] = cmd["work_order_id"]
    current["target_work_order_version"] = cmd["expected_work_order_version"]
    if cmd["policy_id"]:
        current["policy_version"] = policy_owned(db, row, cmd["policy_id"]).version
    if (
        current != action.bindings
        or digest([cmd, action.bindings, stamp(action.expires_at), action.revision])
        != action.snapshot_hash
    ):
        fail("SEND_SNAPSHOT_CHANGED")
    if cmd["work_order_id"]:
        order = db.get(WorkOrderRow, cmd["work_order_id"])
        link = db.get(ConversationOrder, (conv.id, cmd["work_order_id"]))
        if not order or order.account_id != row.account_id or not link:
            fail("NOT_FOUND", 404)
        if order.data["version"] != cmd["expected_work_order_version"]:
            fail("SEND_WORK_ORDER_CHANGED")
    if cmd["policy_id"]:
        p = policy_owned(db, row, cmd["policy_id"])
        if (
            not p.enabled
            or utc(p.expires_at) <= now()
            or p.version != action.bindings.get("policy_version")
        ):
            fail("SEND_POLICY_CHANGED")
        if (
            p.chat_id != chat.id
            or p.payload != cmd["payload"]
            or p.bindings != {k: v for k, v in action.bindings.items() if k != "policy_version"}
            or p.permission_version != cmd["expected_permission_version"]
            or p.control_version != row.control_version
        ):
            fail("SEND_POLICY_MISMATCH")
    return chat, conv


def create_draft(db, row, account, command, key):
    if not re.fullmatch(r"[A-Za-z0-9:_-]{1,128}", key):
        fail("INVALID_IDEMPOTENCY_KEY", 422)
    cmd = command.model_dump(mode="json")
    previous = db.scalar(
        select(WahaSendAction).where(
            WahaSendAction.connection_id == row.id, WahaSendAction.request_key == key
        )
    )
    if previous:
        if previous.command != cmd:
            fail("IDEMPOTENCY_CONFLICT")
        return action_view(previous)
    if db.get(WahaSendRequestFence, (row.id, key)):
        fail("SEND_REQUEST_CANCELLED")
    queued = db.scalar(
        select(func.count())
        .select_from(WahaSendAction)
        .where(
            WahaSendAction.connection_id == row.id,
            WahaSendAction.state.in_(["draft", "queued", "preparing", "dispatching"]),
        )
    )
    if queued >= 100:
        fail("SEND_QUEUE_LIMIT", 429)
    chat, _ = chat_owned(db, row, command.chat_id)
    bindings = bind_payload(db, row, chat, command.payload)
    bindings["target_work_order_id"] = command.work_order_id
    bindings["target_work_order_version"] = command.expected_work_order_version
    if command.policy_id:
        bindings["policy_version"] = policy_owned(db, row, command.policy_id).version
    action = WahaSendAction(
        id=str(uuid4()),
        connection_id=row.id,
        chat_id=chat.id,
        request_key=key,
        command=cmd,
        bindings=bindings,
        revision=1,
        state="draft",
        expires_at=now() + timedelta(minutes=15),
        created_at=now(),
        delivery_rank=0,
    )
    action.snapshot_hash = digest([cmd, bindings, stamp(action.expires_at), action.revision])
    validate_action(db, row, action)
    if command.mode == "agent_auto":
        p = policy_owned(db, row, command.policy_id)
        if p.uses >= p.maximum_uses:
            fail("SEND_POLICY_EXHAUSTED", 429)
        # Uses are reservations, never refunded for unknown outcomes or cancellations.
        p.uses += 1
        action.state, action.approved_by, action.approved_at = "queued", p.approved_by, now()
    db.add(action)
    db.flush()
    return action_view(action)


def action_owned(db, row, identifier):
    action = db.get(WahaSendAction, identifier)
    if not action or action.connection_id != row.id:
        fail("NOT_FOUND", 404)
    return action


def action_view(action):
    delivery = (
        "unknown"
        if action.state == "result_unknown"
        else {0: "not_submitted", 1: "accepted", 2: "sent", 3: "delivered", 4: "read"}.get(
            action.delivery_rank, "read"
        )
    )
    return dict(
        id=action.id,
        chat_id=action.chat_id,
        mode=action.command["mode"],
        revision=action.revision,
        state=action.state,
        delivery_status=delivery,
        payload=action.command["payload"],
        context_version=action.command["expected_context_version"],
        expires_at=stamp(action.expires_at),
        approved_at=stamp(action.approved_at) if action.approved_at else None,
        provider_message_id=action.provider_message_id,
        error_code=action.error_code,
        created_at=stamp(action.created_at),
        unknown_reviewed_at=(action.unknown_review or {}).get("at"),
        upload=action.bindings.get("upload_metadata"),
        work_order_id=action.command["work_order_id"],
        work_order_version=action.command["expected_work_order_version"],
        work_order_versions=action.bindings["work_order_versions"],
    )


def approve(db, row, account, identifier, revision):
    action = action_owned(db, row, identifier)
    if action.revision != revision:
        fail("SEND_REVISION_CHANGED")
    if action.state in {"queued", "preparing", "dispatching", "accepted", "result_unknown"}:
        return action_view(action)  # Never create another outbox entry on lost response.
    if action.state != "draft":
        fail("SEND_ACTION_NOT_APPROVABLE")
    validate_action(db, row, action)
    action.state, action.approved_by, action.approved_at = "queued", account.id, now()
    return action_view(action)


def cancel(db, row, identifier, revision):
    action = action_owned(db, row, identifier)
    if action.revision != revision:
        fail("SEND_REVISION_CHANGED")
    if action.state in {"dispatching", "accepted", "result_unknown"}:
        fail("SEND_ALREADY_DISPATCHED")
    action.state, action.error_code, action.dispatch_key = "cancelled", "USER_CANCELLED", None
    action.lease_token, action.lease_until = None, None
    return action_view(action)


def review_unknown(db, row, account, identifier, command):
    action = action_owned(db, row, identifier)
    if action.revision != command.expected_revision:
        fail("SEND_REVISION_CHANGED")
    if action.state != "result_unknown" or action.lease_token:
        fail("SEND_UNKNOWN_REVIEW_NOT_AVAILABLE")
    if not action.unknown_review:
        action.unknown_review = {
            "by": account.id,
            "at": stamp(now()),
            "note": command.note,
            "acknowledge_possible_delivery": True,
        }
    # This only releases later independent actions. It does not certify delivery,
    # refund a policy use or make this action executable again.
    action.dispatch_key = None
    return action_view(action)


def request_view(db, row, key):
    if not re.fullmatch(r"[A-Za-z0-9:_-]{1,128}", key):
        fail("INVALID_IDEMPOTENCY_KEY", 422)
    action = db.scalar(
        select(WahaSendAction).where(
            WahaSendAction.connection_id == row.id, WahaSendAction.request_key == key
        )
    )
    if action:
        return {"request_key": key, "state": "recorded", "action": action_view(action)}
    if db.get(WahaSendRequestFence, (row.id, key)):
        return {"request_key": key, "state": "cancelled", "action": None}
    fail("NOT_FOUND", 404)


def cancel_request(db, row, key):
    if not re.fullmatch(r"[A-Za-z0-9:_-]{1,128}", key):
        fail("INVALID_IDEMPOTENCY_KEY", 422)
    action = db.scalar(
        select(WahaSendAction).where(
            WahaSendAction.connection_id == row.id, WahaSendAction.request_key == key
        )
    )
    if action:
        if action.state in {"draft", "queued", "preparing", "failed", "cancelled"}:
            cancel(db, row, action.id, action.revision)
        return {"request_key": key, "state": "recorded", "action": action_view(action)}
    if not db.get(WahaSendRequestFence, (row.id, key)):
        db.add(WahaSendRequestFence(connection_id=row.id, request_key=key, cancelled_at=now()))
        db.flush()
    return {"request_key": key, "state": "cancelled", "action": None}


def provider_payload(db, row, action):
    p = WahaSendPayload.model_validate(action.command["payload"])
    body = {"session": row.session_id, "chatId": action.bindings["recipient"]}
    paths = {
        "text": "sendText",
        "image": "sendImage",
        "file": "sendFile",
        "audio": "sendFile",
        "voice": "sendVoice",
        "video": "sendVideo",
        "sticker": "sendSticker",
        "location": "sendLocation",
        "contact": "sendContactVcard",
        "poll": "sendPoll",
        "reaction": "reaction",
    }
    if p.kind == "text":
        body.update(text=p.text, linkPreview=False)
    if p.upload_id:
        asset, content = read_upload(db, row, p.upload_id)
        body["file"] = dict(
            mimetype=asset.mimetype,
            filename=asset.filename,
            data=base64.b64encode(content).decode(),
        )
        if p.caption is not None:
            body["caption"] = p.caption
        if p.kind in {"voice", "video"}:
            body["convert"] = False
    if p.reply_snapshot_id:
        body["reply_to"] = action.bindings["sources"][p.reply_snapshot_id]["provider_message_id"]
    if p.kind == "location":
        body.update(latitude=p.latitude, longitude=p.longitude, title=p.title)
    if p.kind == "contact":
        body["contacts"] = [dict(fullName=c.name, phoneNumber=c.phone) for c in p.contacts]
    if p.kind == "poll":
        body["poll"] = dict(name=p.title, options=p.options, multipleAnswers=p.multiple_answers)
    if p.kind == "reaction":
        body.update(
            messageId=action.bindings["sources"][p.target_snapshot_id]["provider_message_id"],
            reaction=p.reaction,
        )
    return "/api/" + paths[p.kind], body


def locks(db, connection_id, *, require_active=True):
    row = db.get(WahaConnection, connection_id)
    if not row:
        fail("NOT_FOUND", 404)
    account = db.scalar(select(Account).where(Account.id == row.account_id).with_for_update())
    row = db.scalar(
        select(WahaConnection)
        .where(WahaConnection.id == connection_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not account or (require_active and not account.active):
        fail("ACCOUNT_INACTIVE", 403)
    return row


def run_once(factory=Session, make_client=None):
    """GET preflight outside locks; commit dispatch fence before a single POST."""
    make_client = make_client or controls.client_for
    token = str(uuid4())
    with factory.begin() as db:
        candidates = list(
            db.scalars(
                select(WahaSendAction)
                .where(WahaSendAction.state.in_(["queued", "preparing", "dispatching"]))
                .order_by(WahaSendAction.created_at)
                .limit(100)
            )
        )
        action = None
        for candidate in candidates:
            row = locks(db, candidate.connection_id, require_active=False)
            candidate = db.get(WahaSendAction, candidate.id, populate_existing=True)
            if candidate.state in {"preparing", "dispatching"}:
                if candidate.lease_until and utc(candidate.lease_until) > now():
                    continue
                if candidate.state == "dispatching":
                    candidate.state, candidate.error_code = "result_unknown", "SEND_RESULT_UNKNOWN"
                    candidate.lease_token, candidate.lease_until = None, None
                    return True
                candidate.state, candidate.dispatch_key = "queued", None
            if candidate.state != "queued":
                continue
            if db.scalar(
                select(WahaSendAction.id).where(
                    WahaSendAction.dispatch_key == candidate.chat_id,
                    WahaSendAction.id != candidate.id,
                )
            ):
                continue
            recent = db.scalar(
                select(func.max(WahaSendAction.dispatched_at)).where(
                    WahaSendAction.connection_id == row.id
                )
            )
            if recent and (now() - utc(recent)).total_seconds() < INTERVAL_SECONDS:
                continue
            daily = db.scalar(
                select(func.count())
                .select_from(WahaSendAction)
                .where(
                    WahaSendAction.connection_id == row.id,
                    WahaSendAction.dispatched_at
                    >= now().replace(hour=0, minute=0, second=0, microsecond=0),
                )
            )
            if daily >= DAY_LIMIT:
                candidate.state, candidate.error_code = "cancelled", "SEND_DAILY_LIMIT"
                return True
            try:
                if not db.get(Account, row.account_id).active:
                    fail("ACCOUNT_INACTIVE", 403)
                if not candidate.approved_at or candidate.approved_by != row.account_id:
                    fail("SEND_APPROVAL_MISSING")
                validate_action(db, row, candidate)
                client = make_client(row)
            except (BusinessError, AdapterError) as error:
                candidate.state, candidate.error_code = "cancelled", error.code
                return True
            candidate.state, candidate.lease_token = "preparing", token
            candidate.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
            candidate.dispatch_key = candidate.chat_id
            identifier, connection_id = candidate.id, row.id
            needs_video = candidate.command["payload"]["kind"] == "video"
            action = candidate
            break
        if not action:
            return False
    # Provider version/engine/session are verified before irreversible submission.
    try:
        if client.send_status(connection_id, video=needs_video)["state"] != "WORKING":
            fail("SEND_PROVIDER_NOT_CONNECTED")
        with factory.begin() as db:
            row = locks(db, connection_id)
            action = db.get(WahaSendAction, identifier, populate_existing=True)
            if (
                action.state != "preparing"
                or action.lease_token != token
                or utc(action.lease_until) <= now()
            ):
                return True
            validate_action(db, row, action)
            # Different chats may have completed GET preflight concurrently. Enforce
            # connection-wide rate limits again while serializing the dispatch fence.
            recent = db.scalar(
                select(func.max(WahaSendAction.dispatched_at)).where(
                    WahaSendAction.connection_id == row.id
                )
            )
            if recent and (now() - utc(recent)).total_seconds() < INTERVAL_SECONDS:
                action.state, action.dispatch_key, action.lease_token, action.lease_until = (
                    "queued",
                    None,
                    None,
                    None,
                )
                return True
            daily = db.scalar(
                select(func.count())
                .select_from(WahaSendAction)
                .where(
                    WahaSendAction.connection_id == row.id,
                    WahaSendAction.dispatched_at
                    >= now().replace(hour=0, minute=0, second=0, microsecond=0),
                )
            )
            if daily >= DAY_LIMIT:
                fail("SEND_DAILY_LIMIT", 429)
            path, body = provider_payload(db, row, action)
            action.state, action.dispatched_at = "dispatching", now()
            action.dispatch_token = token
        # This durable fence defines dispatch start. Later input cannot undo external I/O.
        response = client.send_message(path, body)
        provider_id = response.get("id") if isinstance(response, dict) else None
        if isinstance(provider_id, dict):
            provider_id = provider_id.get("_serialized")
        is_reaction = body.get("messageId") is not None
        if is_reaction and not (
            response is True or isinstance(response, dict) and response.get("id")
        ):
            raise AdapterError("WAHA_RESULT_UNKNOWN")
        if not is_reaction and (
            not isinstance(provider_id, str)
            or not provider_id.startswith("true_" + body["chatId"] + "_")
            or len(provider_id) > 256
            or any(ord(char) < 32 for char in provider_id)
        ):
            raise AdapterError("WAHA_RESULT_UNKNOWN")
        outcome, error = "accepted", None
        if is_reaction:
            provider_id = None  # Reaction responses are not new-message identity proof.
    except (BusinessError, AdapterError) as exc:
        with factory() as db:
            dispatched = db.get(WahaSendAction, identifier).dispatched_at is not None
        outcome = "result_unknown" if dispatched else "failed"
        error = "SEND_RESULT_UNKNOWN" if dispatched else exc.code
        provider_id = None
    except Exception:
        # Any unexpected error after the fence may follow submission; never retry POST.
        with factory() as db:
            dispatched = db.get(WahaSendAction, identifier).dispatched_at is not None
        outcome, error, provider_id = (
            ("result_unknown" if dispatched else "failed"),
            "SEND_EXECUTION_FAILED",
            None,
        )
    finally:
        try:
            client.close()
        except Exception:
            log.error("send_client_close_failed code=CLOSE_FAILED")
    with factory.begin() as db:
        locks(db, connection_id, require_active=False)
        action = db.get(WahaSendAction, identifier, populate_existing=True)
        if action.lease_token != token and not (
            outcome == "accepted"
            and action.state == "result_unknown"
            and action.dispatch_token == token
        ):
            return True
        action.state, action.error_code, action.provider_message_id = outcome, error, provider_id
        action.delivery_rank = 1 if outcome == "accepted" else 0
        action.lease_until, action.lease_token = None, None
        if outcome != "result_unknown":
            action.dispatch_key = None
    return True


def observe_receipt(db, connection, raw):
    """Only exact returned provider IDs correlate a send; never infer by equal text."""
    if os.environ.get("WAHA_SEND_ENABLED") != "true":
        return
    p = raw.get("payload", {})
    identifier = p.get("id")
    if not isinstance(identifier, str):
        return
    action = db.scalar(
        select(WahaSendAction).where(
            WahaSendAction.connection_id == connection.id,
            WahaSendAction.provider_message_id == identifier,
        )
    )
    if not action or action.state not in {"accepted", "result_unknown"}:
        return
    rank = p.get("ack")
    if type(rank) is int and 0 <= rank <= 4:
        action.delivery_rank = max(action.delivery_rank, rank + 1)


def invalidate_context(db, conversation):
    if os.environ.get("WAHA_SEND_ENABLED") != "true":
        return
    chat = db.scalar(select(WahaChat).where(WahaChat.conversation_id == conversation.id))
    if not chat:
        return
    for action in db.scalars(
        select(WahaSendAction).where(
            WahaSendAction.chat_id == chat.id,
            WahaSendAction.state.in_(["draft", "queued", "preparing"]),
        )
    ):
        if action.command["expected_context_version"] != conversation.context_version:
            action.state, action.error_code, action.dispatch_key = (
                "cancelled",
                "SEND_CONTEXT_CHANGED",
                None,
            )
            action.lease_token, action.lease_until = None, None


def reconcile(db, row, identifier, revision):
    action = action_owned(db, row, identifier)
    if action.revision != revision:
        fail("SEND_REVISION_CHANGED")
    if action.state not in {"result_unknown", "accepted"}:
        return action_view(action)
    # WAHA does not provide a caller-owned send idempotency/lookup key. Without the
    # returned ID there is no safe automatic attribution. Keep it unknown and blocked.
    if not action.provider_message_id:
        if action.state == "result_unknown":
            action.error_code = "SEND_UNKNOWN_WITHOUT_PROVIDER_ID"
        return action_view(action)
    chat, _ = chat_owned(db, row, action.chat_id)
    client = controls.client_for(row)
    try:
        result = client.message_snapshot(chat.provider_chat_id, action.provider_message_id)
    except AdapterError:
        # A missing message is not proof of non-submission; retain the prior outcome.
        action.error_code = "SEND_LOOKUP_UNAVAILABLE"
        return action_view(action)
    finally:
        client.close()
    row = locks(db, row.id, require_active=False)
    action = db.get(WahaSendAction, identifier, populate_existing=True)
    chat_owned(db, row, action.chat_id)

    def serialized(value):
        return value.get("_serialized") if isinstance(value, dict) else value

    if (
        not isinstance(result, dict)
        or serialized(result.get("id")) != action.provider_message_id
        or result.get("fromMe") is not True
        or serialized(result.get("to")) != chat.provider_chat_id
    ):
        fail("SEND_RECEIPT_IDENTITY_MISMATCH", 422)
    rank = result.get("ack")
    if type(rank) is not int or not 0 <= rank <= 4:
        fail("SEND_RECEIPT_ACK_UNAVAILABLE", 422)
    action.state, action.dispatch_key, action.error_code = "accepted", None, None
    action.delivery_rank = max(action.delivery_rank, rank + 1)
    return action_view(action)


def purge(factory=Session):
    with factory.begin() as db:
        for asset in db.scalars(
            select(WahaSendUpload).where(
                WahaSendUpload.expires_at <= now(), WahaSendUpload.blob_key.is_not(None)
            )
        ):
            try:
                storage_path(asset.blob_key).unlink(missing_ok=True)
            except OSError:
                continue
            asset.blob_key = None
        for action in db.scalars(
            select(WahaSendAction).where(
                WahaSendAction.expires_at <= now(),
                WahaSendAction.state.in_(["draft", "queued", "preparing"]),
            )
        ):
            action.state, action.error_code, action.dispatch_key = (
                "cancelled",
                "SEND_APPROVAL_EXPIRED",
                None,
            )
            action.lease_token, action.lease_until = None, None
        if media.capabilities()["enabled"]:
            directory = media.root() / "outgoing"
            if directory.exists() and not directory.is_symlink():
                referenced = set(
                    db.scalars(
                        select(WahaSendUpload.blob_key).where(WahaSendUpload.blob_key.is_not(None))
                    )
                )
                for file in directory.iterdir():
                    if (
                        re.fullmatch(r"[a-f0-9]{32}\.blob", file.name)
                        and file.name not in referenced
                        and not file.is_symlink()
                        and file.is_file()
                        and file.stat().st_mtime < (now() - timedelta(hours=24)).timestamp()
                    ):
                        file.unlink(missing_ok=True)
