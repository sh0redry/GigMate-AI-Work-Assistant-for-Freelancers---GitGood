"""Read-only delivery helpers for D; no replacement for C's pending commands."""

from datetime import UTC
from uuid import UUID

from fastapi import Depends, Query, Request, Response
from sqlalchemy import select

from gigmate.calendar_export import export_event
from gigmate.contracts import Conversation, Detail, Page, ReviewItem, WorkspaceCapabilities
from gigmate.db import CalendarRow, ConversationRow, Inbox, Job, WorkOrderRow
from gigmate.workorders import owned


def install(app, database, actor, detail, page, conversation_info):
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
        return Response(
            export_event(row.data, order.data),
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="gigmate-{event_id}.ics"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
