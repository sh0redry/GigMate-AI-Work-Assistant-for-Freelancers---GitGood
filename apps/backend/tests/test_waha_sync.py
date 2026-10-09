"""Synchronization consent, snapshots, live provenance and durable read recovery."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_waha_controls import path
from test_waha_controls import setup as product_setup
from test_waha_ingress import ingress as ingress_fixture
from test_waha_ingress import post, raw

from gigmate import waha_sync as sync
from gigmate.db import (
    Account,
    ConversationRow,
    Inbox,
    Job,
    WahaChat,
    WahaConnection,
    WahaControl,
    WahaObservationReceipt,
    WahaSnapshot,
    WahaSourceGap,
    WahaSyncJob,
)
from gigmate.waha_adapter import AdapterError


@pytest.fixture
def ingress(signed_in, monkeypatch):
    return ingress_fixture.__wrapped__(signed_in, monkeypatch)


@pytest.fixture
def setup(ingress, monkeypatch):
    return product_setup.__wrapped__(ingress, monkeypatch)


def chat_id(s):
    with s[1]() as db:
        return db.scalar(select(WahaChat.id))


def payload(s, **changes):
    now = datetime.now(UTC) - timedelta(seconds=1)
    return {
        "expected_version": 0,
        "chat_ids": [chat_id(s)],
        "since": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "until": now.isoformat().replace("+00:00", "Z"),
        "consent": True,
        "max_records": 100,
        **changes,
    }


def enqueue(s, body=None, key="sync-1"):
    return s[0].post(
        path(s, "sync-jobs"), json=body or payload(s), headers={**s[2], "Idempotency-Key": key}
    )


def item(ref="synthetic:history", **changes):
    base = dict(
        id=ref,
        fromMe=False,
        hasMedia=False,
        body="Synthetic history text",
        timestamp=int(datetime.now(UTC).timestamp()) - 10,
        **{"from": "synthetic:peer@lid"},
    )
    return {**base, **changes}


class Provider:
    def __init__(self, items):
        self.items = items
        self.calls = []
        self.error = False
        self.on_read = None

    def history_page(self, peer, **params):
        self.calls.append(params)
        if self.on_read:
            self.on_read()
        if self.error:
            raise AdapterError("WAHA_UNAVAILABLE")
        return self.items if params["offset"] == 0 else []

    def message_snapshot(self, peer, reference):
        return self.items[0]

    def close(self):
        pass


def work(s, provider):
    return sync.run_once(s[1], make_client=lambda r: provider)


def test_bounded_sync_snapshots_never_create_business_jobs_and_repeat_deduplicates(setup):
    p = Provider([item()])
    command = payload(setup)
    response = enqueue(setup, command)
    assert response.status_code == 202
    assert enqueue(setup, command).json()["data"]["id"] == response.json()["data"]["id"]
    assert enqueue(setup, {**command, "max_records": 101}).status_code == 409
    assert work(setup, p) and work(setup, p)
    with setup[1]() as db:
        job = db.scalar(select(WahaSyncJob))
        assert job.state == "succeeded"
        assert job.progress["imported"] == 1 and job.progress["pages"] == 2
        assert db.scalar(select(func.count()).select_from(WahaSnapshot)) == 1
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.scalar(select(func.count()).select_from(Inbox)) == 0
    assert enqueue(setup, payload(setup), "sync-2").status_code == 202
    work(setup, p)
    work(setup, p)
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSnapshot)) == 1
    timeline = setup[0].get(path(setup, f"chats/{chat_id(setup)}/timeline")).json()["items"]
    assert timeline[0]["evidence"] == "snapshot" and timeline[0]["revision"] is None
    assert timeline[0]["origin"] == "history"


@pytest.mark.parametrize(
    "change,status",
    [
        ({"consent": False}, 422),
        ({"consent": "true"}, 422),
        ({"expected_version": 5}, 409),
        ({"chat_ids": [str(uuid4())]}, 404),
        ({"max_records": 1001}, 422),
        ({"since": "2000-01-01T00:00:00Z"}, 422),
        ({"until": "2099-01-01T00:00:00Z"}, 422),
    ],
)
def test_invalid_sync_has_no_partial_intent(setup, change, status):
    assert enqueue(setup, payload(setup, **change)).status_code == status
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSyncJob)) == 0


def test_sync_requires_csrf_and_owner(setup):
    assert (
        setup[0]
        .post(path(setup, "sync-jobs"), json=payload(setup), headers={"Idempotency-Key": "test"})
        .status_code
        == 403
    )
    setup[0].post(
        "/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"}
    )
    assert setup[0].get(path(setup, "sync-jobs")).status_code == 404
    assert setup[0].get(path(setup, f"chats/{chat_id(setup)}/timeline")).status_code == 404


@pytest.mark.parametrize("mode", ["pause", "revoke", "account", "cancel"])
def test_consent_change_during_network_read_suppresses_result(setup, mode):
    r = enqueue(setup)
    identifier = r.json()["data"]["id"]
    p = Provider([item()])

    def deny():
        with setup[1].begin() as db:
            row = db.get(WahaConnection, setup[3].connection_id)
            if mode == "pause":
                row.enabled = False
                row.control_version += 1
            if mode == "revoke":
                db.scalar(
                    select(ConversationRow).where(
                        ConversationRow.id.in_(select(WahaChat.conversation_id))
                    )
                ).allowlisted = False
                row.control_version += 1
            if mode == "account":
                db.get(Account, setup[3].account_id).active = False
            if mode == "cancel":
                sync.cancel(db, row, identifier)

    p.on_read = deny
    work(setup, p)
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSnapshot)) == 0
        assert db.get(WahaSyncJob, identifier).state == "cancelled"


def test_read_retry_budget_and_expired_lease_recovery(setup):
    enqueue(setup)
    p = Provider([item()])
    p.error = True
    for _ in range(3):
        work(setup, p)
        with setup[1].begin() as db:
            job = db.scalar(select(WahaSyncJob).where(WahaSyncJob.active_key.is_not(None)))
            if job:
                assert job.progress.get("retry_at")
                job.progress = {
                    **job.progress,
                    "retry_at": (datetime.now(UTC) - timedelta(seconds=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
    with setup[1]() as db:
        assert db.scalar(select(WahaSyncJob)).state == "failed"
    enqueue(setup, payload(setup), "new-explicit-read")
    with setup[1].begin() as db:
        j = db.scalar(select(WahaSyncJob).where(WahaSyncJob.active_key.is_not(None)))
        j.state = "running"
        j.attempts = 1
        j.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        j.lease_token = "old"
    p.error = False
    work(setup, p)
    work(setup, p)
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSnapshot)) == 1


def test_record_limit_and_foreign_chat_snapshot_are_explicit(setup):
    p = Provider([item(), item("synthetic:foreign", **{"from": "synthetic:other@lid"})])
    enqueue(setup, payload(setup, max_records=2))
    work(setup, p)
    with setup[1]() as db:
        j = db.scalar(select(WahaSyncJob))
        assert j.progress["skipped"] == 1
        assert j.state == "succeeded" and j.progress["coverage"] == "limit_reached"
        assert db.scalar(select(func.count()).select_from(WahaSnapshot)) == 1


def test_pause_window_is_never_imported_after_resume(setup):
    at = datetime.now(UTC) - timedelta(seconds=10)
    with setup[1].begin() as db:
        row = db.get(WahaConnection, setup[3].connection_id)
        sync.authorization_changed(db, row, None, True, at - timedelta(seconds=1))
        sync.authorization_changed(db, row, None, False, at + timedelta(seconds=1))
    enqueue(setup)
    p = Provider([item(timestamp=int(at.timestamp()))])
    work(setup, p)
    work(setup, p)
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSnapshot)) == 0
        assert db.scalar(select(WahaSyncJob)).progress["skipped"] == 1


def test_media_metadata_caption_dedup_no_file_url_or_extraction_job(ingress):
    e = raw()
    e["payload"].update(
        hasMedia=True,
        body="Synthetic caption",
        media={
            "mimetype": "image/png",
            "filename": "sample.png",
            "url": "http://untrusted/private",
        },
    )
    assert post(ingress, e).status_code == 200
    assert post(ingress, e).json()["data"]["duplicate"] is True
    with ingress[1]() as db:
        snap = db.scalar(select(WahaSnapshot))
        assert snap.data["kind"] == "image"
        assert snap.data["text"] == "Synthetic caption"
        assert "url" not in snap.data and "untrusted" not in str(snap.data)
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.scalar(select(func.count()).select_from(WahaObservationReceipt)) == 1
    e["payload"]["body"] = "Changed caption on same event"
    assert post(ingress, e).status_code == 409


def test_group_sender_reply_and_live_revocation_dominate_history(ingress):
    e = raw()
    e["payload"].update(
        participant="synthetic:sender@lid",
        replyTo={"id": "synthetic:missing", "body": "must not import quote"},
    )
    assert post(ingress, e).status_code == 200
    revoked = raw("message.revoked", event_id="synthetic:revoked", timestamp=e["timestamp"] + 1000)
    assert post(ingress, revoked).status_code == 200
    with ingress[1].begin() as db:
        chat = db.scalar(select(WahaChat))
        sync.snapshot(
            db,
            chat,
            item("synthetic:original", body="stale history"),
            datetime.now(UTC),
            source="history",
            now=datetime.now(UTC),
        )
        row = db.get(WahaConnection, ingress[4].connection_id)
        timeline = sync.timeline(db, row, chat.id)
        assert len(timeline) == 1 and timeline[0]["revoked"] and timeline[0]["text"] is None
        assert timeline[0]["sender_id"] and timeline[0]["reply_to_id"] is None


def test_source_lookup_retains_uncertainty_without_fabricating_revision(setup):
    with setup[1].begin() as db:
        c = db.scalar(select(WahaChat))
        gap = WahaSourceGap(
            id=str(uuid4()),
            chat_id=c.id,
            provider_reference="synthetic:missing",
            observed_at=datetime.now(UTC),
            state="needs_lookup",
        )
        db.add(gap)
        gid = gap.id
    enqueue(setup, payload(setup, source_gap_id=gid))
    p = Provider([item("synthetic:missing")])
    work(setup, p)
    with setup[1]() as db:
        assert db.get(WahaSourceGap, gid).state == "snapshot_found"
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        assert db.scalar(select(func.count()).select_from(WahaSnapshot)) == 1


def test_cancel_commits_without_waiting_for_provider(setup):
    j = enqueue(setup).json()["data"]
    assert (
        setup[0]
        .post(
            path(setup, f"sync-jobs/{j['id']}/cancel"),
            json={"expected_version": 0},
            headers=setup[2],
        )
        .json()["data"]["state"]
        == "cancelled"
    )
    p = Provider([item()])
    assert not work(setup, p) and not p.calls


def test_discovery_pagination_preserves_prior_candidates(setup):
    calls = []
    setup[4].recent_chats = lambda **k: (
        calls.append(k) or [{"id": f"synthetic:peer-{k['offset']}@lid", "name": "Synthetic"}]
    )
    for offset in (0, 1):
        r = setup[0].post(
            path(setup, "operations"),
            json={"action": "discover", "expected_version": 0, "offset": offset, "limit": 1},
            headers={**setup[2], "Idempotency-Key": f"page-{offset}"},
        )
        assert r.status_code == 202
        from gigmate import waha_controls

        waha_controls.run_once(setup[1], make_client=lambda r: setup[4])
    with setup[1]() as db:
        assert (
            db.scalar(select(WahaControl).order_by(WahaControl.created_at.desc())).result[
                "next_offset"
            ]
            == 2
        )
    assert len(setup[0].get(path(setup, "chats")).json()["data"]) == 3


def test_historical_snapshot_can_refresh_but_never_replace_live_metadata(setup):
    with setup[1].begin() as db:
        c = db.scalar(select(WahaChat))
        now = datetime.now(UTC)
        snap, _ = sync.snapshot(
            db, c, item(), now - timedelta(seconds=30), source="history", now=now
        )
        _, changed = sync.snapshot(
            db,
            c,
            item(body="Updated synthetic snapshot"),
            now - timedelta(seconds=30),
            source="history",
            now=now + timedelta(seconds=1),
        )
        assert changed and snap.data["text"] == "Updated synthetic snapshot"
        sync.snapshot(
            db, c, item(body="Live caption"), now, source="live", now=now + timedelta(seconds=2)
        )
        _, changed = sync.snapshot(
            db,
            c,
            item(body="Old provider history"),
            now + timedelta(seconds=3),
            source="history",
            now=now + timedelta(seconds=4),
        )
        assert not changed and snap.data["text"] == "Live caption"


def test_stale_queued_range_expires_without_provider_read(setup):
    enqueue(setup)
    with setup[1].begin() as db:
        j = db.scalar(select(WahaSyncJob))
        j.command = {**j.command, "since": "2000-01-01T00:00:00Z"}
    p = Provider([item()])
    work(setup, p)
    with setup[1]() as db:
        assert db.scalar(select(WahaSyncJob)).error_code == "SYNC_RANGE_EXPIRED" and not p.calls


def test_history_retention_scrubs_text_by_source_time_not_import_time(setup):
    now = datetime.now(UTC)
    with setup[1].begin() as db:
        c = db.scalar(select(WahaChat))
        snap, _ = sync.snapshot(db, c, item(), now - timedelta(days=31), source="history", now=now)
        sync.purge(db, setup[3].connection_id, now - timedelta(days=30))
        assert snap.data["text"] is None


def test_group_text_and_media_have_owned_sender_identity_without_quote_content(ingress):
    with ingress[1].begin() as db:
        chat = db.scalar(select(WahaChat))
        chat.provider_chat_id = "synthetic:group@g.us"
    event = raw()
    event["payload"].update(
        {
            "from": "synthetic:group@g.us",
            "participant": "synthetic:member@lid",
            "replyTo": {"id": "synthetic:other", "body": "Must not copy quoted text"},
        }
    )
    assert post(ingress, event).status_code == 200
    event = raw(event_id="synthetic:group-media")
    event["payload"].update(
        id="synthetic:audio",
        **{"from": "synthetic:group@g.us"},
        participant="synthetic:member@lid",
        hasMedia=True,
        media={"mimetype": "audio/ogg"},
    )
    assert post(ingress, event).status_code == 200
    with ingress[1]() as db:
        rows = list(db.scalars(select(WahaSnapshot)))
        assert len(rows) == 2 and rows[0].data["sender_id"] == rows[1].data["sender_id"]
        assert "Must not copy" not in str([r.data for r in rows])


def test_two_workers_cannot_claim_same_page(setup):
    with setup[1]() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("PostgreSQL claim locking")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()
    p = Provider([item()])
    p.on_read = lambda: (entered.set(), release.wait(8))
    enqueue(setup)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(work, setup, p)
        assert entered.wait(5)
        try:
            assert pool.submit(work, setup, Provider([item()])).result(timeout=5) is False
        finally:
            release.set()
        assert first.result(timeout=5)
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WahaSnapshot)) == 1


def test_timeline_cursor_is_chat_scoped_and_temporally_ordered(setup):
    with setup[1].begin() as db:
        c = db.scalar(select(WahaChat))
        at = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=10)
        sync.snapshot(db, c, item("synthetic:one"), at, source="history", now=at)
        sync.snapshot(
            db,
            c,
            item("synthetic:two"),
            at + timedelta(microseconds=500000),
            source="history",
            now=at,
        )
    first = setup[0].get(path(setup, f"chats/{chat_id(setup)}/timeline?limit=1")).json()
    second = (
        setup[0]
        .get(path(setup, f"chats/{chat_id(setup)}/timeline?limit=1&cursor={first['next_cursor']}"))
        .json()
    )
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert (
        setup[0].get(path(setup, f"chats/{chat_id(setup)}/timeline?cursor=invalid")).status_code
        == 422
    )


def test_media_short_ack_and_caption_update_preserve_attachment_without_extra_jobs(ingress):
    e = raw()
    e["payload"].update(
        id="false_synthetic:peer@lid_MEDIA01",
        hasMedia=True,
        body="Initial synthetic caption",
        media={"mimetype": "image/png"},
    )
    assert post(ingress, e).status_code == 200
    ack = raw("message.ack", event_id="synthetic:media-ack", timestamp=e["timestamp"] + 500)
    ack["payload"].update(id="MEDIA01", ack=3)
    assert post(ingress, ack).status_code == 200
    edited = raw(
        "message.edited", event_id="synthetic:caption-edit", timestamp=e["timestamp"] + 1000
    )
    edited["payload"].update(editedMessageId="MEDIA01", body="Updated synthetic caption")
    assert post(ingress, edited).status_code == 200
    with ingress[1]() as db:
        snap = db.scalar(select(WahaSnapshot))
        assert snap.data["delivery_status"] == "read"
        assert snap.data["kind"] == "image" and snap.data["text"] == "Updated synthetic caption"
        assert db.scalar(select(func.count()).select_from(Job)) == 0
