"""Synthetic attachment storage, authorization, source/version, leases and B seam."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from test_waha_controls import path
from test_waha_ingress import post, raw
from test_waha_sync import ingress as ingress_fixture
from test_waha_sync import setup as setup_fixture

from gigmate import media_processing
from gigmate import waha_media as media
from gigmate.contracts import WahaMediaResult
from gigmate.db import ConversationRow, Job, WahaAttachment, WahaMediaJob, WahaSnapshot
from gigmate.waha_adapter import AdapterError
from gigmate.waha_client import LocalWahaClient, LocalWahaConfig

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aA4sAAAAASUVORK5CYII="
)


@pytest.fixture
def ingress(signed_in, monkeypatch):
    return ingress_fixture.__wrapped__(signed_in, monkeypatch)


@pytest.fixture
def setup(ingress, monkeypatch, tmp_path):
    value = setup_fixture.__wrapped__(ingress, monkeypatch)
    monkeypatch.setenv("WAHA_MEDIA_ENABLED", "true")
    monkeypatch.setenv("WAHA_MEDIA_ROOT", str(tmp_path / "private-media"))
    monkeypatch.delenv("GIGMATE_MEDIA_PROCESSOR_FACTORY", raising=False)
    event = raw(event_id="synthetic:picture")
    event["payload"].update(
        id="false_synthetic:peer@lid_MEDIA10",
        hasMedia=True,
        body="Synthetic caption",
        media={"mimetype": "image/png", "filename": "synthetic.png"},
    )
    assert post(ingress, event).status_code == 200
    return value


def body(s, **extra):
    with s[1]() as db:
        snap = db.scalar(select(WahaSnapshot))
        identifier = snap.id
    return {
        "expected_version": 0,
        "snapshot_id": identifier,
        "consent_download": True,
        "process": False,
        "consent_model": False,
        **extra,
    }


def enqueue(s, value=None, key="media-1"):
    return s[0].post(
        path(s, "media/jobs"), json=value or body(s), headers={**s[2], "Idempotency-Key": key}
    )


class Provider:
    def __init__(self, content=PNG, mime="image/png", callback=None):
        self.content, self.mime, self.callback, self.calls = content, mime, callback, 0

    def attachment_bytes(self, peer, reference, direction, *, max_bytes):
        assert peer == "synthetic:peer@lid" and reference == "false_synthetic:peer@lid_MEDIA10"
        assert direction == "incoming" and max_bytes == media.MAX_BYTES
        self.calls += 1
        if self.callback:
            self.callback()
        return self.content, self.mime

    def close(self):
        pass


def result():
    return WahaMediaResult(
        provider="synthetic-test-only",
        model_version="fixture-1",
        prompt_version="fixture-1",
        segments=[{"text": "Synthetic OCR text", "page": None, "start_ms": None, "end_ms": None}],
        summary="Synthetic summary",
        suggestions=[
            {"field": "requirements", "text": "Synthetic requirement", "source_indices": [0]}
        ],
    )


class Processor:
    calls = 0

    def process(self, request):
        assert request.origin == "live" and request.content == PNG
        assert request.sha256 == hashlib.sha256(PNG).hexdigest()
        assert not hasattr(request, "api_key") and not hasattr(request, "provider_url")
        self.calls += 1
        return result()

    def reconcile(self, request_id):
        return result()


def work(s, provider=None, processor=None):
    return media.run_once(
        s[1],
        make_client=lambda row: provider or Provider(),
        make_processor=(lambda: processor) if processor else media_processing.processor,
    )


def asset(s):
    with s[1]() as db:
        return db.scalar(select(WahaAttachment))


def test_download_owned_private_preview_and_idempotent_receipt(setup):
    cmd = body(setup)
    first = enqueue(setup, cmd)
    assert first.status_code == 202
    assert enqueue(setup, cmd).json()["data"]["id"] == first.json()["data"]["id"]
    assert enqueue(setup, {**cmd, "process": True, "consent_model": True}).status_code == 409
    assert work(setup)
    a = asset(setup)
    url = path(setup, f"media/attachments/{a.id}/content")
    response = setup[0].get(url)
    assert response.status_code == 200 and response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]
    view = setup[0].get(path(setup, f"media/attachments/{a.id}")).json()["data"]
    assert view["preview_available"] and view["sha256"] == hashlib.sha256(PNG).hexdigest()
    assert a.blob_key not in str(view) and "synthetic:peer" not in str(view)
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.scalar(select(WahaMediaJob)).state == "succeeded"


def test_a_b_processing_handoff_and_review_never_confirm_business(setup):
    enqueue(setup, body(setup, process=True, consent_model=True))
    processor = Processor()
    assert work(setup, processor=processor) and work(setup, processor=processor)
    a = asset(setup)
    view = setup[0].get(path(setup, f"media/attachments/{a.id}")).json()["data"]
    assert view["state"] == "processed" and processor.calls == 1
    review = {
        "expected_attachment_version": a.version,
        "expected_context_version": view["context_version"],
        "expected_result_job_id": view["result_job_id"],
        "reviewed": True,
        "note": "Synthetic merchant checked source",
    }
    r = setup[0].post(
        path(setup, f"media/attachments/{a.id}/review"), json=review, headers=setup[2]
    )
    assert r.status_code == 200 and r.json()["data"]["reviewed_at"]
    assert (
        setup[0]
        .post(
            path(setup, f"media/attachments/{a.id}/review"),
            json={**review, "expected_context_version": 0},
            headers=setup[2],
        )
        .status_code
        == 409
    )
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0


def test_unconfigured_b_keeps_download_and_reports_clear_failure(setup):
    job = enqueue(setup, body(setup, process=True, consent_model=True)).json()["data"]["id"]
    assert work(setup) and work(setup)
    data = setup[0].get(path(setup, f"media/jobs/{job}")).json()["data"]
    assert data["state"] == "failed" and data["error_code"] == "MEDIA_PROCESSOR_NOT_CONFIGURED"
    assert (
        setup[0].get(path(setup, f"media/attachments/{asset(setup).id}/content")).status_code == 200
    )


@pytest.mark.parametrize("consent", [False, 1, "true"])
def test_consent_must_be_explicit_boolean(setup, consent):
    assert enqueue(setup, body(setup, consent_download=consent)).status_code == 422
    assert enqueue(setup, body(setup, process=True)).status_code == 422


def test_csrf_owner_and_foreign_source_guards(setup):
    assert (
        setup[0]
        .post(path(setup, "media/jobs"), json=body(setup), headers={"Idempotency-Key": "x"})
        .status_code
        == 403
    )
    assert enqueue(setup, body(setup, snapshot_id=str(uuid4()))).status_code == 404
    setup[0].post(
        "/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"}
    )
    assert setup[0].get(path(setup, "media/capabilities")).status_code == 404


@pytest.mark.parametrize("operation", ["pause", "caption", "revoke", "cancel"])
def test_inflight_download_suppressed_and_staging_removed(setup, operation):
    job = enqueue(setup).json()["data"]["id"]

    def mutate():
        if operation == "pause":
            assert (
                setup[0]
                .post(path(setup, "pause"), json={"expected_version": 0}, headers=setup[2])
                .status_code
                == 200
            )
        elif operation == "cancel":
            assert (
                setup[0]
                .post(
                    path(setup, f"media/jobs/{job}/cancel"),
                    json={"expected_version": 0},
                    headers=setup[2],
                )
                .status_code
                == 200
            )
        else:
            with setup[1].begin() as db:
                snap = db.scalar(select(WahaSnapshot))
                if operation == "revoke":
                    snap.revoked = True
                else:
                    snap.data = {**snap.data, "text": "Changed synthetic caption"}

    assert work(setup, Provider(callback=mutate))
    assert not asset(setup).blob_key and not list(media.root().glob("*.blob"))
    with setup[1]() as db:
        assert db.get(WahaMediaJob, job).state == "cancelled"


def test_cached_preview_denied_after_revoke_and_changed_source(setup):
    enqueue(setup)
    work(setup)
    a = asset(setup)
    with setup[1].begin() as db:
        snap = db.get(WahaSnapshot, a.snapshot_id)
        snap.data = {**snap.data, "text": "New caption"}
    assert setup[0].get(path(setup, f"media/attachments/{a.id}/content")).status_code == 409
    with setup[1].begin() as db:
        db.get(WahaSnapshot, a.snapshot_id).revoked = True
    assert setup[0].get(path(setup, f"media/attachments/{a.id}/content")).status_code == 409


def test_unknown_processing_requires_read_only_lookup_not_resubmission(setup):
    class Uncertain(Processor):
        def process(self, request):
            self.calls += 1
            raise media_processing.ProcessingUncertain

    model = Uncertain()
    job = enqueue(setup, body(setup, process=True, consent_model=True)).json()["data"]["id"]
    work(setup, processor=model)
    work(setup, processor=model)
    assert (
        setup[0].get(path(setup, f"media/jobs/{job}")).json()["data"]["state"] == "result_unknown"
    )
    assert not work(setup, processor=model)
    assert enqueue(setup, key="new-key").status_code == 409
    assert (
        setup[0]
        .post(
            path(setup, f"media/jobs/{job}/reconcile"),
            json={"expected_version": 0},
            headers=setup[2],
        )
        .status_code
        == 200
    )
    assert work(setup, processor=model) and model.calls == 1
    assert asset(setup).state == "processed"


def test_expired_model_lease_is_unknown_and_download_lease_is_reclaimed(setup):
    job = enqueue(setup).json()["data"]["id"]
    with setup[1].begin() as db:
        row = db.get(WahaMediaJob, job)
        row.state = "running"
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    assert work(setup)
    with setup[1].begin() as db:
        row = db.get(WahaMediaJob, job)
        row.state = "running"
        row.stage = "processing"
        row.active_key = row.attachment_id
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    assert work(setup)
    with setup[1]() as db:
        assert db.get(WahaMediaJob, job).state == "result_unknown"


def test_retention_scrubs_results_and_deletes_only_owned_blobs(setup):
    enqueue(setup)
    work(setup)
    a = asset(setup)
    unrelated = media.root() / "keep.txt"
    unrelated.write_text("Synthetic unrelated file")
    with setup[1].begin() as db:
        db.get(WahaAttachment, a.id).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    media.purge(setup[1])
    assert not media.blob_path(a.blob_key).exists() and unrelated.exists()
    assert asset(setup).state == "expired"


@pytest.mark.parametrize(
    "content,mime",
    [
        (b"OggSsynthetic", "audio/ogg"),
        (b"%PDF-1.7\nsynthetic", "application/pdf"),
        (b"Synthetic text", "text/plain"),
        (PNG, "image/png"),
    ],
)
def test_supported_format_detection(content, mime):
    assert media.validate_bytes(content, mime) == mime


def test_repeat_read_reuses_blob_and_reload_finds_durable_job(setup):
    provider = Provider()
    first = enqueue(setup).json()["data"]
    assert work(setup, provider)
    a = asset(setup)
    second = enqueue(setup, key="repeat-read").json()["data"]
    assert work(setup, provider)
    assert provider.calls == 1 and asset(setup).blob_key == a.blob_key
    view = setup[0].get(path(setup, f"media/attachments/{a.id}")).json()["data"]
    assert view["latest_job_id"] == second["id"] != first["id"]


def test_voice_mime_parameters_are_normalized_without_guessing_type(setup):
    with setup[1].begin() as db:
        snapshot = db.scalar(select(WahaSnapshot))
        snapshot.data = {**snapshot.data, "kind": "audio", "mimetype": "audio/ogg; codecs=opus"}
    assert enqueue(setup).status_code == 202
    assert work(setup, Provider(content=b"OggSsynthetic", mime="audio/ogg; codecs=opus"))
    assert asset(setup).mimetype == "audio/ogg"


def test_cached_file_processing_does_not_depend_on_provider_credentials(setup, monkeypatch):
    enqueue(setup)
    work(setup)
    from gigmate import waha_controls

    def missing_config(row):
        waha_controls.fail("WAHA_CONTROL_DISABLED", 503)

    monkeypatch.setattr(waha_controls, "settings", missing_config)
    assert (
        enqueue(
            setup, body(setup, process=True, consent_model=True), key="cached-process"
        ).status_code
        == 202
    )
    assert work(setup, processor=Processor())
    assert asset(setup).state == "processed"


def test_expired_attachment_cannot_be_reissued_without_a_new_source(setup):
    enqueue(setup)
    work(setup)
    a = asset(setup)
    with setup[1].begin() as db:
        db.get(WahaAttachment, a.id).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert enqueue(setup, key="expired-reissue").status_code == 409


def test_corrupt_cache_is_redownloaded_before_processing(setup):
    enqueue(setup)
    work(setup)
    a = asset(setup)
    media.blob_path(a.blob_key).write_bytes(b"synthetic-corrupt-cache")
    created = enqueue(
        setup, body(setup, process=True, consent_model=True), key="recover-corrupt-file"
    )
    assert created.status_code == 202 and created.json()["data"]["stage"] == "download"
    processor = Processor()
    assert work(setup, processor=processor)
    assert work(setup, processor=processor)
    assert processor.calls == 1 and media.read_blob(asset(setup)) == PNG


@pytest.mark.parametrize("enabled", [False, True])
def test_media_bookkeeping_does_not_require_new_tables_for_existing_pause(
    setup, monkeypatch, enabled
):
    monkeypatch.setenv("WAHA_MEDIA_ENABLED", "true" if enabled else "false")
    with setup[1]() as db:
        engine = db.bind
    WahaMediaJob.__table__.drop(engine)
    WahaAttachment.__table__.drop(engine)
    if not enabled:
        assert work(setup) is False
    assert (
        setup[0]
        .post(path(setup, "pause"), json={"expected_version": 0}, headers=setup[2])
        .status_code
        == 200
    )


def test_unrelated_context_change_hides_old_model_result_and_review(setup):
    enqueue(setup, body(setup, process=True, consent_model=True))
    work(setup)
    work(setup, processor=Processor())
    a = asset(setup)
    with setup[1].begin() as db:
        snap = db.get(WahaSnapshot, a.snapshot_id)
        from gigmate.db import WahaChat

        chat = db.get(WahaChat, snap.chat_id)
        db.get(ConversationRow, chat.conversation_id).context_version += 1
    view = setup[0].get(path(setup, f"media/attachments/{a.id}")).json()["data"]
    assert view["result"] is None and view["state"] == "stale"
    assert view["preview_available"] is True
    command = {
        "expected_attachment_version": a.version,
        "expected_context_version": view["context_version"],
        "expected_result_job_id": a.result["job_id"],
        "reviewed": True,
    }
    assert (
        setup[0]
        .post(path(setup, f"media/attachments/{a.id}/review"), json=command, headers=setup[2])
        .status_code
        == 409
    )


def test_stale_download_owner_cannot_publish_or_leave_staging(setup):
    job = enqueue(setup).json()["data"]["id"]

    def replace():
        with setup[1].begin() as db:
            db.get(WahaMediaJob, job).lease_token = "synthetic-new-owner"

    assert work(setup, Provider(callback=replace))
    assert not asset(setup).blob_key and not list(media.root().glob("*.blob"))


def test_review_binds_exact_result_even_when_file_and_context_are_unchanged(setup):
    enqueue(setup, body(setup, process=True, consent_model=True))
    work(setup)
    work(setup, processor=Processor())
    a = asset(setup)
    old = setup[0].get(path(setup, f"media/attachments/{a.id}")).json()["data"]
    cmd = {
        "expected_attachment_version": a.version,
        "expected_context_version": old["context_version"],
        "expected_result_job_id": old["result_job_id"],
        "reviewed": True,
    }
    enqueue(setup, body(setup, process=True, consent_model=True), key="reprocess-new-result")
    work(setup, processor=Processor())
    assert (
        setup[0]
        .post(path(setup, f"media/attachments/{a.id}/review"), json=cmd, headers=setup[2])
        .status_code
        == 409
    )
    current = setup[0].get(path(setup, f"media/attachments/{a.id}")).json()["data"]
    assert (
        current["version"] == old["version"]
        and current["context_version"] == old["context_version"]
    )
    assert current["result_job_id"] != old["result_job_id"]
    assert (
        setup[0]
        .post(
            path(setup, f"media/attachments/{a.id}/review"),
            json={**cmd, "expected_result_job_id": current["result_job_id"]},
            headers=setup[2],
        )
        .status_code
        == 200
    )


def test_postgres_two_media_workers_publish_one_blob(setup):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    with setup[1]() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("Requires PostgreSQL account/connection locks")
    enqueue(setup)
    entered, release = threading.Event(), threading.Event()

    def pause():
        entered.set()
        assert release.wait(10)

    provider = Provider(callback=pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(work, setup, provider)
        try:
            assert entered.wait(10)
            assert work(setup, provider) is False
        finally:
            release.set()
        assert first.result(timeout=10)
    assert provider.calls == 1 and len(list(media.root().glob("*.blob"))) == 1


@pytest.mark.parametrize(
    "content,mime",
    [
        (b"<script>synthetic</script>", "image/png"),
        (b"\x00binary", "text/plain"),
        (PNG, "application/pdf"),
    ],
)
def test_mismatch_and_binary_text_fail(content, mime):
    with pytest.raises(AdapterError):
        media.validate_bytes(content, mime)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.invalid/api/files/image.png",
        "http://localhost:3000/api/files/%2e%2e/config",
        "http://localhost:3000/api/files/image.png?x-api-key=bad",
    ],
)
def test_provider_url_never_becomes_arbitrary_fetch(url):
    def transport(request):
        if request.url.path == "/api/sessions/default":
            return httpx.Response(
                200, json={"name": "default", "status": "WORKING", "engine": {"engine": "WEBJS"}}
            )
        assert not request.url.path.startswith("/api/files/")
        return httpx.Response(
            200,
            json={
                "id": "synthetic:media",
                "fromMe": False,
                "from": "synthetic:peer@lid",
                "hasMedia": True,
                "media": {"url": url, "mimetype": "image/png"},
            },
        )

    config = LocalWahaConfig(
        "http://127.0.0.1:18700",
        "00000000-0000-4000-8000-000000000001",
        "default",
        "a" * 40,
        "b" * 40,
    )
    with pytest.raises(AdapterError, match="UNTRUSTED_MEDIA_LOCATION"):
        LocalWahaClient(config, transport=httpx.MockTransport(transport)).attachment_bytes(
            "synthetic:peer@lid", "synthetic:media", "incoming", max_bytes=100
        )
