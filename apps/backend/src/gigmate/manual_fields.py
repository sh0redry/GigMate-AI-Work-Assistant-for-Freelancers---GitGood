"""Explicit merchant corrections with reviewed sources, never model authority."""

from uuid import UUID, uuid4

from fastapi import Depends, Header, Request
from pydantic import ValidationError
from sqlalchemy import select

from gigmate.approvals import cancel_pending
from gigmate.contracts import (
    ConfirmChangeCommand,
    Detail,
    ManualFieldCommand,
    RequirementChange,
    WorkOrder,
)
from gigmate.db import ChangeRow, ConversationRow, MessageRow
from gigmate.errors import BusinessError
from gigmate.workorders import (
    audit_row,
    authorized_order_conversation,
    command_cache,
    confirm,
    current_sources,
    locked_order,
    save_result,
    validate,
)


def correct_field(db, account, order_id, command, key, request_id):
    scope = f"manual_field:{order_id}"
    payload = command.model_dump(mode="json")
    digest, cached = command_cache(db, account.id, scope, key, payload)
    if cached:
        return cached.data
    try:
        order = locked_order(db, account, order_id, command.expected_version)
        # Supported additive legacy fields receive only contract defaults, never
        # guessed values. Corrupt required data requires review, not a raw 500.
        order.data = WorkOrder.model_validate(order.data).model_dump(mode="json")
    except (KeyError, TypeError, ValidationError):
        raise BusinessError(
            409, "WORK_ORDER_REVIEW_REQUIRED", "Stored work order needs review"
        ) from None
    conversation = db.scalar(
        select(ConversationRow)
        .where(
            ConversationRow.id == command.conversation_id, ConversationRow.account_id == account.id
        )
        .with_for_update()
    )
    if conversation is None:
        raise BusinessError(404, "NOT_FOUND", "Conversation not found")
    authorized_order_conversation(db, account, order, conversation.id)
    if conversation.context_version != command.expected_context_version:
        raise BusinessError(409, "VERSION_CONFLICT", "Refresh the source context")
    current_sources(db, account, conversation.id, payload["sources"])
    for source in payload["sources"]:
        message = db.scalar(
            select(MessageRow).where(
                MessageRow.id == source["message_id"],
                MessageRow.revision == source["message_revision"],
                MessageRow.account_id == account.id,
                MessageRow.conversation_id == conversation.id,
            )
        )
        if message.data["direction"] != "incoming":
            raise BusinessError(422, "VALIDATION_FAILED", "Review a customer source message")
    field = command.field
    old = order.data["summary"] if field == "summary" else order.data["fields"][field]["value"]
    identifier = str(uuid4())
    change = ChangeRow(
        id=identifier,
        account_id=account.id,
        work_order_id=order.id,
        conversation_id=conversation.id,
        context_version=conversation.context_version,
        data=validate(
            RequirementChange,
            {
                "id": identifier,
                "account_id": account.id,
                "work_order_id": order.id,
                "field": field,
                "old_value": old,
                "new_value": payload["value"],
                "status": "proposed",
                "customer_confirmation": "confirmed"
                if command.customer_confirmed
                else "not_requested",
                "proposer": "merchant",
                "sources": payload["sources"],
                "base_work_order_version": command.expected_version,
            },
        ),
    )
    # A reviewed manual correction supersedes earlier proposals for this one
    # field. Keep their source history, but do not leave a disabled old card as
    # the next required action. Other fields still need separate review.
    superseded = []
    for earlier in db.scalars(
        select(ChangeRow).where(
            ChangeRow.work_order_id == order.id, ChangeRow.account_id == account.id
        )
    ):
        if earlier.data["field"] == field and earlier.data["status"] in {
            "proposed",
            "needs_review",
        }:
            earlier.data = {
                **earlier.data,
                "status": "rejected",
                "rejection_reason": "Merchant replaced this field after reviewing its source",
            }
            superseded.append(earlier.id)
    order.data = {
        **order.data,
        "pending_change_ids": [
            identifier
            for identifier in order.data["pending_change_ids"]
            if identifier not in superseded
        ],
    }
    db.add(change)
    db.flush()
    # Retire only non-dispatched drafts. Submitted/unknown sends keep their
    # reconciliation records. confirm() atomically updates calendar/tasks and
    # creates a replacement question only for genuinely unresolved fields.
    cancel_pending(db, account.id, work_order_id=order.id, reason="superseded")
    result = confirm(
        db,
        account,
        order.id,
        change.id,
        ConfirmChangeCommand(
            expected_version=command.expected_version,
            expected_context_version=command.expected_context_version,
            apply_calendar_update=command.apply_calendar_update,
        ),
        key,
        request_id,
    )
    db.add(audit_row(account.id, order.id, "merchant_corrected_" + field, request_id))
    save_result(db, account.id, scope, key, digest, result)
    return result


def install(app, database, actor, detail):
    @app.post("/api/v1/work-orders/{order_id}/manual-field", response_model=Detail[WorkOrder])
    def manual_field(
        order_id: UUID,
        command: ManualFieldCommand,
        request: Request,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        account=Depends(actor),
        db=Depends(database),
    ):
        return detail(
            request,
            correct_field(
                db, account, str(order_id), command, idempotency_key, request.state.request_id
            ),
        )
