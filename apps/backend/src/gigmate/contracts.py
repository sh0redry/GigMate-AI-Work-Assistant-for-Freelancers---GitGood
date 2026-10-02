"""Canonical Pydantic domain models; export their schemas with scripts/export_contracts.py."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, WithJsonSchema, model_validator


def valid_id(value: str) -> str:
    UUID(value)
    return value


def valid_utc(value: str) -> str:
    if not value.endswith("Z") or datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("Use a UTC RFC3339 timestamp ending in Z")
    return value


def valid_date(value: str) -> str:
    date.fromisoformat(value)
    return value


def valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except KeyError as exc:
        raise ValueError("Use a known IANA timezone") from exc
    return value


Id = Annotated[str, AfterValidator(valid_id), WithJsonSchema({"type": "string", "format": "uuid"})]
UtcTimestamp = Annotated[
    str,
    AfterValidator(valid_utc),
    WithJsonSchema({"type": "string", "format": "date-time", "pattern": "Z$"}),
]
DateString = Annotated[
    str, AfterValidator(valid_date), WithJsonSchema({"type": "string", "format": "date"})
]
Timezone = Annotated[str, AfterValidator(valid_timezone), Field(min_length=1)]
Positive = Annotated[int, Field(ge=1)]
Text = Annotated[str, Field(min_length=1)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ConnectorStatus(Model):
    id: Id
    connector: Literal["waha"]
    state: Literal["unknown", "connected", "connecting", "disconnected", "failed"]
    enabled: bool
    live_connected: bool
    stale: bool
    observed_at: UtcTimestamp | None
    last_sync_at: UtcTimestamp | None
    accepted: Annotated[int, Field(ge=0)]
    duplicates: Annotated[int, Field(ge=0)]
    stale_events: Annotated[int, Field(ge=0)]
    pending_jobs: Annotated[int, Field(ge=0)]
    processing_jobs: Annotated[int, Field(ge=0)]
    failed_jobs: Annotated[int, Field(ge=0)]


class ConnectorReceipt(Model):
    event_id: Id
    duplicate: bool
    context_version: Annotated[int, Field(ge=0)]
    durable_acceptance: Literal[True]


class WorkOrderStatus(StrEnum):
    unclassified = "unclassified"
    pending_confirmation = "pending_confirmation"
    confirmed = "confirmed"
    in_progress = "in_progress"
    waiting_customer = "waiting_customer"
    completed = "completed"
    cancelled = "cancelled"


class FieldStatus(StrEnum):
    missing = "missing"
    proposed = "proposed"
    confirmed = "confirmed"
    needs_review = "needs_review"


class CustomerConfirmation(StrEnum):
    not_requested = "not_requested"
    pending = "pending"
    confirmed = "confirmed"
    ambiguous = "ambiguous"


class ActionState(StrEnum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    executing = "executing"
    succeeded = "succeeded"
    failed = "failed"
    result_unknown = "result_unknown"
    cancelled = "cancelled"
    expired = "expired"


class SourceRef(Model):
    message_id: Id
    message_revision: Positive


class TimedSchedule(Model):
    kind: Literal["timed"]
    start_at: UtcTimestamp
    end_at: UtcTimestamp
    timezone: Timezone

    @model_validator(mode="after")
    def chronological(self):
        if datetime.fromisoformat(self.end_at) <= datetime.fromisoformat(self.start_at):
            raise ValueError("end_at must follow start_at")
        return self


class DateOnly(Model):
    kind: Literal["date_only"]
    date: DateString
    timezone: Timezone


class InstantDeadline(Model):
    kind: Literal["instant"]
    at: UtcTimestamp
    timezone: Timezone


ScheduleValue = TimedSchedule | DateOnly
DeadlineValue = InstantDeadline | DateOnly
FieldValue = str | int | float | bool | None | TimedSchedule | DateOnly | InstantDeadline


class ProvenancedField(Model):
    value: FieldValue
    status: Annotated[FieldStatus, Field(strict=False)]
    sources: list[SourceRef]
    interpretation: str | None
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"status": {"const": "missing"}}},
                    "then": {"properties": {"value": {"type": "null"}}},
                },
                {
                    "if": {"properties": {"status": {"const": "confirmed"}}},
                    "then": {
                        "properties": {
                            "value": {"not": {"type": "null"}},
                            "sources": {"minItems": 1},
                        }
                    },
                },
            ]
        },
    )

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "missing" and self.value is not None:
            raise ValueError("Missing fields must have null values")
        if self.status == "confirmed" and (self.value is None or not self.sources):
            raise ValueError("Confirmed fields require a value and provenance")
        return self


class WorkOrderFields(Model):
    schedule: ProvenancedField
    address: ProvenancedField


class WorkOrder(Model):
    id: Id
    account_id: Id
    conversation_ids: Annotated[list[Id], Field(min_length=1)]
    summary: Text
    status: Annotated[WorkOrderStatus, Field(strict=False)]
    version: Positive
    fields: WorkOrderFields
    pending_change_ids: list[Id]
    updated_at: UtcTimestamp


class AccountConsent(Model):
    id: Id
    account_id: Id
    allowed_conversation_ids: list[Id]
    scopes: list[Literal["process_text", "prepare_drafts", "approved_send"]]
    status: Literal["active", "paused", "revoked"]
    expires_at: UtcTimestamp | None


class Conversation(Model):
    id: Id
    account_id: Id
    provider_conversation_id: Text
    context_version: Positive
    work_order_ids: list[Id]


class ConversationMessage(Model):
    id: Id
    account_id: Id
    conversation_id: Id
    provider_message_id: Text
    revision: Positive
    direction: Literal["incoming", "outgoing"]
    source: Literal["app", "api", "replay"]
    occurred_at: UtcTimestamp
    text: str | None
    revoked: bool


class RequirementChange(Model):
    id: Id
    account_id: Id
    work_order_id: Id
    field: Literal["schedule", "address", "summary", "quantity", "specification", "deadline"]
    old_value: FieldValue
    new_value: FieldValue
    status: Annotated[FieldStatus, Field(strict=False)]
    customer_confirmation: Annotated[CustomerConfirmation, Field(strict=False)]
    proposer: Literal["customer", "merchant"]
    sources: Annotated[list[SourceRef], Field(min_length=1)]
    base_work_order_version: Positive


class Task(Model):
    id: Id
    account_id: Id
    work_order_id: Id
    work_order_version: Positive
    title: Text
    owner_id: Id
    due: DeadlineValue | None
    depends_on: list[Id]
    state: Literal["pending", "blocked", "completed", "cancelled"]
    sources: Annotated[list[SourceRef], Field(min_length=1)]


class CalendarEvent(Model):
    id: Id
    account_id: Id
    work_order_id: Id
    work_order_version: Positive
    schedule: ScheduleValue
    tentative: bool
    buffer_minutes: Annotated[int, Field(ge=0)]
    sources: Annotated[list[SourceRef], Field(min_length=1)]


class ApprovalAction(Model):
    id: Id
    account_id: Id
    work_order_id: Id
    conversation_id: Id
    kind: Literal["send_text"]
    revision: Positive
    state: Annotated[ActionState, Field(strict=False)]
    recipient: Text
    body: Text
    bound_work_order_version: Positive
    bound_context_version: Positive
    snapshot_hash: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    expires_at: UtcTimestamp
    approved_by: Id | None
    approved_at: UtcTimestamp | None
    idempotency_key: Text
    provider_message_id: str | None
    delivery_status: Literal["not_submitted", "accepted", "sent", "delivered", "read", "unknown"]
    sources: Annotated[list[SourceRef], Field(min_length=1)]
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "state": {
                                "enum": [
                                    "approved",
                                    "executing",
                                    "succeeded",
                                    "failed",
                                    "result_unknown",
                                ]
                            }
                        }
                    },
                    "then": {
                        "properties": {
                            "approved_by": {"type": "string", "format": "uuid"},
                            "approved_at": {"type": "string", "format": "date-time"},
                        }
                    },
                },
                {
                    "if": {"properties": {"state": {"const": "result_unknown"}}},
                    "then": {"properties": {"delivery_status": {"const": "unknown"}}},
                },
            ]
        },
    )

    @model_validator(mode="after")
    def authorized(self):
        if self.state in {"approved", "executing", "succeeded", "failed", "result_unknown"} and (
            not self.approved_by or not self.approved_at
        ):
            raise ValueError("Approved actions need an approving merchant")
        if self.state == "result_unknown" and self.delivery_status != "unknown":
            raise ValueError("Unknown result needs unknown delivery state")
        return self


class AuditLog(Model):
    id: Id
    account_id: Id
    actor_id: Id | None
    entity_type: Text
    entity_id: Id
    action_id: Id | None
    operation: Text
    occurred_at: UtcTimestamp
    request_id: Id


class ConfirmChangeCommand(Model):
    expected_version: Positive
    expected_context_version: Positive
    apply_calendar_update: bool


class RejectCommand(Model):
    expected_version: Positive
    reason: Text


class ApproveActionCommand(Model):
    expected_version: Positive
    expected_context_version: Positive
    expected_action_revision: Positive
    snapshot_hash: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


class RejectActionCommand(ApproveActionCommand):
    reason: Text


T = TypeVar("T")


class Detail(Model, Generic[T]):
    data: T
    request_id: Id


class Page(Model, Generic[T]):
    items: list[T]
    next_cursor: str | None
    request_id: Id
