"""Merchant-reviewed suggestion consumption and task decisions; no external effects."""

import base64
import copy
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from gigmate.contracts import (
    AssignMessageCommand,
    Detail,
    DismissSuggestionCommand,
    MessageAssignmentResult,
    NewOrderSuggestionView,
    Page,
    SetTaskStatusCommand,
    Task,
    WorkspaceQuery,
    WorkspaceQueryResult,
)
from gigmate.db import (
    ConversationRow,
    Inbox,
    Job,
    JobAssignment,
    MessageRow,
    Proposal,
    ProposalDecision,
    TaskRow,
)
from gigmate.errors import BusinessError
from gigmate.workorders import (
    REVIEWABLE,
    audit_row,
    authorized_order_conversation,
    command_cache,
    locked_order,
    now_text,
    owned,
    save_result,
    validate,
)


def available_suggestion_job(account_id, event_id):
    """One unhandled review decision, shared by listing and creation checks."""
    return select(Job).where(
        Job.account_id == account_id,
        Job.event_id == event_id,
        Job.state == "completed",
        Job.error_code.in_(REVIEWABLE),
        ~select(JobAssignment.job_id).where(JobAssignment.job_id == Job.id).exists(),
    )


def current_suggestion(db, account_id, proposal_id):
    row = owned(db, Proposal, proposal_id, account_id)
    conversation = owned(db, ConversationRow, row.conversation_id, account_id)
    inbox = owned(db, Inbox, row.event_id, account_id)
    if not conversation.allowlisted:
        raise BusinessError(403, "CONSENT_REVOKED", "Conversation processing is paused")
    if row.context_version != conversation.context_version:
        raise BusinessError(409, "APPROVAL_STALE", "Suggestion context changed")
    suggestion = row.proposal.get("new_work_order")
    if not suggestion or row.assignment != "needs_review" or row.work_order_id is not None:
        raise BusinessError(409, "VERSION_CONFLICT", "No new-order suggestion is available")
    if db.get(ProposalDecision, row.event_id) is not None:
        raise BusinessError(409, "VERSION_CONFLICT", "This message already created an order")
    if db.scalar(available_suggestion_job(account_id, row.event_id)) is None:
        raise BusinessError(409, "VERSION_CONFLICT", "This message no longer needs a decision")
    payload = inbox.payload
    if (
        payload.get("conversation_id") != conversation.id
        or inbox.context_version != row.context_version
    ):
        raise BusinessError(409, "APPROVAL_STALE", "Suggestion event changed")
    refs = [
        {
            "message_id": payload["payload"]["message_id"],
            "message_revision": payload["message_revision"],
        }
    ]
    for field in suggestion["fields"]:
        refs.extend(field["sources"])
    refs = list({(ref["message_id"], ref["message_revision"]): ref for ref in refs}.values())
    for ref in refs:
        latest = db.scalar(
            select(MessageRow)
            .where(
                MessageRow.id == ref["message_id"],
                MessageRow.account_id == account_id,
                MessageRow.conversation_id == conversation.id,
            )
            .order_by(MessageRow.revision.desc())
        )
        if (
            latest is None
            or latest.revision != ref["message_revision"]
            or latest.data["revoked"]
            or latest.data["direction"] != "incoming"
        ):
            raise BusinessError(409, "APPROVAL_STALE", "Suggestion source changed")
    return row, refs


def bind_suggestion(db, account_id, command):
    if not command.from_proposal_id:
        return None
    row, _ = current_suggestion(db, account_id, command.from_proposal_id)
    if (
        row.conversation_id != command.conversation_id
        or row.context_version != command.expected_context_version
    ):
        raise BusinessError(409, "VERSION_CONFLICT", "Refresh and review the suggestion")
    return row


def consume_suggestion(db, account_id, row, work_order_id):
    if row is None:
        return
    try:
        # The caller holds the account lock; keep the unique constraint as a
        # final fence, returning a business conflict if another writer won.
        with db.begin_nested():
            db.add(
                ProposalDecision(
                    event_id=row.event_id,
                    proposal_id=row.id,
                    account_id=account_id,
                    work_order_id=work_order_id,
                )
            )
            db.flush()
    except IntegrityError:
        if (
            db.get(ProposalDecision, row.event_id) is not None
            or db.scalar(select(ProposalDecision).where(ProposalDecision.proposal_id == row.id))
            is not None
        ):
            raise BusinessError(
                409, "VERSION_CONFLICT", "This message already created an order"
            ) from None
        raise
    job = db.scalar(select(Job).where(Job.event_id == row.event_id, Job.account_id == account_id))
    if job and job.state == "completed":
        job.error_code = "NEW_ORDER_REVIEWED"


def task_status(db, account, task_id, command, key, request_id):
    scope = f"task:{task_id}"
    digest, cached = command_cache(db, account.id, scope, key, command.model_dump())
    if cached:
        return cached.data
    task = owned(db, TaskRow, task_id, account.id)
    order = locked_order(db, account, task.work_order_id, command.expected_version)
    if task.data["state"] != command.expected_state:
        raise BusinessError(409, "VERSION_CONFLICT", "Task state changed")
    for ref in task.data["sources"]:
        source = db.scalar(
            select(MessageRow)
            .where(
                MessageRow.id == ref["message_id"],
                MessageRow.account_id == account.id,
            )
            .order_by(MessageRow.revision.desc())
        )
        if source is None or source.revision != ref["message_revision"] or source.data["revoked"]:
            raise BusinessError(409, "APPROVAL_STALE", "Task source changed")
        authorized_order_conversation(db, account, order, source.conversation_id)
    if command.state == "completed":
        for dependency_id in task.data["depends_on"]:
            dependency = owned(db, TaskRow, dependency_id, account.id)
            if dependency.work_order_id != order.id or dependency.data["state"] != "completed":
                raise BusinessError(409, "DEPENDENCY_OPEN", "Complete the prerequisite first")
    value = copy.deepcopy(order.data)
    value["version"] += 1
    value["updated_at"] = now_text()
    for item in value.get("requirements") or []:
        if item.get("task_id") == task.id and item["status"] == "open":
            item["status"] = "done" if command.state == "completed" else "cancelled"
    from gigmate.contracts import WorkOrder

    order.data = validate(WorkOrder, value)
    task.data = validate(
        Task, {**task.data, "state": command.state, "work_order_version": value["version"]}
    )
    db.add(audit_row(account.id, order.id, f"task_{command.state}", request_id))
    save_result(db, account.id, scope, key, digest, task.data)
    return task.data


def query_workspace(db, account_id, question, now=None):
    """A bounded read-only intent helper. Never claims to understand arbitrary questions."""
    from gigmate import scheduling, summary

    zone = ZoneInfo(scheduling.settings(db, account_id).timezone)
    day = (now or datetime.now(UTC)).astimezone(zone).date()
    q = question.strip().lower().rstrip("?？。.!！")
    intents = {
        "今天有什么安排": "today",
        "今日有咩安排": "today",
        "what is on today": "today",
        "明天有什么安排": "tomorrow",
        "聽日有咩安排": "tomorrow",
        "what is on tomorrow": "tomorrow",
        "哪些在等客户": "waiting",
        "邊啲等緊客人": "waiting",
        "what is waiting for customers": "waiting",
        "有什么待决定": "open_items",
        "有咩要我決定": "open_items",
        "what needs my decision": "open_items",
    }
    intent = intents.get(q, "unsupported")
    if intent == "tomorrow":
        day += timedelta(days=1)
    if intent == "unsupported":
        return {"supported": False, "intent": intent, "day": day, "items": []}
    data = summary.build(db, account_id, day)
    key = {
        "today": "today",
        "tomorrow": "today",
        "waiting": "waiting_for_customer",
        "open_items": "needs_decision",
    }[intent]
    return {"supported": True, "intent": intent, "day": day, "items": data[key]}


def dismiss_suggestion(db, account, proposal_id, command, key, request_id):
    """Discard one AI new-order suggestion without creating an order.

    This is the existing "not business" decision on the message that produced
    the suggestion (``assign_message`` with ``dismiss``), so it shares its
    idempotency receipt, context-version check and audit row. Afterwards the
    suggestion is no longer listed and cannot be used to create an order.
    """
    from gigmate.workorders import assign_message

    row = owned(db, Proposal, proposal_id, account.id)
    if row.assignment != "needs_review" or not row.proposal.get("new_work_order"):
        raise BusinessError(404, "NOT_FOUND", "Suggestion not found")
    job = db.scalar(select(Job).where(Job.account_id == account.id, Job.event_id == row.event_id))
    if job is None:
        raise BusinessError(404, "NOT_FOUND", "Suggestion not found")
    return assign_message(
        db,
        account,
        job.id,
        AssignMessageCommand(
            action="dismiss", expected_context_version=command.expected_context_version
        ),
        key,
        request_id,
    )


def install(app, database, actor, detail, page):
    @app.post(
        "/api/v1/new-order-suggestions/{proposal_id}/dismiss",
        response_model=Detail[MessageAssignmentResult],
    )
    def dismiss_new_order_suggestion(
        proposal_id: UUID,
        command: DismissSuggestionCommand,
        request: Request,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        account=Depends(actor),
        db=Depends(database),
    ):
        return detail(
            request,
            dismiss_suggestion(
                db, account, str(proposal_id), command, idempotency_key, request.state.request_id
            ),
        )

    @app.get("/api/v1/new-order-suggestions", response_model=Page[NewOrderSuggestionView])
    def suggestions(
        request: Request,
        cursor: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        account=Depends(actor),
        db=Depends(database),
    ):
        try:
            last_id = base64.urlsafe_b64decode(cursor.encode()).decode() if cursor else ""
            if last_id:
                UUID(last_id)
        except (ValueError, UnicodeDecodeError):
            raise BusinessError(422, "VALIDATION_FAILED", "Invalid cursor") from None

        # Filter obvious candidates in SQL and inspect only bounded batches.
        # Source/context validation still happens in current_suggestion; it is
        # deliberately not replaced by a JSON shortcut.
        batch_size = max(2, min(limit + 1, 100))
        scan_id = last_id
        result = []
        has_more = False
        for _ in range(5):
            query = (
                select(Proposal)
                .where(
                    Proposal.account_id == account.id,
                    Proposal.assignment == "needs_review",
                    Proposal.work_order_id.is_(None),
                    available_suggestion_job(account.id, Proposal.event_id).exists(),
                    Proposal.proposal["new_work_order"].as_string().is_not(None),
                    ~select(ProposalDecision.event_id)
                    .where(ProposalDecision.event_id == Proposal.event_id)
                    .exists(),
                    Proposal.id > scan_id,
                )
                .order_by(Proposal.id)
                .limit(batch_size)
            )
            batch = list(db.scalars(query))
            has_more = len(batch) == batch_size
            for row in batch:
                scan_id = row.id
                try:
                    current, refs = current_suggestion(db, account.id, row.id)
                except BusinessError:
                    continue
                result.append(
                    {
                        "id": current.id,
                        "conversation_id": current.conversation_id,
                        "context_version": current.context_version,
                        "suggestion": current.proposal["new_work_order"],
                        "sources": refs,
                        "created_at": current.created_at.replace(tzinfo=UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    }
                )
                if len(result) >= limit + 1:
                    break
            if len(result) >= limit + 1 or not has_more:
                break
        visible = result[:limit]
        if len(result) > limit:
            next_cursor = base64.urlsafe_b64encode(visible[-1]["id"].encode()).decode()
        elif has_more:
            next_cursor = base64.urlsafe_b64encode(scan_id.encode()).decode()
        else:
            next_cursor = None
        return {
            "items": visible,
            "next_cursor": next_cursor,
            "request_id": request.state.request_id,
        }

    @app.post("/api/v1/tasks/{task_id}/status", response_model=Detail[Task])
    def update_task(
        task_id: UUID,
        command: SetTaskStatusCommand,
        request: Request,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        account=Depends(actor),
        db=Depends(database),
    ):
        return detail(
            request,
            task_status(
                db, account, str(task_id), command, idempotency_key, request.state.request_id
            ),
        )

    @app.post("/api/v1/workspace-query", response_model=Detail[WorkspaceQueryResult])
    def query(
        command: WorkspaceQuery, request: Request, account=Depends(actor), db=Depends(database)
    ):
        return detail(request, query_workspace(db, account.id, command.question))
