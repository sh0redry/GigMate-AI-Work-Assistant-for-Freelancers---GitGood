"""Synthetic original-time, immutable B input and reviewed C handoff regressions."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_waha_controls import path
from test_waha_ingress import post, raw
from test_waha_media import Processor, asset, body, enqueue, result, work
from test_waha_media import ingress as ingress_fixture
from test_waha_media import setup as setup_fixture

from gigmate.db import ConversationRow, WahaMediaJob, WahaSnapshot
from gigmate.waha_sync import message_time


@pytest.fixture
def ingress(signed_in, monkeypatch):
    return ingress_fixture.__wrapped__(signed_in, monkeypatch)


@pytest.fixture
def setup(ingress, monkeypatch, tmp_path):
    return setup_fixture.__wrapped__(ingress, monkeypatch, tmp_path)


@pytest.mark.parametrize(
    "value", [None, True, "1700000000", -1, 0, float("nan"), float("inf"), 1700000000000]
)
def test_invalid_or_ambiguous_message_time_stays_unknown(value):
    assert message_time(value) is None


def test_original_time_survives_edit_without_changing_receipt_identity(setup, ingress):
    event = raw(event_id="synthetic:timed-media")
    sent = datetime.now(UTC) - timedelta(minutes=5)
    event["payload"].update(
        id="false_synthetic:peer@lid_TIMED20",
        timestamp=sent.timestamp(),
        hasMedia=True,
        body="Synthetic original",
        media={"mimetype": "image/png"},
    )
    assert post(ingress, event).status_code == 200
    with setup[1]() as db:
        snap = db.scalar(
            select(WahaSnapshot).where(WahaSnapshot.provider_message_id.endswith("TIMED20"))
        )
        identifier = snap.id
        assert snap.message_sent_at.replace(tzinfo=UTC) == sent
    assert post(ingress, event).json()["data"]["duplicate"]
    edit = {
        **event,
        "id": "synthetic:timed-edit",
        "event": "message.edited",
        "timestamp": event["timestamp"] + 1000,
        "payload": {
            **event["payload"],
            "editedMessageId": "TIMED20",
            "body": "Synthetic edited",
            "timestamp": sent.timestamp() + 60,
        },
    }
    assert post(ingress, edit).status_code == 200
    with setup[1]() as db:
        assert db.get(WahaSnapshot, identifier).message_sent_at.replace(tzinfo=UTC) == sent


def test_processing_context_is_frozen_and_timezone_validated(setup):
    sent = datetime.now(UTC) - timedelta(minutes=1)
    with setup[1].begin() as db:
        db.scalar(select(WahaSnapshot)).message_sent_at = sent
    assert enqueue(setup, body(setup, timezone="not-a-zone")).status_code == 422
    command = body(setup, process=True, consent_model=True, timezone="Asia/Hong_Kong")
    assert enqueue(setup, command).status_code == 202
    assert enqueue(setup, {**command, "timezone": "UTC"}).status_code == 409
    with setup[1].begin() as db:
        job = db.scalar(select(WahaMediaJob))
        assert job.input_context["timezone_source"] == "merchant_choice"
        captured = job.input_context["message_sent_at"]
        db.scalar(select(WahaSnapshot)).message_sent_at = sent + timedelta(seconds=1)

    class Capture(Processor):
        def process(self, request):
            assert request.message_sent_at == captured
            assert request.timezone == "Asia/Hong_Kong"
            assert request.timezone_source == "merchant_choice"
            assert request.source_observed_at
            return result()

    assert work(setup) and work(setup, processor=Capture())
    view = setup[0].get(path(setup, f"media/attachments/{asset(setup).id}")).json()["data"]
    assert view["input_context"]["message_sent_at"] == captured


def processed(setup):
    assert enqueue(setup, body(setup, process=True, consent_model=True)).status_code == 202
    assert work(setup) and work(setup, processor=Processor())
    identifier = asset(setup).id
    view = setup[0].get(path(setup, f"media/attachments/{identifier}")).json()["data"]
    query = dict(
        expected_attachment_version=view["version"],
        expected_context_version=view["context_version"],
        expected_result_job_id=view["result_job_id"],
    )
    return identifier, view, query


def checked(setup, identifier, query):
    return setup[0].post(
        path(setup, f"media/attachments/{identifier}/review"),
        json={**query, "reviewed": True, "note": "Synthetic source review"},
        headers=setup[2],
    )


def test_evidence_requires_current_review_and_returns_no_execution_authority(setup):
    identifier, _, query = processed(setup)
    url = path(setup, f"media/attachments/{identifier}/evidence")
    assert setup[0].get(url, params=query).json()["error"]["code"] == "MEDIA_REVIEW_REQUIRED"
    assert checked(setup, identifier, query).status_code == 200
    response = setup[0].get(url, params=query)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    evidence = response.json()["data"]
    assert (
        evidence["schema_version"] == "0.1.0" and evidence["business_confirmation_required"] is True
    )
    assert evidence["result_job_id"] == query["expected_result_job_id"]
    assert evidence["input_context"]["timezone"] is None
    assert "work_order_id" not in evidence and "blob_key" not in evidence
    assert (
        setup[0].get(url, params={**query, "expected_result_job_id": str(uuid4())}).status_code
        == 409
    )
    with setup[1].begin() as db:
        db.get(ConversationRow, evidence["conversation_id"]).context_version += 1
    assert setup[0].get(url, params=query).status_code == 409


def test_corrupt_original_and_legacy_unbound_review_cannot_be_handed_off(setup):
    from gigmate.waha_media import blob_path

    identifier, _, query = processed(setup)
    assert checked(setup, identifier, query).status_code == 200
    url = path(setup, f"media/attachments/{identifier}/evidence")
    with setup[1].begin() as db:
        from gigmate.db import WahaAttachment

        original = db.get(WahaAttachment, identifier)
        saved = original.review
        original.review = {key: value for key, value in saved.items() if key != "result_job_id"}
    assert setup[0].get(url, params=query).status_code == 409
    assert checked(setup, identifier, query).status_code == 200
    blob_path(asset(setup).blob_key).write_bytes(b"Synthetic corrupt content")
    response = setup[0].get(url, params=query)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MEDIA_INTEGRITY_FAILED"


@pytest.mark.parametrize(
    "change", ["paused", "revoked", "expired", "replaced_result", "other_account"]
)
def test_handoff_revalidates_permissions_source_and_exact_result(setup, change):
    from gigmate.db import WahaAttachment, WahaConnection

    identifier, _, query = processed(setup)
    assert checked(setup, identifier, query).status_code == 200
    if change == "other_account":
        assert (
            setup[0]
            .post(
                "/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"}
            )
            .status_code
            == 200
        )
    else:
        with setup[1].begin() as db:
            original = db.get(WahaAttachment, identifier)
            if change == "paused":
                db.get(WahaConnection, original.connection_id).enabled = False
            elif change == "revoked":
                db.get(WahaSnapshot, original.snapshot_id).revoked = True
            elif change == "expired":
                original.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                original.result = {**original.result, "job_id": str(uuid4())}
    response = setup[0].get(path(setup, f"media/attachments/{identifier}/evidence"), params=query)
    assert response.status_code in {403, 404, 409}
    assert "segments" not in response.json()
