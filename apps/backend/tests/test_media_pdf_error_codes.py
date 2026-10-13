import pytest
from test_waha_controls import path
from test_waha_media import Processor, body, enqueue, work
from test_waha_media import ingress as ingress
from test_waha_media import setup as setup

from gigmate import media_processing
from gigmate.db import WahaMediaJob


@pytest.mark.parametrize(
    "code",
    [
        "MEDIA_PDF_TIMEOUT",
        "MEDIA_PDF_MEMORY_LIMIT",
        "MEDIA_PDF_LIMIT_UNAVAILABLE",
        "MEDIA_PDF_OUTPUT_LIMIT",
    ],
)
def test_pdf_pre_submission_failure_is_persisted_without_retry(setup, code):
    class Refused(Processor):
        calls = 0

        def process(self, request):
            self.calls += 1
            raise media_processing.ProcessingUnavailable(code)

    identifier = enqueue(setup, body(setup, process=True, consent_model=True)).json()["data"]["id"]
    processor = Refused()
    assert work(setup) and work(setup, processor=processor)
    with setup[1]() as db:
        job = db.get(WahaMediaJob, identifier)
        assert job.state == "failed"
        assert job.error_code == code
        assert job.active_key is None
    assert not work(setup, processor=processor)
    assert processor.calls == 1


def test_cancel_during_preparation_blocks_trusted_submission_hook(setup):
    identifier = enqueue(setup, body(setup, process=True, consent_model=True)).json()["data"]["id"]
    evidence = {}

    class Preparation(Processor):
        def process(self, request):
            response = setup[0].post(
                path(setup, f"media/jobs/{identifier}/cancel"),
                json={"expected_version": 0},
                headers=setup[2],
            )
            evidence["cancel"] = response.status_code
            try:
                request.before_submit()
            except media_processing.ProcessingUnavailable:
                evidence["blocked"] = True
                raise
            pytest.fail("authority was not rechecked")

    assert work(setup) and work(setup, processor=Preparation())
    assert evidence == {"cancel": 200, "blocked": True}
    with setup[1]() as db:
        job = db.get(WahaMediaJob, identifier)
        assert job.state == "cancelled" and job.active_key is None
