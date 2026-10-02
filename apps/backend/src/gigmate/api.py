import base64
import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from gigmate import identity
from gigmate.config import COOKIE_SECURE, TRUSTED_ORIGINS
from gigmate.contracts import (
    CalendarEvent,
    ConfirmChangeCommand,
    ConnectorReceipt,
    ConnectorStatus,
    Conversation,
    ConversationMessage,
    Detail,
    Model,
    Page,
    RequirementChange,
    Task,
    Text,
    WorkOrder,
)
from gigmate.db import (
    ChangeRow,
    ConversationOrder,
    ConversationRow,
    LoginSession,
    MessageRow,
    Session,
    TaskRow,
    WahaChat,
    WahaConnection,
    WorkOrderRow,
)
from gigmate.errors import BusinessError
from gigmate.messaging import ingest, replay_event
from gigmate.planning import conflicts
from gigmate.waha_adapter import AdapterError
from gigmate.waha_ingress import binding_for, receive, status_view
from gigmate.waha_probe import MAX_BODY, _non_json_constant, _pairs, verify_hmac
from gigmate.workorders import command_cache, confirm, owned, save_result

app = FastAPI(title="GigMate replay skeleton", version="0.2.0")


class LoginCommand(Model):
    username: Text
    password: Annotated[str, Field(min_length=1, max_length=128)]


class LoginResult(Model):
    account_id: str
    username: str
    csrf_token: str
    mode: Literal["synthetic_replay"]


class ReplayCommand(Model):
    scenario: Literal["reschedule", "available"]


class ReplayResult(Model):
    event_id: str
    duplicate: bool
    context_version: int


class ChangeView(RequirementChange):
    context_version: int
    conflict_ids: list[str]


class ConnectionInfo(Model):
    mode: Literal["synthetic_replay"]
    connector: Literal["replay"]
    live_connected: Literal[False]


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(BusinessError)
async def business_error(request: Request, exc: BusinessError):
    return JSONResponse(
        status_code=exc.status,
        content={
            "error": {"code": exc.code, "message": exc.message, "details": {}},
            "request_id": request.state.request_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, _exc):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "Invalid request shape",
                "details": {},
            },
            "request_id": request.state.request_id,
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, _exc):
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "DATABASE_UNAVAILABLE",
                "message": "Retry after checking connector delivery",
                "details": {},
            },
            "request_id": request.state.request_id,
        },
    )


def database():
    with Session.begin() as db:
        yield db


def origin_check(request):
    origin = request.headers.get("origin")
    if origin and origin not in TRUSTED_ORIGINS:
        raise BusinessError(403, "CSRF_REJECTED", "Untrusted origin")


def actor(request: Request, db=Depends(database)):
    mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
    if mutation:
        origin_check(request)
    return identity.authenticate(
        db, request.cookies.get("gigmate_session"), request.headers.get("X-CSRF-Token"), mutation
    )


def detail(request, data):
    return {"data": data, "request_id": request.state.request_id}


def page(request, rows, cursor, limit, mapper=lambda row: row.data):
    try:
        last_id = base64.urlsafe_b64decode(cursor.encode()).decode() if cursor else ""
        if last_id:
            UUID(last_id)
    except (ValueError, UnicodeDecodeError):
        raise BusinessError(422, "VALIDATION_FAILED", "Invalid cursor") from None
    rows = sorted((row for row in rows if row.id > last_id), key=lambda row: row.id)
    current = rows[:limit]
    next_cursor = (
        base64.urlsafe_b64encode(current[-1].id.encode()).decode() if len(rows) > limit else None
    )
    return {
        "items": [mapper(row) for row in current],
        "next_cursor": next_cursor,
        "request_id": request.state.request_id,
    }


@app.get("/health")
def health(db=Depends(database)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "mode": "synthetic_replay"}


@app.post("/api/v1/auth/login", response_model=Detail[LoginResult])
def login(command: LoginCommand, request: Request, response: Response, db=Depends(database)):
    origin_check(request)
    account, token, csrf = identity.login(db, command.username, command.password)
    response.set_cookie(
        "gigmate_session",
        token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        max_age=8 * 3600,
        path="/",
    )
    return detail(
        request,
        {
            "account_id": account.id,
            "username": account.username,
            "csrf_token": csrf,
            "mode": "synthetic_replay",
        },
    )


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, account=Depends(actor), db=Depends(database)):
    db.delete(db.get(LoginSession, identity.digest(request.cookies["gigmate_session"])))
    response.delete_cookie("gigmate_session", path="/")
    return detail(request, {"signed_out": True})


@app.get("/api/v1/work-orders", response_model=Page[WorkOrder])
def orders(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    account=Depends(actor),
    db=Depends(database),
):
    return page(
        request,
        db.scalars(select(WorkOrderRow).where(WorkOrderRow.account_id == account.id)),
        cursor,
        limit,
    )


@app.get("/api/v1/work-orders/{order_id}", response_model=Detail[WorkOrder])
def order_detail(order_id: UUID, request: Request, account=Depends(actor), db=Depends(database)):
    return detail(request, owned(db, WorkOrderRow, str(order_id), account.id).data)


@app.get("/api/v1/work-orders/{order_id}/changes", response_model=Page[ChangeView])
def changes(
    order_id: UUID,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    account=Depends(actor),
    db=Depends(database),
):
    owned(db, WorkOrderRow, str(order_id), account.id)
    rows = db.scalars(
        select(ChangeRow).where(
            ChangeRow.account_id == account.id, ChangeRow.work_order_id == str(order_id)
        )
    )
    return page(
        request,
        rows,
        cursor,
        limit,
        lambda row: {
            **row.data,
            "context_version": row.context_version,
            "conflict_ids": conflicts(db, account.id, str(order_id), row.data["new_value"]),
        },
    )


@app.post(
    "/api/v1/work-orders/{order_id}/changes/{change_id}/confirm", response_model=Detail[WorkOrder]
)
def confirm_change(
    order_id: UUID,
    change_id: UUID,
    command: ConfirmChangeCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    account=Depends(actor),
    db=Depends(database),
):
    return detail(
        request,
        confirm(
            db,
            account,
            str(order_id),
            str(change_id),
            command,
            idempotency_key,
            request.state.request_id,
        ),
    )


@app.get("/api/v1/conversations/{conversation_id}", response_model=Detail[Conversation])
def conversation_info(
    conversation_id: UUID, request: Request, account=Depends(actor), db=Depends(database)
):
    row = owned(db, ConversationRow, str(conversation_id), account.id)
    if not row.allowlisted:
        raise BusinessError(404, "NOT_FOUND", "Conversation not found")
    ids = list(
        db.scalars(
            select(ConversationOrder.work_order_id).where(
                ConversationOrder.conversation_id == row.id
            )
        )
    )
    chat = db.scalar(
        select(WahaChat)
        .join(WahaConnection)
        .where(WahaChat.conversation_id == row.id, WahaConnection.account_id == account.id)
    )
    return detail(
        request,
        {
            "id": row.id,
            "account_id": account.id,
            "provider_conversation_id": chat.provider_chat_id if chat else f"synthetic:{row.id}",
            "context_version": row.context_version,
            "work_order_ids": ids,
        },
    )


@app.get(
    "/api/v1/conversations/{conversation_id}/messages", response_model=Page[ConversationMessage]
)
def messages(
    conversation_id: UUID,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    account=Depends(actor),
    db=Depends(database),
):
    conversation = owned(db, ConversationRow, str(conversation_id), account.id)
    if not conversation.allowlisted:
        raise BusinessError(404, "NOT_FOUND", "Conversation not found")
    latest = {}
    for row in db.scalars(
        select(MessageRow)
        .where(MessageRow.account_id == account.id, MessageRow.conversation_id == conversation.id)
        .order_by(MessageRow.revision)
    ):
        latest[row.id] = row
    return page(request, latest.values(), cursor, limit)


@app.get("/api/v1/tasks", response_model=Page[Task])
def tasks(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    account=Depends(actor),
    db=Depends(database),
):
    return page(
        request, db.scalars(select(TaskRow).where(TaskRow.account_id == account.id)), cursor, limit
    )


@app.get("/api/v1/calendar-events", response_model=Page[CalendarEvent])
def calendar(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    account=Depends(actor),
    db=Depends(database),
):
    from gigmate.db import CalendarRow

    return page(
        request,
        db.scalars(select(CalendarRow).where(CalendarRow.account_id == account.id)),
        cursor,
        limit,
    )


@app.get("/api/v1/connection-status", response_model=Detail[ConnectionInfo])
def connection(request: Request, account=Depends(actor)):
    return detail(
        request, {"mode": "synthetic_replay", "connector": "replay", "live_connected": False}
    )


@app.get("/api/v1/connectors", response_model=Page[ConnectorStatus])
def connector_statuses(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    account=Depends(actor),
    db=Depends(database),
):
    return page(
        request,
        db.scalars(select(WahaConnection).where(WahaConnection.account_id == account.id)),
        cursor,
        limit,
        lambda row: status_view(db, row),
    )


@app.post("/api/v1/connectors/waha/{connection_id}/events", response_model=Detail[ConnectorReceipt])
async def waha_events(
    connection_id: UUID, request: Request, db=Depends(database, scope="function")
):
    binding = binding_for(str(connection_id))
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise BusinessError(422, "INVALID_WEBHOOK_JSON", "Expected JSON")
    for name in ("x-webhook-hmac", "x-webhook-hmac-algorithm"):
        if len(request.headers.getlist(name)) != 1:
            raise BusinessError(401, "WEBHOOK_AUTH_REJECTED", "Webhook authentication failed")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            raise BusinessError(413, "WEBHOOK_TOO_LARGE", "Webhook exceeds limit")
        body.extend(chunk)
    try:
        verify_hmac(
            bytes(body),
            request.headers.get("X-Webhook-Hmac"),
            request.headers.get("X-Webhook-Hmac-Algorithm"),
            binding.secret,
        )
    except AdapterError:
        raise BusinessError(401, "WEBHOOK_AUTH_REJECTED", "Webhook authentication failed") from None
    try:
        raw = json.loads(body, object_pairs_hook=_pairs, parse_constant=_non_json_constant)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise BusinessError(422, "INVALID_WEBHOOK_JSON", "Invalid webhook JSON") from None
    # Row-lock waits must not block the event loop that schedules transaction exit.
    result = await run_in_threadpool(receive, db, binding, raw)
    return detail(request, result)


@app.post("/api/v1/replay", status_code=202, response_model=Detail[ReplayResult])
def replay(
    command: ReplayCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    account=Depends(actor),
    db=Depends(database),
):
    digest, cache = command_cache(db, account.id, "replay", idempotency_key, command.model_dump())
    result = cache.data if cache else ingest(db, account, replay_event(command.scenario))
    if not cache:
        save_result(db, account.id, "replay", idempotency_key, digest, result)
    return detail(request, result)


@app.post("/api/v1/replay/events", status_code=202, response_model=Detail[ReplayResult])
def replay_custom(
    event: dict,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    account=Depends(actor),
    db=Depends(database),
):
    digest, cache = command_cache(db, account.id, "replay/events", idempotency_key, event)
    result = cache.data if cache else ingest(db, account, event)
    if not cache:
        save_result(db, account.id, "replay/events", idempotency_key, digest, result)
    return detail(request, result)
