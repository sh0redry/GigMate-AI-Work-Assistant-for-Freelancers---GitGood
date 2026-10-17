"""Fictional product acceptance: no connector or paid vendor is contacted."""

import copy
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_create_order import create, future
from test_extraction import _build_reschedule_request
from test_extraction_batch3 import _configure

from gigmate.contracts import ChangeProposal
from gigmate.db import (
    Account,
    AuditRow,
    ConversationRow,
    Inbox,
    Job,
    MessageRow,
    Proposal,
    ProposalDecision,
    TaskRow,
    WahaConnection,
    WorkOrderRow,
)
from gigmate.extraction.disabled import DisabledProvider
from gigmate.extraction.persistence import persist_proposal
from gigmate.extraction.registry import _reset_provider_for_testing
from gigmate.extraction.reviewed import ReviewedLLMProvider
from gigmate.messaging import ingest, replay_event
from gigmate.seed import uid
from gigmate.worker import audit_provider_config, run_once


def incoming(factory):
    event = copy.deepcopy(replay_event("available"))
    event.update(
        connector="waha", source="app", provider_message_id="synthetic:product", message_revision=1
    )
    with factory.begin() as db:
        ingest(db, db.get(Account, uid(1)), event, trusted_waha=True)
    return event


def test_model_io_has_no_business_locks_and_revalidates_consent(signed_in):
    _, factory, _, _ = signed_in
    incoming(factory)

    class DuringCall(DisabledProvider):
        def propose(self, request):
            # A second transaction must be able to lock/write the same account.
            with factory.begin() as db:
                db.scalar(select(Account).where(Account.id == uid(1)).with_for_update(nowait=True))
                db.get(ConversationRow, uid(2)).allowlisted = False
            return super().propose(request)

    _reset_provider_for_testing(DuringCall())
    try:
        assert run_once(factory)
        with factory() as db:
            assert db.scalar(select(Job)).error_code == "CONSENT_REVOKED"
            assert db.scalar(select(func.count()).select_from(Proposal)) == 0
    finally:
        _reset_provider_for_testing()


@pytest.mark.parametrize("change", ["context", "order", "pause-regrant", "crash"])
def test_model_results_never_promote_stale_snapshots_or_repeat_unknown_calls(signed_in, change):
    _, factory, _, _ = signed_in
    incoming(factory)
    with factory.begin() as db:
        connection = WahaConnection(
            id=uid(80),
            account_id=uid(1),
            instance_id="synthetic-instance",
            session_id="synthetic-session",
            enabled=True,
        )
        db.add(connection)
        db.scalar(select(Inbox)).connection_id = connection.id

    class DuringCall(DisabledProvider):
        calls = 0

        def propose(self, request):
            self.calls += 1
            if change == "crash":
                raise RuntimeError("synthetic lost reply")
            with factory.begin() as db:
                if change == "context":
                    db.get(ConversationRow, uid(2)).context_version += 1
                elif change == "order":
                    order = db.get(WorkOrderRow, uid(3))
                    order.data = {**order.data, "version": order.data["version"] + 1}
                elif change == "pause-regrant":
                    db.get(WahaConnection, uid(80)).control_version += 2
            return super().propose(request)

    p = DuringCall()
    _reset_provider_for_testing(p)
    try:
        assert run_once(factory)
        assert run_once(factory) is False
        assert p.calls == 1
        with factory() as db:
            assert db.scalar(select(Job)).state == "completed"
            assert not list(db.scalars(select(Proposal)))
    finally:
        _reset_provider_for_testing()


def test_abandoned_model_submission_never_reclaims_as_a_new_paid_call(signed_in):
    _, factory, _, _ = signed_in
    incoming(factory)
    with factory.begin() as db:
        job = db.scalar(select(Job))
        job.state, job.model_request_id = "processing", "synthetic:persisted-call"
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        job.lease_owner = str(uuid4())
    assert run_once(factory)
    with factory() as db:
        job = db.scalar(select(Job))
        assert job.state == "completed" and job.error_code == "MODEL_OUTCOME_UNKNOWN"
    assert not run_once(factory)


def test_provider_names_are_validated_before_startup(monkeypatch, caplog):
    monkeypatch.setenv("GIGMATE_EXTRACTION_PROVIDER", "synthetic-private-invalid")
    assert not audit_provider_config()
    assert "EXTRACTION_PROVIDER_INVALID" in caplog.text
    assert "synthetic-private-invalid" not in caplog.text
    for provider in ("deterministic", "disabled", "llm", "reviewed_llm"):
        monkeypatch.setenv("GIGMATE_EXTRACTION_PROVIDER", provider)
        monkeypatch.delenv("GIGMATE_LLM_LIVE", raising=False)
        assert audit_provider_config()


def configured(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("GIGMATE_LLM_COST_INPUT_USD_PER_1K", "0.001")
    monkeypatch.setenv("GIGMATE_LLM_COST_OUTPUT_USD_PER_1K", "0.002")
    return ReviewedLLMProvider()


def test_reviewed_provider_requires_explicit_operator_prices(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.delenv("GIGMATE_LLM_COST_INPUT_USD_PER_1K", raising=False)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("must refuse before process/network")
    )
    result = ReviewedLLMProvider().propose(_build_reschedule_request(text="synthetic"))
    assert result.refused_reason == "llm:operator-pricing-required"


def test_reviewed_provider_keeps_request_identity_on_a_successful_child(monkeypatch):
    p = configured(monkeypatch)
    request = _build_reschedule_request(text="synthetic")

    def child(args, **kwargs):
        request_value = json.loads(kwargs["input"])
        outcome = DisabledProvider().propose(request)
        value = asdict(outcome)
        value["proposal"] = outcome.proposal.model_dump(mode="json")
        value["request_id"] = request_value["extra"]["request_id"]
        assert kwargs["timeout"] == 20 and kwargs["capture_output"]
        assert "sk-fake-test" not in kwargs["input"].decode()
        return subprocess.CompletedProcess(args, 0, json.dumps(value).encode(), b"")

    monkeypatch.setattr(subprocess, "run", child)
    result = p.propose(request)
    assert result.request_id and result.proposal.assignment.value == "needs_review"


def test_actual_sleeping_child_is_killed_and_never_resubmitted(monkeypatch):
    p = configured(monkeypatch)
    actual = subprocess.run
    calls = []

    def child(args, **kwargs):
        calls.append(args)
        return actual(
            [sys.executable, "-c", "import time; time.sleep(10)"], capture_output=True, timeout=0.05
        )

    monkeypatch.setattr(subprocess, "run", child)
    result = p.propose(_build_reschedule_request(text="synthetic"))
    assert len(calls) == 1
    assert result.refused_reason == "llm:result-unknown:deadline" and result.request_id


def suggestion(factory):
    event = incoming(factory)
    with factory.begin() as db:
        inbox = db.get(Inbox, event["event_id"])
        context = db.get(ConversationRow, uid(2)).context_version
        from gigmate.extraction.types import ExtractionRequest

        request = ExtractionRequest(
            account_id=uid(1),
            conversation_id=uid(2),
            message_id=event["payload"]["message_id"],
            message_revision=1,
            message_text="synthetic",
            context_version=context,
        )
        outcome = DisabledProvider().propose(request)
        value = outcome.proposal.model_dump(mode="json")
        value["new_work_order"] = {
            "summary": "Synthetic new job",
            "fields": [],
            "missing_fields": ["schedule", "address"],
            "unresolved_questions": [],
            "confidence": 0.8,
        }
        row = persist_proposal(
            db,
            account_id=uid(1),
            conversation_id=uid(2),
            event_id=inbox.id,
            proposal=ChangeProposal.model_validate_json(json.dumps(value)),
            outcome=outcome,
        )
        return row.id, context


def test_suggestion_is_readonly_then_consumed_once_with_original_key_recovery(signed_in):
    client, factory, _, headers = signed_in
    proposed, context = suggestion(factory)
    path = "/api/v1/new-order-suggestions"
    assert client.get(path).json()["items"][0]["id"] == proposed
    with factory() as db:
        before = db.scalar(select(func.count()).select_from(WorkOrderRow))
    key = str(uuid4())
    args = dict(from_proposal_id=proposed, expected_context_version=context)
    created = create(client, headers, key=key, **args)
    assert created.status_code == 201, created.text
    assert created.json()["data"]["fields"]["schedule"]["status"] == "missing"
    assert create(client, headers, key=key, **args).json()["data"] == created.json()["data"]
    assert create(client, headers, **args).status_code == 409
    assert client.get(path).json()["items"] == []
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WorkOrderRow)) == before + 1
        assert db.scalar(select(func.count()).select_from(ProposalDecision)) == 1


@pytest.mark.parametrize("case", ["foreign", "paused", "context", "source"])
def test_suggestion_creation_rejects_foreign_paused_and_changed_evidence(signed_in, case):
    client, factory, _, headers = signed_in
    proposed, context = suggestion(factory)
    with factory.begin() as db:
        row = db.get(Proposal, proposed)
        if case == "foreign":
            row.account_id = uid(99)
        elif case == "paused":
            db.get(ConversationRow, uid(2)).allowlisted = False
        elif case == "context":
            db.get(ConversationRow, uid(2)).context_version += 1
        else:
            inbox = db.get(Inbox, row.event_id)
            db.get(MessageRow, (inbox.payload["payload"]["message_id"], 1)).data = {
                **db.get(MessageRow, (inbox.payload["payload"]["message_id"], 1)).data,
                "revoked": True,
            }
        before = db.scalar(select(func.count()).select_from(WorkOrderRow))
    response = create(client, headers, from_proposal_id=proposed, expected_context_version=context)
    assert response.status_code in {403, 404, 409}, response.text
    assert client.get("/api/v1/new-order-suggestions").json()["items"] == []
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WorkOrderRow)) == before
        assert not list(db.scalars(select(ProposalDecision)))


def test_task_decision_preserves_customer_facts_and_checks_versions(signed_in):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(), address="Synthetic address").json()["data"]
    with factory() as db:
        task = db.scalar(select(TaskRow).where(TaskRow.work_order_id == order["id"]))
        task_id = task.id
    body = {"expected_version": order["version"], "expected_state": "pending", "state": "completed"}
    h = {**headers, "Idempotency-Key": str(uuid4())}
    path = f"/api/v1/tasks/{task_id}/status"
    result = client.post(path, json=body, headers=h)
    assert result.status_code == 200, result.text
    assert client.post(path, json=body, headers=h).json()["data"] == result.json()["data"]
    assert (
        client.post(path, json=body, headers={**h, "Idempotency-Key": str(uuid4())}).status_code
        == 409
    )
    updated = client.get(f"/api/v1/work-orders/{order['id']}").json()["data"]
    assert updated["version"] == order["version"] + 1
    assert updated["fields"] == order["fields"]


@pytest.mark.parametrize("case", ["foreign", "paused", "dependency"])
def test_task_decision_has_no_partial_writes_on_rejection(signed_in, case):
    client, factory, _, headers = signed_in
    order = create(client, headers, schedule=future(), address="Synthetic address").json()["data"]
    with factory.begin() as db:
        task = db.scalar(select(TaskRow).where(TaskRow.work_order_id == order["id"]))
        task_id = task.id
        if case == "foreign":
            task.account_id = uid(99)
        elif case == "paused":
            db.get(ConversationRow, uid(2)).allowlisted = False
        else:
            task.data = {**task.data, "depends_on": [task.id]}
        before = db.scalar(select(func.count()).select_from(AuditRow))
    result = client.post(
        f"/api/v1/tasks/{task_id}/status",
        json={
            "expected_version": order["version"],
            "expected_state": "pending",
            "state": "completed",
        },
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert result.status_code in {403, 404, 409}, result.text
    with factory() as db:
        assert db.get(WorkOrderRow, order["id"]).data["version"] == order["version"]
        assert db.get(TaskRow, task_id).data["state"] == "pending"
        assert db.scalar(select(func.count()).select_from(AuditRow)) == before


@pytest.mark.parametrize(
    "question,intent",
    [
        ("今天有什么安排", "today"),
        ("聽日有咩安排", "tomorrow"),
        ("what is waiting for customers", "waiting"),
        ("有咩要我決定", "open_items"),
        ("send a message now", "unsupported"),
    ],
)
def test_workspace_query_is_bounded_owned_and_readonly(signed_in, question, intent):
    client, factory, _, headers = signed_in
    with factory() as db:
        before = db.scalar(select(func.count()).select_from(AuditRow))
    result = client.post("/api/v1/workspace-query", json={"question": question}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["intent"] == intent
    assert all(item.get("work_order_id") != uid(23) for item in result.json()["data"]["items"])
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditRow)) == before


def test_worker_invalid_provider_exits_before_any_heartbeat(monkeypatch):
    from gigmate import worker

    monkeypatch.setenv("GIGMATE_EXTRACTION_PROVIDER", "synthetic-invalid")
    monkeypatch.setattr(worker, "heartbeat_loop", lambda *a, **k: pytest.fail("must not start"))
    with pytest.raises(SystemExit) as exit_info:
        worker.main()
    assert exit_info.value.code == 2


def test_unknown_model_job_cannot_be_reassigned_but_can_be_dismissed(signed_in):
    client, factory, _, headers = signed_in
    incoming(factory)
    with factory.begin() as db:
        job = db.scalar(select(Job))
        job.state, job.error_code = "completed", "MODEL_OUTCOME_UNKNOWN"
        job.model_request_id = "synthetic:original-paid-call"
        context = db.get(ConversationRow, uid(2)).context_version
        job_id = job.id
    queue = client.get("/api/v1/review-items").json()["items"]
    assert queue[0]["model_request_id"] == "synthetic:original-paid-call"
    path = f"/api/v1/review-items/{job_id}/assign"
    h = {**headers, "Idempotency-Key": str(uuid4())}
    response = client.post(
        path,
        headers=h,
        json={"action": "assign", "work_order_id": uid(3), "expected_context_version": context},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MODEL_OUTCOME_UNKNOWN"
    response = client.post(
        path,
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={"action": "dismiss", "expected_context_version": context},
    )
    assert response.status_code == 200, response.text
    with factory() as db:
        assert db.get(Job, job_id).state == "completed"
        assert db.get(Job, job_id).model_request_id == "synthetic:original-paid-call"


def test_reviewed_provider_real_subprocess_calls_only_the_loopback_fake_vendor(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from gigmate.extraction.reviewed import configured_for_live

    configured(monkeypatch)
    from pathlib import Path

    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src"))
    calls = []
    request = _build_reschedule_request(text="Synthetic local-only message")
    outcome = DisabledProvider().propose(request)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(
                {
                    "path": self.path,
                    "body": body,
                    "request_id": self.headers.get("X-Gigmate-Request-Id"),
                }
            )
            value = {
                "choices": [{"message": {"content": outcome.proposal.model_dump_json()}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }
            payload = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("GIGMATE_LLM_ENDPOINT", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("GIGMATE_EXTRACTION_PROVIDER", "reviewed_llm")
        monkeypatch.setenv("GIGMATE_LLM_ALLOW_LIVE_ORIGIN", "1")
        monkeypatch.setenv("GIGMATE_WORKSPACE_TIMEZONE", "Asia/Hong_Kong")
        assert configured_for_live()
        result = ReviewedLLMProvider().propose(request)
        assert len(calls) == 1
        assert calls[0]["path"] == "/v1/chat/completions"
        assert calls[0]["request_id"] == result.request_id
        assert result.proposal.assignment.value == "needs_review"
        assert result.input_tokens == 100 and result.output_tokens == 20
        assert result.cost_usd is not None
        assert calls[0]["body"]["max_tokens"] == 1000
        assert "sk-fake-test" not in json.dumps(calls[0]["body"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
