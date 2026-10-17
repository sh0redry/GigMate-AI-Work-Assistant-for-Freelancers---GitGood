"""Read-only delivery helpers for D; mutations remain in C's canonical services."""

from datetime import UTC
from uuid import UUID

from fastapi import Depends, Query, Request, Response
from sqlalchemy import select

from gigmate.calendar_export import export_event
from gigmate.contracts import (
    Conversation,
    Detail,
    InspectWorkOrderCommand,
    Page,
    ReviewItem,
    WorkOrder,
    WorkspaceCapabilities,
)
from gigmate.db import (
    CalendarRow,
    ConversationOrder,
    ConversationRow,
    Inbox,
    Job,
    MessageRow,
    WorkOrderRow,
)
from gigmate.errors import BusinessError
from gigmate.workorders import command_cache, owned


def require_export_sources(db, account_id, order):
    """Check actual current evidence, not just two matching historical snapshots."""
    conversations = (
        select(ConversationRow.id)
        .join(ConversationOrder, ConversationOrder.conversation_id == ConversationRow.id)
        .where(
            ConversationOrder.work_order_id == order.id,
            ConversationRow.account_id == account_id,
            ConversationRow.allowlisted.is_(True),
        )
    )
    fields = [order.data["fields"]["schedule"]]
    address = order.data["fields"]["address"]
    if address["status"] == "confirmed" and isinstance(address["value"], str):
        fields.append(address)
    for field in fields:
        if not field["sources"]:
            raise BusinessError(409, "APPROVAL_STALE", "Review the appointment sources first")
        for source in field["sources"]:
            latest = db.scalar(
                select(MessageRow)
                .where(
                    MessageRow.account_id == account_id,
                    MessageRow.id == source["message_id"],
                    MessageRow.conversation_id.in_(conversations),
                )
                .order_by(MessageRow.revision.desc())
            )
            if (
                latest is None
                or latest.revision != source["message_revision"]
                or latest.data["revoked"]
                or latest.data["direction"] != "incoming"
            ):
                raise BusinessError(409, "APPROVAL_STALE", "Review the appointment sources first")


def install(app, database, actor, detail, page, conversation_info):
    @app.post("/api/v1/work-order-command-results/{key}/inspect", response_model=Detail[WorkOrder])
    def inspect_command(
        key: UUID,
        command: InspectWorkOrderCommand,
        request: Request,
        account=Depends(actor),
        db=Depends(database),
    ):
        # POST carries the typed original body and requires CSRF/account locking.
        # Only the immutable cache is read: absence never authorizes a new write.
        scope = (
            "create_work_order"
            if command.kind == "create"
            else f"status:{command.order_id}"
            if command.kind == "status"
            else f"confirm:{command.order_id}:{command.change_id}"
        )
        _, cached = command_cache(
            db, account.id, scope, str(key), command.command.model_dump(mode="json")
        )
        if cached is None:
            raise BusinessError(
                409,
                "COMMAND_RESULT_PENDING",
                "No completed receipt is available; keep the original command identity",
            )
        return detail(request, cached.data)

    @app.get("/api/v1/workspace-capabilities", response_model=Detail[WorkspaceCapabilities])
    def capabilities(request: Request, account=Depends(actor)):
        return detail(request, WorkspaceCapabilities())

    @app.get("/api/v1/conversations", response_model=Page[Conversation])
    def conversations(
        request: Request,
        cursor: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        account=Depends(actor),
        db=Depends(database),
    ):
        return page(
            request,
            db.scalars(
                select(ConversationRow).where(
                    ConversationRow.account_id == account.id, ConversationRow.allowlisted.is_(True)
                )
            ),
            cursor,
            limit,
            lambda row: conversation_info(UUID(row.id), request, account, db)["data"],
        )

    @app.get("/api/v1/review-items", response_model=Page[ReviewItem])
    def review_items(
        request: Request,
        cursor: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        account=Depends(actor),
        db=Depends(database),
    ):
        allowed = {
            row.id: row.context_version
            for row in db.scalars(
                select(ConversationRow).where(
                    ConversationRow.account_id == account.id, ConversationRow.allowlisted.is_(True)
                )
            )
        }
        codes = {
            "LIVE_EXTRACTION_PENDING",
            "EXTRACTION_NEEDS_REVIEW",
            "ASSIGNMENT_NEEDS_REVIEW",
            "PROCESSING_FAILED",
            "RETRY_EXHAUSTED",
        }
        rows, shown = [], {}
        for job, inbox in db.execute(
            select(Job, Inbox)
            .join(Inbox, Job.event_id == Inbox.id)
            .where(
                Job.account_id == account.id,
                Inbox.account_id == account.id,
                Job.error_code.in_(codes),
            )
        ):
            conversation_id = inbox.payload.get("conversation_id")
            if conversation_id not in allowed:
                continue
            rows.append(job)
            shown[job.id] = {
                "id": job.id,
                "conversation_id": conversation_id,
                "message_id": inbox.payload.get("payload", {}).get("message_id"),
                "context_version": inbox.context_version,
                "current_context_version": allowed[conversation_id],
                "reason": job.error_code,
                "state": job.state,
                "observed_at": inbox.received_at.replace(tzinfo=UTC)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        return page(request, rows, cursor, limit, lambda row: shown[row.id])

    @app.get(
        "/api/v1/calendar-events/{event_id}.ics",
        response_class=Response,
        responses={200: {"content": {"text/calendar": {"schema": {"type": "string"}}}}},
    )
    def download_calendar(
        event_id: UUID,
        account=Depends(actor),
        db=Depends(database),
    ):
        row = owned(db, CalendarRow, str(event_id), account.id)
        order = owned(db, WorkOrderRow, row.work_order_id, account.id)
        content = export_event(row.data, order.data)
        require_export_sources(db, account.id, order)
        return Response(
            content,
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="gigmate-{event_id}.ics"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
