"""Fictional product acceptance: no connector or paid vendor is contacted."""

import copy
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, select
from test_create_order import create, future
from test_extraction import _build_reschedule_request
from test_extraction_batch3 import _configure
from test_waha_controls import ingress as ingress  # noqa: F401
from test_waha_controls import path
from test_waha_controls import setup as control_setup  # noqa: F401
from test_waha_ingress import post, raw

from gigmate.contracts import ChangeProposal
from gigmate.db import (
    Account,
    ActionRow,
    AuditRow,
    CalendarRow,
    CommandResult,
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


@pytest.mark.parametrize("operation", ["unchanged", "pause", "pause-resume"])
def test_inflight_text_respects_real_control_routes_and_retains_submission_fence(
    request, operation
):
    setup = request.getfixturevalue("control_setup")
    client, factory, headers, binding, _ = setup
    incoming_setup = (client, factory, None, headers, binding, None)
    response = post(incoming_setup, raw())
    assert response.status_code == 200, response.text
    observed = []

    class DuringCall(DisabledProvider):
        calls = 0

        def propose(self, request):
            self.calls += 1
            for verb, version in (
                []
                if operation == "unchanged"
                else [("pause", 0)] + ([("resume", 1)] if operation == "pause-resume" else [])
            ):
                response = client.post(
                    path(setup, verb), json={"expected_version": version}, headers=headers
                )
                observed.append(response.status_code)
            return super().propose(request)

    selected = DuringCall()
    _reset_provider_for_testing(selected)
    try:
        assert run_once(factory)
        assert observed == (
            [] if operation == "unchanged" else [200, 200] if operation == "pause-resume" else [200]
        )
        with factory() as db:
            job = db.scalar(select(Job))
            assert job.model_request_id
            assert (
                job.error_code
                == {
                    "unchanged": "EXTRACTION_NEEDS_REVIEW",
                    "pause": "CONSENT_REVOKED",
                    "pause-resume": "SOURCE_SUPERSEDED",
                }[operation]
            )
            assert db.scalar(select(func.count()).select_from(Proposal)) == int(
                operation == "unchanged"
            )
        assert not run_once(factory)
        assert selected.calls == 1
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
        assert job.processing_ms is not None and job.completion_latency_ms is not None
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


@pytest.mark.parametrize("same_key", [False, True])
def test_postgres_concurrent_suggestion_creation_is_atomic_and_idempotent(signed_in, same_key):
    client, factory, engine, headers = signed_in
    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrent account-lock acceptance requires PostgreSQL")
    proposed, context = suggestion(factory)
    barrier = Barrier(2)
    seen_connections = set()
    keys = [str(uuid4()), str(uuid4())]
    if same_key:
        keys[1] = keys[0]

    def before_lock(conn, cursor, statement, parameters, execution_context, executemany):
        if (
            "accounts" in statement
            and "FOR UPDATE" in statement
            and id(conn) not in seen_connections
        ):
            seen_connections.add(id(conn))
            # Both real HTTP requests reach the lock before either executes it.
            barrier.wait(timeout=10)

    with factory() as db:
        before = db.scalar(select(func.count()).select_from(WorkOrderRow))
    sqlalchemy_event.listen(engine, "before_cursor_execute", before_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(
                    lambda key: create(
                        client,
                        headers,
                        key=key,
                        from_proposal_id=proposed,
                        expected_context_version=context,
                    ),
                    keys,
                )
            )
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", before_lock)
    assert sorted(response.status_code for response in responses) == (
        [201, 201] if same_key else [201, 409]
    ), [response.text for response in responses]
    if same_key:
        assert responses[0].json()["data"] == responses[1].json()["data"]
    else:
        rejected = next(response for response in responses if response.status_code == 409)
        assert rejected.json()["error"]["code"] == "VERSION_CONFLICT"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(WorkOrderRow)) == before + 1
        assert db.scalar(select(func.count()).select_from(ProposalDecision)) == 1
        assert db.scalar(select(func.count()).select_from(CommandResult)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRow)
                .where(AuditRow.data["operation"].as_string() == "create_work_order")
            )
            == 1
        )


def test_suggestion_unique_fence_returns_409_and_rolls_back_losing_order(signed_in, monkeypatch):
    from gigmate import product_commands

    client, factory, _, headers = signed_in
    proposed, context = suggestion(factory)
    assert (
        create(
            client, headers, from_proposal_id=proposed, expected_context_version=context
        ).status_code
        == 201
    )
    with factory() as db:
        models = [
            WorkOrderRow,
            CalendarRow,
            TaskRow,
            ActionRow,
            AuditRow,
            CommandResult,
            ProposalDecision,
        ]
        before = {model: db.scalar(select(func.count()).select_from(model)) for model in models}

    # Exercise the DB fence independently of the earlier read/lock guard.
    monkeypatch.setattr(
        product_commands,
        "bind_suggestion",
        lambda db, account_id, command: db.get(Proposal, proposed),
    )
    response = create(
        client,
        headers,
        from_proposal_id=proposed,
        expected_context_version=context,
        schedule=future(),
        address="Synthetic address",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "VERSION_CONFLICT"
    with factory() as db:
        assert {
            model: db.scalar(select(func.count()).select_from(model)) for model in models
        } == before


def history(factory, count=101):
    proposed, _ = suggestion(factory)
    with factory.begin() as db:
        original = db.get(Proposal, proposed)
        value = {
            column.name: copy.deepcopy(getattr(original, column.name))
            for column in Proposal.__table__.columns
            if column.name != "id"
        }
        ids = [proposed]
        for index in range(count - 1):
            identity = uid(1000 + index)
            db.add(Proposal(id=identity, **copy.deepcopy(value)))
            ids.append(identity)
    return sorted(ids)


def test_suggestions_load_limit_plus_one_and_pages_never_repeat_or_omit(signed_in):
    client, factory, _, _ = signed_in
    expected = history(factory)
    loaded = []

    def load(row, context):
        loaded.append(row.id)

    sqlalchemy_event.listen(Proposal, "load", load)
    try:
        response = client.get("/api/v1/new-order-suggestions?limit=1")
    finally:
        sqlalchemy_event.remove(Proposal, "load", load)
    assert response.status_code == 200, response.text
    assert len(loaded) <= 2
    page = response.json()
    seen = [item["id"] for item in page["items"]]
    cursors = set()
    while page["next_cursor"]:
        cursor = page["next_cursor"]
        assert cursor not in cursors
        cursors.add(cursor)
        response = client.get(
            "/api/v1/new-order-suggestions", params={"limit": 7, "cursor": cursor}
        )
        assert response.status_code == 200, response.text
        page = response.json()
        seen.extend(item["id"] for item in page["items"])
    assert seen == expected


@pytest.mark.parametrize("case", ["no_suggestion", "consumed", "stale"])
def test_suggestions_skip_ineligible_history_with_bounded_scans(signed_in, case):
    client, factory, _, _ = signed_in
    identities = history(factory)
    with factory.begin() as db:
        for identity in identities:
            row = db.get(Proposal, identity)
            if case == "no_suggestion":
                row.proposal = {**row.proposal, "new_work_order": None}
            elif case == "stale":
                row.context_version -= 1
        if case == "consumed":
            first = db.get(Proposal, identities[0])
            db.add(
                ProposalDecision(
                    event_id=first.event_id,
                    proposal_id=first.id,
                    account_id=uid(1),
                    work_order_id=uid(3),
                )
            )
    loaded = []

    def load(row, context):
        loaded.append(row.id)

    sqlalchemy_event.listen(Proposal, "load", load)
    try:
        response = client.get("/api/v1/new-order-suggestions?limit=1")
    finally:
        sqlalchemy_event.remove(Proposal, "load", load)
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    if case == "stale":
        assert len(loaded) <= 10
        assert response.json()["next_cursor"]
        with factory.begin() as db:
            last = db.get(Proposal, identities[-1])
            last.context_version = db.get(ConversationRow, uid(2)).context_version
        page = response.json()
        seen = []
        for _ in range(20):
            if not page["next_cursor"]:
                break
            page = client.get(
                "/api/v1/new-order-suggestions", params={"limit": 1, "cursor": page["next_cursor"]}
            ).json()
            seen.extend(item["id"] for item in page["items"])
        assert seen == [identities[-1]]
        assert page["next_cursor"] is None
    else:
        assert loaded == []
        assert response.json()["next_cursor"] is None


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
