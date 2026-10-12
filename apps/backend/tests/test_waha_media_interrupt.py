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
