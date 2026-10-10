"""Account-owned sending routes; connector secrets remain server-side."""

import asyncio
import base64
from urllib.parse import unquote
from uuid import UUID

from fastapi import Depends, Header, Query, Request, Response
from sqlalchemy import select

from gigmate import waha_controls as controls
from gigmate import waha_send as sends
from gigmate.contracts import (
    Detail,
    Page,
    WahaSendActionView,
    WahaSendCapabilities,
    WahaSendDraftCommand,
    WahaSendPermissionCommand,
    WahaSendPermissionView,
    WahaSendPolicyCommand,
    WahaSendPolicyView,
    WahaSendRequestView,
    WahaSendRevisionCommand,
    WahaSendUnknownReviewCommand,
    WahaSendUploadView,
)
from gigmate.db import WahaSendAction, WahaSendPolicy


def install(app, database, setup_actor, detail, page, io_actor):
    def row_for(db, account, connection_id, *, lock=False):
        row = controls.owned(db, account, str(connection_id))
        return sends.locks(db, row.id) if lock else row

    def bounded_rows(db, model, row, cursor, limit, chat_id):
        query = select(model).where(model.connection_id == row.id)
        if chat_id:
            sends.chat_owned(db, row, str(chat_id))
            query = query.where(model.chat_id == str(chat_id))
        if cursor:
            try:
                last_id = base64.urlsafe_b64decode(cursor.encode()).decode()
                UUID(last_id)
            except (ValueError, UnicodeDecodeError):
                sends.fail("VALIDATION_FAILED", 422)
            query = query.where(model.id > last_id)
        return db.scalars(query.order_by(model.id).limit(limit + 1))

    base = "/api/v1/connectors/{connection_id}/sending"

    @app.get(base + "/requests/{request_key}", response_model=Detail[WahaSendRequestView])
    def request_lookup(
        connection_id: UUID,
        request_key: str,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(
            request, sends.request_view(db, row_for(db, account, connection_id), request_key)
        )

    @app.post(base + "/requests/{request_key}/cancel", response_model=Detail[WahaSendRequestView])
    def request_cancel(
        connection_id: UUID,
        request_key: str,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(
            request,
            sends.cancel_request(db, row_for(db, account, connection_id, lock=True), request_key),
        )

    @app.get(base + "/capabilities", response_model=Detail[WahaSendCapabilities])
    def capabilities(
        connection_id: UUID,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        row_for(db, account, connection_id)
        return detail(request, sends.capabilities())

    @app.get(base + "/permission", response_model=Detail[WahaSendPermissionView])
    def permission(
        connection_id: UUID,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(request, sends.permission_view(db, row_for(db, account, connection_id)))

    @app.post(base + "/permission", response_model=Detail[WahaSendPermissionView])
    def set_permission(
        connection_id: UUID,
        command: WahaSendPermissionCommand,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(
            request,
            sends.set_permission(db, row_for(db, account, connection_id, lock=True), command),
        )

    @app.get(base + "/context/{chat_id}", response_model=Detail[dict[str, int]])
    def context(
        connection_id: UUID,
        chat_id: UUID,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        row = row_for(db, account, connection_id)
        _, conv = sends.chat_owned(db, row, str(chat_id))
        return detail(
            request,
            {"context_version": conv.context_version, "control_version": row.control_version},
        )

    @app.post(
        base + "/uploads",
        status_code=201,
        response_model=Detail[WahaSendUploadView],
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
                },
            }
        },
    )
    async def upload(
        connection_id: UUID,
        request: Request,
        filename: str = Header(alias="X-File-Name", min_length=1, max_length=1536),
        mimetype: str = Header(alias="X-File-Mimetype", min_length=1, max_length=100),
        account=Depends(io_actor),
        db=Depends(database, scope="function"),
    ):
        row = row_for(db, account, connection_id)
        sends.enabled()
        # Authenticate and resolve ownership before accepting any private bytes.
        sends.upload_permission(db, row)
        try:
            filename = unquote(filename, errors="strict")
        except UnicodeDecodeError:
            sends.fail("SEND_UPLOAD_INVALID", 422)
        content = bytearray()
        try:
            async with asyncio.timeout(30):
                async for chunk in request.stream():
                    if len(content) + len(chunk) > sends.MAX_BYTES:
                        sends.fail("SEND_UPLOAD_TOO_LARGE", 413)
                    content.extend(chunk)
        except TimeoutError:
            sends.fail("SEND_UPLOAD_TIMEOUT", 408)
        db.expire_all()
        account = setup_actor(request, db)
        row = row_for(db, account, connection_id, lock=True)
        return detail(request, sends.upload(db, row, bytes(content), mimetype, filename))

    @app.get(base + "/uploads/{upload_id}/content", response_class=Response)
    def preview(
        connection_id: UUID,
        upload_id: UUID,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        row = row_for(db, account, connection_id)
        sends.upload_permission(db, row)
        asset, content = sends.read_upload(db, row, str(upload_id))
        # Office/unknown decoder formats are downloads, never active inline documents.
        safe = asset.mimetype.startswith(("image/", "audio/", "video/")) or asset.mimetype in {
            "application/pdf",
            "text/plain",
        }
        return Response(
            content,
            media_type=asset.mimetype,
            headers={
                "Content-Disposition": "inline" if safe else "attachment",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'",
            },
        )

    @app.post(base + "/drafts", status_code=201, response_model=Detail[WahaSendActionView])
    def draft(
        connection_id: UUID,
        command: WahaSendDraftCommand,
        request: Request,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(
            request,
            sends.create_draft(
                db,
                row_for(db, account, connection_id, lock=True),
                account,
                command,
                idempotency_key,
            ),
        )

    @app.get(base + "/actions", response_model=Page[WahaSendActionView])
    def actions(
        connection_id: UUID,
        request: Request,
        cursor: str | None = None,
        chat_id: UUID | None = None,
        limit: int = Query(30, ge=1, le=100),
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        row = row_for(db, account, connection_id)
        rows = bounded_rows(db, WahaSendAction, row, cursor, limit, chat_id)
        return page(request, rows, cursor, limit, sends.action_view)

    @app.get(base + "/actions/{action_id}", response_model=Detail[WahaSendActionView])
    def action(
        connection_id: UUID,
        action_id: UUID,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(
            request,
            sends.action_view(
                sends.action_owned(db, row_for(db, account, connection_id), str(action_id))
            ),
        )

    @app.post(base + "/actions/{action_id}/approve", response_model=Detail[WahaSendActionView])
    def approve(
        connection_id: UUID,
        action_id: UUID,
        command: WahaSendRevisionCommand,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(
            request,
            sends.approve(
                db,
                row_for(db, account, connection_id, lock=True),
                account,
                str(action_id),
                command.expected_revision,
            ),
        )

    @app.post(base + "/actions/{action_id}/cancel", response_model=Detail[WahaSendActionView])
    def cancel(
        connection_id: UUID,
        action_id: UUID,
        command: WahaSendRevisionCommand,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(
            request,
            sends.cancel(
                db,
                row_for(db, account, connection_id, lock=True),
                str(action_id),
                command.expected_revision,
            ),
        )

    @app.post(base + "/actions/{action_id}/reconcile", response_model=Detail[WahaSendActionView])
    def reconcile(
        connection_id: UUID,
        action_id: UUID,
        command: WahaSendRevisionCommand,
        request: Request,
        account=Depends(io_actor),
        db=Depends(database, scope="function"),
    ):
        result = sends.reconcile(
            db, row_for(db, account, connection_id), str(action_id), command.expected_revision
        )
        db.expire_all()
        setup_actor(request, db)
        return detail(request, result)

    @app.post(
        base + "/actions/{action_id}/review-unknown", response_model=Detail[WahaSendActionView]
    )
    def review_unknown(
        connection_id: UUID,
        action_id: UUID,
        command: WahaSendUnknownReviewCommand,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(
            request,
            sends.review_unknown(
                db, row_for(db, account, connection_id, lock=True), account, str(action_id), command
            ),
        )

    @app.post(base + "/policies", status_code=201, response_model=Detail[WahaSendPolicyView])
    def policy(
        connection_id: UUID,
        command: WahaSendPolicyCommand,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        return detail(
            request,
            sends.create_policy(
                db, row_for(db, account, connection_id, lock=True), account, command
            ),
        )

    @app.get(base + "/policies", response_model=Page[WahaSendPolicyView])
    def policies(
        connection_id: UUID,
        request: Request,
        cursor: str | None = None,
        chat_id: UUID | None = None,
        limit: int = Query(30, ge=1, le=100),
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        row = row_for(db, account, connection_id)
        return page(
            request,
            bounded_rows(db, WahaSendPolicy, row, cursor, limit, chat_id),
            cursor,
            limit,
            sends.policy_view,
        )

    @app.post(base + "/policies/{policy_id}/revoke", response_model=Detail[WahaSendPolicyView])
    def revoke_policy(
        connection_id: UUID,
        policy_id: UUID,
        command: WahaSendRevisionCommand,
        request: Request,
        account=Depends(setup_actor),
        db=Depends(database, scope="function"),
    ):
        row = row_for(db, account, connection_id, lock=True)
        p = sends.policy_owned(db, row, str(policy_id))
        if p.version != command.expected_revision:
            sends.fail("SEND_POLICY_VERSION_CONFLICT")
        p.enabled, p.version = False, p.version + 1
        return detail(request, sends.policy_view(p))
