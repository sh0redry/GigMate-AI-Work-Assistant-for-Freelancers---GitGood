"""Synthetic real HTTP routes and outbox execution; no real external sends."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from test_waha_controls import setup as controls_setup
from test_waha_ingress import ingress as ingress_setup
from test_waha_ingress import post, raw
from test_waha_media import PNG

from gigmate import waha_send as sends
from gigmate.contracts import WahaSendPayload
from gigmate.db import (
    ConversationRow,
    Job,
    WahaChat,
    WahaConnection,
    WahaSendAction,
    WahaSendPermission,
    WahaSendPolicy,
    WahaSendUpload,
)
from gigmate.waha_adapter import AdapterError
from gigmate.waha_client import LocalWahaClient, LocalWahaConfig
from gigmate.worker import run_once as text_worker


@pytest.fixture
def ingress(signed_in, monkeypatch):
    return ingress_setup.__wrapped__(signed_in, monkeypatch)


@pytest.fixture
def setup(ingress, monkeypatch, tmp_path):
    value = controls_setup.__wrapped__(ingress, monkeypatch)
    monkeypatch.setenv("WAHA_SEND_ENABLED", "true")
    monkeypatch.setenv("WAHA_MEDIA_ENABLED", "true")
    monkeypatch.setenv("WAHA_MEDIA_ROOT", str(tmp_path / "media"))
    with value[1]() as db:
        chat = db.scalar(select(WahaChat))
        chat_id = chat.id
    assert (
        value[0]
        .post(
            base(value) + "/permission",
            json={
                "expected_version": 0,
                "enabled": True,
                "chat_ids": [chat_id],
                "expires_at": expiry(),
            },
            headers=value[2],
        )
        .status_code
        == 200
    )
    return value


def base(s):
    return f"/api/v1/connectors/{s[3].connection_id}/sending"


def upload_request(s, filename, mime, content):
    return s[0].post(
        base(s) + "/uploads",
        content=content,
        headers=s[2] | {"X-File-Name": quote(filename, safe=""), "X-File-Mimetype": mime},
    )


@pytest.mark.parametrize(
    "operation", ["chat", "pause", "permission", "pause-regrant", "permission-regrant"]
)
def test_upload_rechecks_authority_after_stream_without_persisting(setup, monkeypatch, operation):
    from starlette.requests import Request

    original = Request.stream
    changed = []

    async def interrupted(request):
        async for chunk in original(request):
            yield chunk
        if request.url.path.endswith("/sending/uploads"):
            with setup[1].begin() as db:
                row = db.get(WahaConnection, setup[3].connection_id)
                permission = db.get(WahaSendPermission, row.id)
                if operation == "chat":
                    chat = db.scalar(select(WahaChat))
                    db.get(ConversationRow, chat.conversation_id).allowlisted = False
                elif operation.startswith("pause"):
                    row.enabled = operation.endswith("regrant")
                    row.control_version += 2 if operation.endswith("regrant") else 1
                else:
                    permission.enabled = operation.endswith("regrant")
                    permission.version += 2 if operation.endswith("regrant") else 1
            changed.append(operation)

    monkeypatch.setattr(Request, "stream", interrupted)
    response = upload_request(setup, "synthetic.png", "image/png", PNG)
    assert changed == [operation]
    assert response.status_code == 403, response.text
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSendUpload)) == 0
    assert not list(sends.storage_path("0" * 32 + ".blob").parent.glob("*.blob"))


def expiry():
    return (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")


def command(s, **extra):
    with s[1]() as db:
        chat = db.scalar(select(WahaChat))
        conv = db.get(ConversationRow, chat.conversation_id)
        row = db.get(WahaConnection, s[3].connection_id)
        p = db.get(WahaSendPermission, row.id)
        result = dict(
            expected_control_version=row.control_version,
            expected_permission_version=p.version,
            chat_id=chat.id,
            expected_context_version=conv.context_version,
            mode="manual",
            payload={"kind": "text", "text": "Synthetic outbound"},
        )
    return result | extra


def draft(s, *, key="send-1", **extra):
    return s[0].post(
        base(s) + "/drafts", json=command(s, **extra), headers=s[2] | {"Idempotency-Key": key}
    )


def change(s, identifier, action="approve"):
    return s[0].post(
        base(s) + f"/actions/{identifier}/{action}", json={"expected_revision": 1}, headers=s[2]
    )


class Provider:
    def __init__(self):
        self.calls = []
        self.before_status = None
        self.before_send = None
        self.error = None

    def status(self):
        if self.before_status:
            self.before_status()
        return {"state": "WORKING", "connected": True}

    def send_status(self, connection_id, *, video=False):
        return self.status()

    def send_message(self, path, body):
        self.calls.append((path, body))
        if self.before_send:
            self.before_send()
        if self.error:
            raise self.error
        return {"id": "true_" + body["chatId"] + "_SYNTHETIC01"}

    def close(self):
        pass


def execute(s, provider):
    return sends.run_once(s[1], make_client=lambda row: provider)


def test_manual_draft_requires_exact_approval_and_only_one_send(setup):
    s = setup
    response = draft(s)
    assert response.status_code == 201
    action = response.json()["data"]
    assert action["state"] == "draft"
    provider = Provider()
    assert not execute(s, provider)
    assert change(s, action["id"]).json()["data"]["state"] == "queued"
    assert execute(s, provider)
    assert len(provider.calls) == 1
    assert not execute(s, provider)
    assert draft(s).json()["data"]["id"] == action["id"]
    assert change(s, action["id"]).json()["data"]["state"] == "accepted"
    assert draft(s, payload={"kind": "text", "text": "Changed"}).status_code == 409
    assert change(s, action["id"], "cancel").status_code == 409
    with s[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSendAction)) == 1


@pytest.mark.parametrize(
    "change_kind",
    ["context", "permission", "control", "expiry", "content", "approver", "allowlist"],
)
def test_dispatch_revalidates_all_bindings(setup, change_kind):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    assert change(s, identifier).status_code == 200
    with s[1].begin() as db:
        action = db.get(WahaSendAction, identifier)
        chat = db.get(WahaChat, action.chat_id)
        if change_kind == "context":
            db.get(ConversationRow, chat.conversation_id).context_version += 1
        elif change_kind == "permission":
            db.get(WahaSendPermission, s[3].connection_id).enabled = False
        elif change_kind == "control":
            db.get(WahaConnection, s[3].connection_id).control_version += 1
        elif change_kind == "expiry":
            action.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif change_kind == "content":
            action.command = action.command | {"payload": {"kind": "text", "text": "Tampered"}}
        elif change_kind == "approver":
            action.approved_by = None
        else:
            db.get(ConversationRow, chat.conversation_id).allowlisted = False
    provider = Provider()
    assert execute(s, provider)
    assert not provider.calls
    with s[1]() as db:
        assert db.get(WahaSendAction, identifier).state == "cancelled"


def test_input_during_preflight_cancels_and_echo_does_not_call_model(setup, ingress):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    change(s, identifier)
    provider = Provider()
    provider.before_status = lambda: post(ingress, raw(event_id="synthetic:invalidate"))
    assert execute(s, provider)
    assert not provider.calls
    # A fresh action is accepted; its API echo advances context but never invokes B.
    identifier = draft(s, key="send-2").json()["data"]["id"]
    change(s, identifier)
    provider.before_status = None
    assert execute(s, provider)
    event = raw(event_id="synthetic:echo")
    event["payload"].update(
        id="true_synthetic:peer@lid_SYNTHETIC01",
        fromMe=True,
        to="synthetic:peer@lid",
        body="Synthetic outbound",
    )
    event["payload"]["source"] = "api"
    echo_response = post(ingress, event)
    assert echo_response.status_code == 200, echo_response.text
    # Drain pending incoming job and echo; echo has its own stable terminal reason.
    assert text_worker(s[1])
    assert text_worker(s[1])
    with s[1]() as db:
        assert db.scalar(select(Job).where(Job.error_code == "API_SEND_ECHO"))
        assert db.get(WahaSendAction, identifier).state == "accepted"


def test_cancel_and_revocation_work_without_provider_configuration(setup, monkeypatch):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    change(s, identifier)
    monkeypatch.setenv("WAHA_SEND_ENABLED", "false")
    monkeypatch.delenv("WAHA_CONTROL_CONFIG", raising=False)
    response = s[0].post(
        base(s) + "/permission",
        json={"expected_version": 1, "enabled": False, "chat_ids": []},
        headers=s[2],
    )
    assert response.status_code == 200
    assert change(s, identifier, "cancel").status_code == 200
    assert s[0].get(base(s) + f"/actions/{identifier}").json()["data"]["state"] == "cancelled"


def test_timeout_and_crashed_dispatch_never_resubmit(setup):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    change(s, identifier)
    provider = Provider()
    provider.error = AdapterError("WAHA_RESULT_UNKNOWN")
    assert execute(s, provider)
    assert len(provider.calls) == 1
    assert (
        change(s, identifier, "reconcile").json()["data"]["error_code"]
        == "SEND_UNKNOWN_WITHOUT_PROVIDER_ID"
    )
    assert not execute(s, provider)
    with s[1].begin() as db:
        action = db.get(WahaSendAction, identifier)
        action.state = "dispatching"
        action.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    assert execute(s, provider)
    assert len(provider.calls) == 1


def test_policy_exact_payload_use_limit_and_revocation(setup):
    s = setup
    cmd = command(s)
    response = s[0].post(
        base(s) + "/policies",
        json={
            k: cmd[k]
            for k in (
                "expected_control_version",
                "expected_permission_version",
                "chat_id",
                "payload",
            )
        }
        | {"expires_at": expiry(), "maximum_uses": 1},
        headers=s[2],
    )
    assert response.status_code == 201
    policy = response.json()["data"]
    assert (
        draft(
            s,
            mode="agent_auto",
            policy_id=policy["id"],
            payload={"kind": "text", "text": "Unauthorized model output"},
        ).status_code
        == 409
    )
    action = draft(s, mode="agent_auto", policy_id=policy["id"]).json()["data"]
    assert action["state"] == "queued"
    assert draft(s, mode="agent_auto", policy_id=policy["id"]).json()["data"]["id"] == action["id"]
    assert draft(s, key="send-2", mode="agent_auto", policy_id=policy["id"]).status_code == 429
    assert (
        s[0]
        .post(
            base(s) + f"/policies/{policy['id']}/revoke",
            json={"expected_revision": 1},
            headers=s[2],
        )
        .status_code
        == 200
    )
    provider = Provider()
    assert execute(s, provider)
    assert not provider.calls
    with s[1]() as db:
        assert db.get(WahaSendPolicy, policy["id"]).uses == 1


def test_upload_private_integrity_preview_and_kind_binding(setup):
    s = setup
    response = upload_request(s, "synthetic.png", "image/png", PNG)
    assert response.status_code == 201
    upload = response.json()["data"]
    assert "blob" not in str(upload)
    content_url = base(s) + f"/uploads/{upload['id']}/content"
    assert s[0].get(content_url).content == PNG
    assert s[0].get(content_url).headers["cache-control"] == "no-store"
    assert draft(s, payload={"kind": "voice", "upload_id": upload["id"]}).status_code == 422
    action = draft(
        s, payload={"kind": "image", "upload_id": upload["id"], "caption": "Synthetic caption"}
    ).json()["data"]
    assert change(s, action["id"]).status_code == 200
    with s[1]() as db:
        key = db.get(WahaSendUpload, upload["id"]).blob_key
    sends.storage_path(key).write_bytes(b"corrupt")
    provider = Provider()
    assert execute(s, provider)
    assert not provider.calls
    assert upload_request(s, "synthetic.png", "image/png", b"not png").status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "text"},
        {"kind": "text", "text": " "},
        {"kind": "text", "text": "ok", "upload_id": str(uuid4())},
        {"kind": "location", "latitude": 91.0, "longitude": 0.0, "title": "test"},
        {"kind": "poll", "title": "test", "options": ["a", "a"], "multiple_answers": False},
        {"kind": "contact", "contacts": [{"name": "test", "phone": "123"}]},
        {"kind": "reaction", "reaction": "x"},
    ],
)
def test_payload_rejects_invalid_and_incompatible_fields(payload):
    with pytest.raises(ValueError):
        WahaSendPayload.model_validate(payload)


def test_csrf_ownership_and_permission_separate_from_reception(setup):
    s = setup
    assert (
        s[0]
        .post(base(s) + "/drafts", json=command(s), headers={"Idempotency-Key": "x"})
        .status_code
        == 403
    )
    foreign = base(s).replace(s[3].connection_id, str(uuid4()))
    assert s[0].get(foreign + "/actions").status_code == 404
    assert (
        s[0]
        .post(
            base(s) + "/permission",
            json={"expected_version": 1, "enabled": False, "chat_ids": []},
            headers=s[2],
        )
        .status_code
        == 200
    )
    assert draft(s).status_code == 403
    with s[1]() as db:
        assert db.get(WahaConnection, s[3].connection_id).enabled


def test_client_pinned_routes_put_reaction_and_no_url_or_retry():
    config = LocalWahaConfig(
        "http://localhost:18700",
        "00000000-0000-4000-8000-000000000001",
        "default",
        "a" * 40,
        "b" * 40,
    )
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) > 1:
            raise httpx.ReadTimeout("synthetic", request=request)
        return httpx.Response(200, json=True)

    client = LocalWahaClient(config, transport=httpx.MockTransport(handle))
    body = {
        "session": "default",
        "chatId": "synthetic:peer@lid",
        "messageId": "false_synthetic:peer@lid_X",
        "reaction": "",
    }
    assert client.send_message("/api/reaction", body) is True
    assert calls[0].method == "PUT"
    with pytest.raises(AdapterError):
        client.send_message(
            "/api/sendImage", body | {"file": {"url": "https://invalid.test/private"}}
        )
    with pytest.raises(AdapterError) as failure:
        client.send_message(
            "/api/sendText", {"session": "default", "chatId": "synthetic:peer@lid", "text": "test"}
        )
    assert failure.value.code == "WAHA_RESULT_UNKNOWN"
    assert len(calls) == 2
    client.close()


def test_real_payload_source_rejects_conflicts_and_incoming_api_claims():
    from gigmate.waha_adapter import event_source

    payload = {"fromMe": True, "source": "api"}
    assert event_source({"payload": payload}, payload) == "api"
    for raw_value, details in [
        ({"source": "app", "payload": payload}, payload),
        ({"payload": {"source": ["api"], "fromMe": True}}, {"source": ["api"], "fromMe": True}),
        ({"payload": {"source": "api", "fromMe": False}}, {"source": "api", "fromMe": False}),
    ]:
        with pytest.raises(AdapterError):
            event_source(raw_value, details)


def test_raw_sdk_id_object_is_canonicalized_and_empty_reaction_is_only_api_acceptance(setup):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    change(s, identifier)

    class RawProvider(Provider):
        def send_message(self, path, body):
            self.calls.append((path, body))
            return {
                "id": {
                    "_serialized": "true_" + body["chatId"] + "_RAW01",
                    "fromMe": True,
                    "remote": body["chatId"],
                }
            }

    p = RawProvider()
    assert execute(s, p)
    with s[1]() as db:
        assert db.get(WahaSendAction, identifier).provider_message_id.endswith("_RAW01")
    config = LocalWahaConfig(
        "http://localhost:18700",
        "00000000-0000-4000-8000-000000000001",
        "default",
        "a" * 40,
        "b" * 40,
    )
    c = LocalWahaClient(
        config, transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b""))
    )
    assert (
        c.send_message(
            "/api/reaction",
            {"session": "default", "messageId": "false_synthetic:peer@lid_A", "reaction": ""},
        )
        is True
    )
    with pytest.raises(AdapterError):
        c.send_message(
            "/api/sendText", {"session": "default", "chatId": "synthetic:peer@lid", "text": "test"}
        )
    c.close()


@pytest.mark.parametrize(
    "kind, extra, file",
    [
        ("text", {"text": "Synthetic https://example.invalid"}, None),
        ("image", {"caption": "Synthetic"}, ("synthetic.png", "image/png", PNG)),
        (
            "file",
            {},
            (
                "synthetic.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                b"PK\x03\x04synthetic",
            ),
        ),
        ("audio", {}, ("synthetic.mp3", "audio/mpeg", b"ID3synthetic")),
        ("voice", {}, ("synthetic.ogg", "audio/ogg", b"OggSsyntheticOpusHead")),
        ("video", {}, ("synthetic.mp4", "video/mp4", b"\x00\x00\x00\x18ftypmp42synthetic")),
        ("sticker", {}, ("synthetic.webp", "image/webp", b"RIFF\x14\x00\x00\x00WEBPsynthetic")),
        ("location", {"latitude": 0.0, "longitude": 0.0, "title": "Synthetic location"}, None),
        ("contact", {"contacts": [{"name": "Synthetic", "phone": "+12025550101"}]}, None),
        (
            "poll",
            {"title": "Synthetic poll", "options": ["A", "B"], "multiple_answers": False},
            None,
        ),
    ],
)
def test_all_send_kinds_map_to_exact_provider_request(setup, kind, extra, file):
    s = setup
    payload = {"kind": kind} | extra
    if file:
        filename, mime, content = file
        result = upload_request(s, filename, mime, content)
        assert result.status_code == 201, result.text
        payload["upload_id"] = result.json()["data"]["id"]
    identifier = draft(s, payload=payload).json()["data"]["id"]
    change(s, identifier)
    provider = Provider()
    assert execute(s, provider)
    path, body = provider.calls[0]
    assert path.endswith(
        {"audio": "sendFile"}.get(
            kind, "send" + kind.capitalize() if kind != "contact" else "sendContactVcard"
        )
    )
    assert body["chatId"] == "synthetic:peer@lid"
    if file:
        assert set(body["file"]) == {"data", "filename", "mimetype"}
    if kind == "poll":
        assert body["poll"]["multipleAnswers"] is False
    if kind == "location":
        assert body["latitude"] == 0.0


def test_unknown_review_releases_only_later_actions_without_certifying_delivery(setup):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    change(s, identifier)
    provider = Provider()
    provider.error = AdapterError("WAHA_RESULT_UNKNOWN")
    execute(s, provider)
    url = base(s) + f"/actions/{identifier}/review-unknown"
    cmd = {
        "expected_revision": 1,
        "acknowledge_possible_delivery": True,
        "note": "Synthetic phone review; no resend",
    }
    assert (
        s[0]
        .post(url, json=cmd | {"acknowledge_possible_delivery": False}, headers=s[2])
        .status_code
        == 422
    )
    result = s[0].post(url, json=cmd, headers=s[2]).json()["data"]
    assert result["state"] == "result_unknown"
    assert result["delivery_status"] == "unknown"
    assert result["unknown_reviewed_at"]
    with s[1]() as db:
        assert db.get(WahaSendAction, identifier).dispatch_key is None
    assert change(s, identifier).json()["data"]["state"] == "result_unknown"
    assert not execute(s, provider)
    assert len(provider.calls) == 1


def test_known_receipt_lookup_does_not_send_and_ignores_wrong_identity(setup, monkeypatch):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    change(s, identifier)
    provider = Provider()
    execute(s, provider)

    class Lookup:
        def message_snapshot(self, chat, reference):
            return {"id": reference, "fromMe": True, "to": chat, "ack": 3}

        def close(self):
            pass

    monkeypatch.setattr("gigmate.waha_controls.client_for", lambda row: Lookup())
    assert change(s, identifier, "reconcile").json()["data"]["delivery_status"] == "read"
    assert len(provider.calls) == 1

    class WrongLookup(Lookup):
        def message_snapshot(self, chat, reference):
            return {"id": "true_synthetic:other@lid_X", "fromMe": True, "to": chat, "ack": 3}

    monkeypatch.setattr("gigmate.waha_controls.client_for", lambda row: WrongLookup())
    assert change(s, identifier, "reconcile").status_code == 422


def test_purge_expires_files_and_preserves_unknown_identity(setup):
    s = setup
    result = upload_request(s, "synthetic.txt", "text/plain", b"Synthetic").json()["data"]
    with s[1].begin() as db:
        asset = db.get(WahaSendUpload, result["id"])
        key = asset.blob_key
        asset.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    path = sends.storage_path(key)
    sends.purge(s[1])
    assert not path.exists()
    with s[1]() as db:
        assert db.get(WahaSendUpload, result["id"]).blob_key is None


def test_purge_retries_expired_upload_after_unlink_failure(setup, monkeypatch):
    s = setup
    result = upload_request(s, "synthetic.txt", "text/plain", b"Synthetic").json()["data"]
    with s[1].begin() as db:
        asset = db.get(WahaSendUpload, result["id"])
        key = asset.blob_key
        asset.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    path = sends.storage_path(key)
    original_unlink = type(path).unlink

    def unavailable(file, *args, **kwargs):
        if file == path:
            raise OSError("Synthetic storage failure")
        return original_unlink(file, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(type(path), "unlink", unavailable)
        sends.purge(s[1])
    assert path.exists()
    with s[1]() as db:
        assert db.get(WahaSendUpload, result["id"]).blob_key == key
    response = s[0].get(base(s) + f"/uploads/{result['id']}/content")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SEND_UPLOAD_EXPIRED"
    sends.purge(s[1])
    assert not path.exists()
    with s[1]() as db:
        assert db.get(WahaSendUpload, result["id"]).blob_key is None


def test_purge_recovers_deleted_blob_after_database_rollback(setup):
    s = setup
    result = upload_request(s, "synthetic.txt", "text/plain", b"Synthetic").json()["data"]
    with s[1].begin() as db:
        asset = db.get(WahaSendUpload, result["id"])
        key = asset.blob_key
        asset.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    path = sends.storage_path(key)

    class FailedCommit:
        @contextmanager
        def begin(self):
            with s[1].begin() as db:
                yield db
                raise RuntimeError("Synthetic database commit failure")

    with pytest.raises(RuntimeError, match="Synthetic database commit failure"):
        sends.purge(FailedCommit())
    assert not path.exists()
    with s[1]() as db:
        assert db.get(WahaSendUpload, result["id"]).blob_key == key
    response = s[0].get(base(s) + f"/uploads/{result['id']}/content")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SEND_UPLOAD_EXPIRED"
    sends.purge(s[1])
    with s[1]() as db:
        assert db.get(WahaSendUpload, result["id"]).blob_key is None


def test_postgres_competing_workers_dispatch_once(setup):
    s = setup
    if s[1].kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks require TEST_DATABASE_URL")
    identifier = draft(s).json()["data"]["id"]
    change(s, identifier)
    provider = Provider()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute(s, provider), range(2)))
    assert results.count(True) == 1
    assert len(provider.calls) == 1


def test_revocation_after_dispatch_boundary_does_not_rewrite_sent_outcome(setup):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    change(s, identifier)
    provider = Provider()

    def revoke():
        assert change(s, identifier, "cancel").status_code == 409
        assert (
            s[0]
            .post(
                base(s) + "/permission",
                json={"expected_version": 1, "enabled": False, "chat_ids": []},
                headers=s[2],
            )
            .status_code
            == 200
        )

    provider.before_send = revoke
    assert execute(s, provider)
    assert s[0].get(base(s) + f"/actions/{identifier}").json()["data"]["state"] == "accepted"


def test_reaction_binds_existing_message_and_creates_no_new_identity(setup, ingress):
    from gigmate.db import WahaSnapshot

    s = setup
    assert post(ingress, raw()).status_code == 200
    with s[1]() as db:
        snapshot = db.scalar(select(WahaSnapshot))
        target = snapshot.id
    identifier = draft(
        s, payload={"kind": "reaction", "target_snapshot_id": target, "reaction": ""}
    ).json()["data"]["id"]
    change(s, identifier)
    provider = Provider()
    execute(s, provider)
    assert provider.calls[0][0] == "/api/reaction"
    assert provider.calls[0][1]["reaction"] == ""
    with s[1]() as db:
        assert db.get(WahaSendAction, identifier).provider_message_id is None


def test_structured_api_echo_without_text_is_observation_not_extraction(setup, ingress):
    from gigmate.db import WahaSnapshot

    s = setup
    identifier = draft(
        s, payload={"kind": "location", "latitude": 0.0, "longitude": 0.0, "title": "Synthetic"}
    ).json()["data"]["id"]
    change(s, identifier)
    execute(s, Provider())
    event = raw(event_id="synthetic:structured-echo")
    event["source"] = "api"
    event["payload"].update(
        id="true_synthetic:peer@lid_SYNTHETIC01",
        fromMe=True,
        to="synthetic:peer@lid",
        body=None,
        hasMedia=False,
    )
    response = post(ingress, event)
    assert response.status_code == 200, response.text
    assert post(ingress, event).json()["data"]["duplicate"]
    with s[1]() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.scalar(select(WahaSnapshot)).data["kind"] == "other"
        assert db.get(WahaSendAction, identifier).state == "accepted"


def test_sending_requires_exact_pinned_version_webhook_and_echo_tags():
    from gigmate.waha_client import ENGINE, VERSION

    connection = str(uuid4())
    config = LocalWahaConfig(
        "http://localhost:18700",
        "00000000-0000-4000-8000-000000000001",
        "default",
        "a" * 40,
        "b" * 40,
    )
    calls = []
    session = {
        "name": "default",
        "status": "WORKING",
        "engine": {"engine": ENGINE},
        "config": {
            "webjs": {"tagsEventsOn": True},
            "webhooks": [
                {
                    "url": f"http://ingress:8000/api/v1/connectors/waha/{connection}/events",
                    "hmac": {"key": config.webhook_secret},
                    "events": [
                        "session.status",
                        "message.any",
                        "message.edited",
                        "message.revoked",
                        "message.ack",
                    ],
                }
            ],
        },
    }
    version = {"version": VERSION, "engine": ENGINE}

    def handle(request):
        calls.append(request.method)
        return httpx.Response(
            200, json=version if request.url.path.endswith("/version") else session
        )

    client = LocalWahaClient(config, transport=httpx.MockTransport(handle))
    assert client.send_status(connection)["connected"]
    with pytest.raises(AdapterError) as error:
        client.send_status(connection, video=True)
    assert error.value.code == "WAHA_SEND_VIDEO_REQUIRES_CHROME"
    version["browser"] = "/usr/bin/google-chrome-stable"
    assert client.send_status(connection, video=True)["connected"]
    session["config"]["webjs"]["tagsEventsOn"] = False
    with pytest.raises(AdapterError) as error:
        client.send_status(connection)
    assert error.value.code == "WAHA_SEND_ECHO_TAGS_REQUIRED"
    version["version"] = "synthetic:wrong-version"
    with pytest.raises(AdapterError) as error:
        client.send_status(connection)
    assert error.value.code == "WAHA_SEND_VERSION_MISMATCH"
    assert set(calls) == {"GET"}
    client.close()


def test_late_original_receipt_survives_expired_dispatch_lease_without_a_second_post(setup):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    change(s, identifier)
    provider = Provider()
    other = Provider()

    def expire_and_recover():
        with s[1].begin() as db:
            db.get(WahaSendAction, identifier).lease_until = datetime.now(UTC) - timedelta(
                seconds=1
            )
        assert execute(s, other)
        assert not other.calls

    provider.before_send = expire_and_recover
    assert execute(s, provider)
    with s[1]() as db:
        action = db.get(WahaSendAction, identifier)
        assert action.state == "accepted"
        assert action.provider_message_id
    assert len(provider.calls) == 1


def test_auto_policy_cannot_change_merchant_approved_order_association(setup):
    from gigmate.db import ConversationOrder, WorkOrderRow

    s = setup
    with s[1].begin() as db:
        chat = db.scalar(select(WahaChat))
        order = db.scalar(select(WorkOrderRow))
        order_id, version = order.id, order.data["version"]
        db.add(ConversationOrder(conversation_id=chat.conversation_id, work_order_id=order_id))
    cmd = command(s)
    policy = (
        s[0]
        .post(
            base(s) + "/policies",
            json={
                k: cmd[k]
                for k in (
                    "expected_control_version",
                    "expected_permission_version",
                    "chat_id",
                    "payload",
                )
            }
            | {"expires_at": expiry(), "maximum_uses": 1},
            headers=s[2],
        )
        .json()["data"]
    )
    assert (
        draft(
            s,
            mode="agent_auto",
            policy_id=policy["id"],
            work_order_id=order_id,
            expected_work_order_version=version,
        ).status_code
        == 409
    )
    bound = (
        s[0]
        .post(
            base(s) + "/policies",
            json={
                k: cmd[k]
                for k in (
                    "expected_control_version",
                    "expected_permission_version",
                    "chat_id",
                    "payload",
                )
            }
            | {
                "expires_at": expiry(),
                "maximum_uses": 1,
                "work_order_id": order_id,
                "expected_work_order_version": version,
            },
            headers=s[2],
        )
        .json()["data"]
    )
    assert bound["work_order_id"] == order_id
    assert (
        draft(
            s,
            mode="agent_auto",
            policy_id=bound["id"],
            work_order_id=order_id,
            expected_work_order_version=version,
        ).json()["data"]["state"]
        == "queued"
    )


def test_c_only_work_order_change_invalidates_unbound_send(setup):
    from gigmate.db import ConversationOrder, WorkOrderRow

    s = setup
    with s[1].begin() as db:
        chat = db.scalar(select(WahaChat))
        order = db.scalar(select(WorkOrderRow))
        order_id = order.id
        db.add(ConversationOrder(conversation_id=chat.conversation_id, work_order_id=order_id))
    response = draft(s).json()["data"]
    assert response["work_order_versions"][order_id] >= 1
    change(s, response["id"])
    with s[1].begin() as db:
        order = db.get(WorkOrderRow, order_id)
        order.data = order.data | {"version": order.data["version"] + 1}
    provider = Provider()
    assert execute(s, provider)
    assert not provider.calls


def test_quote_rejects_canonical_revocation_even_if_old_snapshot_flag_is_not_set(setup, ingress):
    from gigmate.db import WahaSnapshot

    s = setup
    original = raw(event_id="synthetic:quote-source")
    assert post(ingress, original).status_code == 200
    with s[1]() as db:
        snapshot = db.scalar(select(WahaSnapshot))
        source_id = snapshot.id
    revoke = raw(
        "message.revoked", event_id="synthetic:quote-revoke", timestamp=original["timestamp"] + 1000
    )
    assert post(ingress, revoke).status_code == 200
    response = draft(
        s, payload={"kind": "text", "text": "Synthetic quote", "reply_snapshot_id": source_id}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "SEND_SOURCE_INVALID"


def test_upload_unicode_name_is_header_metadata_not_access_log_url(setup):
    response = upload_request(setup, "Synthetic-客户.png", "image/png", PNG)
    assert response.status_code == 201, response.text
    assert response.json()["data"]["filename"] == "Synthetic-客户.png"


def test_cancel_lost_creation_request_blocks_a_late_auto_submit(setup):
    s = setup
    url = base(s) + "/requests/send-late"
    assert s[0].get(url).status_code == 404
    assert s[0].post(url + "/cancel", json={}, headers=s[2]).json()["data"]["state"] == "cancelled"
    assert draft(s, key="send-late").json()["error"]["code"] == "SEND_REQUEST_CANCELLED"
    assert s[0].get(url).json()["data"]["action"] is None
    with s[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSendAction)) == 0


def test_request_lookup_recovers_original_record_and_cancel_is_configuration_free(
    setup, monkeypatch
):
    s = setup
    identifier = draft(s).json()["data"]["id"]
    url = base(s) + "/requests/send-1"
    assert s[0].get(url).json()["data"]["action"]["id"] == identifier
    monkeypatch.setenv("WAHA_SEND_ENABLED", "false")
    assert (
        s[0].post(url + "/cancel", json={}, headers=s[2]).json()["data"]["action"]["state"]
        == "cancelled"
    )
