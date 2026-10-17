"""Reviewed attachments becoming work-order evidence (role C, item 4).

The promotion path must never bypass review, never cross conversation
boundaries, never duplicate evidence and never confirm a requirement change.
"""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_waha_media import asset, body, enqueue, work
from test_waha_media import ingress as ingress_fixture
from test_waha_media import setup as setup_fixture
from test_waha_media_evidence import checked, processed

from gigmate.db import (
    ChangeRow,
    ConversationOrder,
    ConversationRow,
    WahaAttachment,
    WorkOrderEvidenceRow,
    WorkOrderRow,
)
from gigmate.seed import uid

ORDER = uid(3)


@pytest.fixture
def ingress(signed_in, monkeypatch):
    return ingress_fixture.__wrapped__(signed_in, monkeypatch)


@pytest.fixture
def setup(ingress, monkeypatch, tmp_path):
    value = setup_fixture.__wrapped__(ingress, monkeypatch, tmp_path)
    monkeypatch.setenv("WAHA_MEDIA_ENABLED", "true")
    monkeypatch.setenv("WAHA_MEDIA_ROOT", str(tmp_path / "private-media"))
    monkeypatch.delenv("GIGMATE_MEDIA_PROCESSOR_FACTORY", raising=False)
    from test_waha_ingress import post, raw

    event = raw(event_id="synthetic:evidence-picture")
    event["payload"].update(
        id="false_synthetic:peer@lid_EVID10",
        hasMedia=True,
        body="Synthetic evidence caption",
        media={"mimetype": "image/png", "filename": "synthetic.png"},
    )
    assert post(ingress, event).status_code == 200
    return value


def conversation_of_attachment(db, attachment_id):
    from gigmate.db import WahaChat, WahaSnapshot

    snapshot = db.get(WahaSnapshot, db.get(WahaAttachment, attachment_id).snapshot_id)
    return db.get(WahaChat, snapshot.chat_id).conversation_id


def link_order(s, order_id=ORDER):
    """Link the attachment's conversation to a seeded work order."""
    with s[1].begin() as db:
        conversation_id = conversation_of_attachment(db, asset(s).id)
        if db.get(ConversationOrder, (conversation_id, order_id)) is None:
            db.add(ConversationOrder(conversation_id=conversation_id, work_order_id=order_id))
    return order_id


def unlinked_order(s):
    """A work order whose conversation is not the attachment's."""
    from gigmate.seed import uid as seeded

    order_id = str(uuid4())
    with s[1].begin() as db:
        if db.get(WorkOrderRow, order_id) is None:
            db.add(
                WorkOrderRow(
                    id=order_id,
                    account_id=seeded(1),
                    data={"id": order_id, "version": 1, "pending_change_ids": []},
                )
            )
    return order_id


def payload(identifier, query, note="Synthetic evidence note"):
    return {
        "attachment_id": identifier,
        "expected_attachment_version": query["expected_attachment_version"],
        "expected_context_version": query["expected_context_version"],
        "expected_result_job_id": str(query["expected_result_job_id"]),
        "note": note,
    }


def test_review_is_required_before_promotion(setup):
    identifier, _, query = processed(setup)
    link_order(setup)
    response = setup[0].post(
        f"/api/v1/work-orders/{ORDER}/evidence", json=payload(identifier, query), headers=setup[2]
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MEDIA_REVIEW_REQUIRED"
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WorkOrderEvidenceRow)) == 0


def test_reviewed_attachment_becomes_work_order_evidence_idempotently(setup):
    identifier, _, query = processed(setup)
    link_order(setup)
    with setup[1]() as db:
        changes_before = db.scalar(select(func.count()).select_from(ChangeRow))
    assert checked(setup, identifier, query).status_code == 200
    response = setup[0].post(
        f"/api/v1/work-orders/{ORDER}/evidence", json=payload(identifier, query), headers=setup[2]
    )
    assert response.status_code == 201
    first = response.json()["data"]
    assert first["attachment_id"] == identifier
    assert first["result_job_id"] == query["expected_result_job_id"]
    assert first["stale"] is False and first["stale_reason"] is None
    assert first["sha256"] and first["work_order_id"] == ORDER

    # Same binding again: one row, same identity.
    repeat = setup[0].post(
        f"/api/v1/work-orders/{ORDER}/evidence", json=payload(identifier, query), headers=setup[2]
    )
    assert repeat.status_code == 201 and repeat.json()["data"]["id"] == first["id"]

    listed = setup[0].get(f"/api/v1/work-orders/{ORDER}/evidence").json()["items"]
    assert [item["id"] for item in listed] == [first["id"]]

    # Promotion is evidence only: no requirement change, no confirmation.
    with setup[1]() as db:
        order = db.get(WorkOrderRow, ORDER)
        assert db.scalar(select(func.count()).select_from(WorkOrderEvidenceRow)) == 1
        assert db.scalar(select(func.count()).select_from(ChangeRow)) == changes_before
        assert "pending_change_ids" not in order.data or not order.data["pending_change_ids"]


def test_evidence_requires_the_conversation_to_be_linked(setup):
    identifier, _, query = processed(setup)
    assert checked(setup, identifier, query).status_code == 200
    order_id = unlinked_order(setup)
    response = setup[0].post(
        f"/api/v1/work-orders/{order_id}/evidence",
        json=payload(identifier, query),
        headers=setup[2],
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MEDIA_ORDER_LINK_REQUIRED"


def test_evidence_rejects_a_newer_result_than_the_reviewed_one(setup):
    identifier, _, query = processed(setup)
    link_order(setup)
    assert checked(setup, identifier, query).status_code == 200
    with setup[1].begin() as db:
        db.get(WahaAttachment, identifier).result = {
            **db.get(WahaAttachment, identifier).result,
            "job_id": str(uuid4()),
        }
    response = setup[0].post(
        f"/api/v1/work-orders/{ORDER}/evidence", json=payload(identifier, query), headers=setup[2]
    )
    assert response.status_code == 409


def test_evidence_is_scoped_to_the_owning_account(setup):
    identifier, _, query = processed(setup)
    link_order(setup)
    assert checked(setup, identifier, query).status_code == 200
    assert (
        setup[0]
        .post("/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"})
        .status_code
        == 200
    )
    response = setup[0].post(
        f"/api/v1/work-orders/{ORDER}/evidence", json=payload(identifier, query), headers=setup[2]
    )
    assert response.status_code in {403, 404}
    with setup[1]() as db:
        assert db.scalar(select(func.count()).select_from(WorkOrderEvidenceRow)) == 0


def test_prior_evidence_is_flagged_stale_instead_of_rewritten(setup):
    identifier, _, query = processed(setup)
    link_order(setup)
    assert checked(setup, identifier, query).status_code == 200
    created = (
        setup[0]
        .post(
            f"/api/v1/work-orders/{ORDER}/evidence",
            json=payload(identifier, query),
            headers=setup[2],
        )
        .json()["data"]
    )
    with setup[1].begin() as db:
        db.get(ConversationRow, created["conversation_id"]).context_version += 1
    listed = setup[0].get(f"/api/v1/work-orders/{ORDER}/evidence").json()["items"]
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]
    assert listed[0]["stale"] is True
    assert listed[0]["stale_reason"] == "MEDIA_SOURCE_CHANGED"


def test_promotion_requires_explicit_csrf_headers(setup):
    identifier, _, query = processed(setup)
    link_order(setup)
    assert checked(setup, identifier, query).status_code == 200
    response = setup[0].post(
        f"/api/v1/work-orders/{ORDER}/evidence", json=payload(identifier, query)
    )
    assert response.status_code == 403


def test_download_only_attachment_cannot_be_promoted(setup):
    """An attachment that was never processed has no reviewed result."""
    assert enqueue(setup, body(setup)).status_code == 202
    assert work(setup)
    identifier = asset(setup).id
    link_order(setup)
    response = setup[0].post(
        f"/api/v1/work-orders/{ORDER}/evidence",
        json={
            "attachment_id": identifier,
            "expected_attachment_version": 1,
            "expected_context_version": 0,
            "expected_result_job_id": str(uuid4()),
        },
        headers=setup[2],
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] in {
        "MEDIA_SOURCE_CHANGED",
        "MEDIA_RESULT_CHANGED",
        "MEDIA_REVIEW_REQUIRED",
        "MEDIA_RESULT_UNAVAILABLE",
    }
