from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_waha_controls import path
from test_waha_media import Processor, asset, body, enqueue, result, work
from test_waha_media import ingress as ingress
from test_waha_media import setup as setup

from gigmate import media_processing
from gigmate import waha_media as media
from gigmate.db import WahaAttachment, WahaMediaJob, WahaSnapshot


@pytest.mark.parametrize("operation", ["cancel", "pause-regrant", "source", "expiry"])
@pytest.mark.parametrize("outcome", ["unknown", "success", "unavailable"])
def test_inflight_stop_keeps_unknown_gate_and_suppresses_late_content(setup, operation, outcome):
    command = body(setup, process=True, consent_model=True)
    job_id = enqueue(setup, command).json()["data"]["id"]
    assert work(setup)
    evidence = {}

    class Interrupted(Processor):
        def process(self, request):
            if operation == "cancel":
                response = setup[0].post(
                    path(setup, f"media/jobs/{job_id}/cancel"),
                    json={"expected_version": 0},
                    headers=setup[2],
                )
                evidence["cancel_status"] = response.status_code
                lookup = setup[0].post(
                    path(setup, f"media/jobs/{job_id}/reconcile"),
                    json={"expected_version": 0},
                    headers=setup[2],
                )
                evidence["inflight_reconcile"] = lookup.status_code
            elif operation == "pause-regrant":
                for verb, version in (("pause", 0), ("resume", 1)):
                    response = setup[0].post(
                        path(setup, verb), json={"expected_version": version}, headers=setup[2]
                    )
                    evidence[verb] = response.status_code
                command["expected_version"] = 2
            elif operation == "source":
                with setup[1].begin() as db:
                    snapshot = db.scalar(select(WahaSnapshot))
                    snapshot.data = {**snapshot.data, "text": "Changed synthetic caption"}
            else:
                with setup[1].begin() as db:
                    current = db.get(WahaAttachment, request.attachment_id)
                    current.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                media.purge(setup[1])
            if outcome == "unknown":
                raise media_processing.ProcessingUncertain
            if outcome == "unavailable":
                raise media_processing.ProcessingUnavailable
            return result()

    assert work(setup, processor=Interrupted())
    if operation == "cancel":
        assert evidence == {"cancel_status": 200, "inflight_reconcile": 409}
    if operation == "pause-regrant":
        assert evidence == {"pause": 200, "resume": 200}
    with setup[1]() as db:
        job = db.get(WahaMediaJob, job_id)
        assert job.state == ("result_unknown" if outcome == "unknown" else "cancelled")
        assert bool(job.active_key) == (outcome == "unknown")
        assert job.lease_token is None
    assert asset(setup).result is None
    assert asset(setup).review is None
    if outcome == "unknown":
        response = enqueue(setup, command, key="synthetic-new-intent")
        assert response.status_code == 409
        assert not work(setup, processor=Interrupted())


@pytest.mark.parametrize("operation", ["cancel", "pause-regrant"])
@pytest.mark.parametrize("unknown_lookups", [0, 2])
def test_stopped_unknown_result_never_republished_after_later_lookup(
    setup, operation, unknown_lookups
):
    observed = {"submissions": 0, "lookups": []}
    command = body(setup, process=True, consent_model=True)
    job_id = enqueue(setup, command).json()["data"]["id"]

    class Stopped(Processor):
        def process(self, request):
            observed["submissions"] += 1
            actions = (
                [(f"media/jobs/{job_id}/cancel", 0)]
                if operation == "cancel"
                else [("pause", 0), ("resume", 1)]
            )
            observed["statuses"] = [
                setup[0]
                .post(path(setup, verb), json={"expected_version": version}, headers=setup[2])
                .status_code
                for verb, version in actions
            ]
            raise media_processing.ProcessingUncertain

        def reconcile(self, request_id):
            observed["lookups"].append(request_id)
            return None if len(observed["lookups"]) <= unknown_lookups else result()

    processor = Stopped()
    assert work(setup) and work(setup, processor=processor)
    assert observed["statuses"] == ([200] if operation == "cancel" else [200, 200])
    version = 0 if operation == "cancel" else 2
    reason = "MEDIA_CANCELLED" if operation == "cancel" else "CONSENT_REVOKED"
    for index in range(unknown_lookups + 1):
        response = setup[0].post(
            path(setup, f"media/jobs/{job_id}/reconcile"),
            json={"expected_version": version},
            headers=setup[2],
        )
        assert response.status_code == 200, response.text
        assert work(setup, processor=processor)
        final = index == unknown_lookups
        with setup[1]() as db:
            job = db.get(WahaMediaJob, job_id)
            assert job.state == ("cancelled" if final else "result_unknown")
            assert bool(job.active_key) == (not final)
            assert job.error_code == reason
            assert job.content_stop_reason == reason
            assert job.lease_token is None
        current = asset(setup)
        assert current.result is None and current.review is None
        response = setup[0].get(path(setup, f"media/attachments/{current.id}"))
        assert response.status_code == 200, response.text
        assert response.json()["data"]["result"] is None
        if not final:
            assert (
                enqueue(
                    setup, {**command, "expected_version": version}, key=f"blocked-{index}"
                ).status_code
                == 409
            )
    assert observed["submissions"] == 1
    assert observed["lookups"] == [job_id] * (unknown_lookups + 1)
    fresh = enqueue(setup, {**command, "expected_version": version}, key="explicit-new-intent")
    assert fresh.status_code == 202, fresh.text
    assert fresh.json()["data"]["id"] != job_id


def test_cancel_pending_reconciliation_preserves_original_unknown(setup):
    class Uncertain(Processor):
        def process(self, request):
            raise media_processing.ProcessingUncertain

    command = body(setup, process=True, consent_model=True)
    job = enqueue(setup, command).json()["data"]["id"]
    assert work(setup) and work(setup, processor=Uncertain())
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
    assert (
        setup[0]
        .post(
            path(setup, f"media/jobs/{job}/cancel"), json={"expected_version": 0}, headers=setup[2]
        )
        .status_code
        == 200
    )
    assert enqueue(setup, command, key="another-intent").status_code == 409
    assert not work(setup, processor=Uncertain())


@pytest.mark.parametrize("outcome", ["unknown", "success", "unavailable"])
def test_cancel_running_read_only_reconciliation_does_not_resubmit(setup, outcome):
    observed = {}

    class Reconciler(Processor):
        def process(self, request):
            raise media_processing.ProcessingUncertain

        def reconcile(self, request_id):
            observed["request_id"] = request_id
            response = setup[0].post(
                path(setup, f"media/jobs/{request_id}/cancel"),
                json={"expected_version": 0},
                headers=setup[2],
            )
            observed["status"] = response.status_code
            if outcome == "unknown":
                return None
            if outcome == "unavailable":
                raise media_processing.ProcessingUnavailable
            return result()

    command = body(setup, process=True, consent_model=True)
    job_id = enqueue(setup, command).json()["data"]["id"]
    processor = Reconciler()
    assert work(setup) and work(setup, processor=processor)
    assert (
        setup[0]
        .post(
            path(setup, f"media/jobs/{job_id}/reconcile"),
            json={"expected_version": 0},
            headers=setup[2],
        )
        .status_code
        == 200
    )
    assert work(setup, processor=processor)
    assert observed == {"request_id": job_id, "status": 200}
    with setup[1]() as db:
        job = db.get(WahaMediaJob, job_id)
        assert job.state == ("cancelled" if outcome == "success" else "result_unknown")
        assert bool(job.active_key) == (outcome != "success")
    assert asset(setup).result is None
