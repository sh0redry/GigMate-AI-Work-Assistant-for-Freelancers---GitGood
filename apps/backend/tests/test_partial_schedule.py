"""Synthetic live-message regressions; never contact a model or connector."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_reviewed_product import incoming

from gigmate.approvals import draft_for_change
from gigmate.contracts import ChangeProposal
from gigmate.db import CalendarRow, ChangeRow, ConversationRow, Job, ModelCallTrace, WorkOrderRow
from gigmate.extraction.disabled import DisabledProvider
from gigmate.extraction.registry import _reset_provider_for_testing
from gigmate.seed import uid
from gigmate.worker import run_once


@pytest.mark.parametrize(
    "schedule,expected_status",
    [
        ("2026-10-18T02:00:00Z", "needs_review"),
        ("Synthetic tomorrow morning", "needs_review"),
        (10, "needs_review"),
        (True, "needs_review"),
        (None, "needs_review"),
        (
            {"kind": "instant", "at": "2026-10-18T02:00:00Z", "timezone": "Asia/Hong_Kong"},
            "needs_review",
        ),
        (
            {"kind": "date_only", "date": "2026-10-18", "timezone": "Asia/Hong_Kong"},
            "proposed",
        ),
        (
            {
                "kind": "timed",
                "start_at": "2026-10-18T02:00:00Z",
                "end_at": "2026-10-18T03:00:00Z",
                "timezone": "Asia/Hong_Kong",
            },
            "proposed",
        ),
    ],
)
def test_partial_schedule_preserves_address_and_evidence_without_calendar(
    signed_in, schedule, expected_status
):
    client, factory, _, headers = signed_in
    incoming(factory)

    class PartialSchedule(DisabledProvider):
        calls = 0

        def propose(self, request):
            self.calls += 1
            outcome = super().propose(request)
            data = outcome.proposal.model_dump(mode="json")
            data.update(
                assignment="matched",
                work_order_id=uid(3),
                base_work_order_version=request.base_work_order_version,
                unresolved_questions=[],
                changes=[
                    {
                        "field": field,
                        "old_value": None,
                        "new_value": value,
                        "field_status": "proposed",
                        "customer_confirmation": "confirmed",
                        "sources": [{"message_id": request.message_id, "message_revision": 1}],
                        "reason": "Synthetic customer supplied a location and start time.",
                    }
                    for field, value in [
                        ("address", "Synthetic meeting point"),
                        ("schedule", schedule),
                    ]
                ],
            )
            return replace(
                outcome,
                proposal=ChangeProposal.model_validate_json(json.dumps(data)),
                refused_reason=None,
                request_id=request.extra["request_id"],
            )

    selected = PartialSchedule()
    _reset_provider_for_testing(selected)
    try:
        with factory() as db:
            original = json.loads(json.dumps(db.get(WorkOrderRow, uid(3)).data))
            calendar = [row.data for row in db.scalars(select(CalendarRow))]
        assert run_once(factory)
        assert not run_once(factory)
        assert selected.calls == 1
        with factory() as db:
            job = db.scalar(select(Job))
            assert job.state == "completed" and job.error_code is None
            assert db.scalar(select(ModelCallTrace)).request_id == job.model_request_id
            order = db.get(WorkOrderRow, uid(3)).data
            assert order["fields"] == original["fields"]
            assert order["version"] == original["version"]
            assert [row.data for row in db.scalars(select(CalendarRow))] == calendar
            rows = {row.data["field"]: row for row in db.scalars(select(ChangeRow))}
            assert rows["address"].data["status"] == "proposed"
            assert rows["schedule"].data["new_value"] == schedule
            assert rows["schedule"].data["status"] == expected_status
            schedule_id = rows["schedule"].id
            version, context = order["version"], rows["schedule"].context_version
        response = client.get(f"/api/v1/work-orders/{uid(3)}/changes")
        assert response.status_code == 200
        if expected_status == "needs_review":
            response = client.post(
                f"/api/v1/work-orders/{uid(3)}/changes/{schedule_id}/confirm",
                json={
                    "expected_version": version,
                    "expected_context_version": context,
                    "apply_calendar_update": True,
                },
                headers={**headers, "Idempotency-Key": str(uuid4())},
            )
            assert response.status_code == 409
    finally:
        _reset_provider_for_testing()


def test_draft_generation_tolerates_a_partial_schedule(signed_in):
    _, factory, _, _ = signed_in
    with factory.begin() as db:
        order = db.get(WorkOrderRow, uid(3))
        conversation = db.get(ConversationRow, uid(2))
        assert (
            draft_for_change(
                db,
                order.account_id,
                order,
                conversation,
                {"field": "schedule", "status": "proposed", "new_value": "Synthetic 10am"},
            )
            is None
        )


def test_worker_failure_diagnostics_never_log_exception_text(signed_in, caplog):
    _, factory, _, _ = signed_in
    incoming(factory)

    class Broken(DisabledProvider):
        def propose(self, request):
            raise AttributeError("synthetic-private-message-and-credential")

    _reset_provider_for_testing(Broken())
    try:
        assert run_once(factory)
        with factory() as db:
            assert db.scalar(select(Job)).error_code == "MODEL_OUTCOME_UNKNOWN"
        assert "exception_type=AttributeError" in caplog.text
        assert "synthetic-private-message-and-credential" not in caplog.text
        assert not run_once(factory)
    finally:
        _reset_provider_for_testing()
