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


class ComponentHealth(Model):
    state: Literal["healthy", "unavailable", "stale", "unknown"]
    observed_at: UtcTimestamp | None


class WahaSetup(Model):
    connection_id: Id
    control_version: Annotated[int, Field(ge=0)]
    enabled: bool
    available: bool
    provider_state: str | None
    provider_observed_at: UtcTimestamp | None
    active_operation_id: Id | None
    last_operation_id: Id | None
    provider_sample_stale: bool


class WahaControlCommand(Model):
    expected_version: Annotated[int, Field(ge=0)]
    action: Literal["connect", "recover", "inspect", "discover"]
    offset: Annotated[int, Field(ge=0, le=10000)] = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 100

    @model_validator(mode="after")
    def discovery_only(self):
        if self.action != "discover" and (self.offset != 0 or self.limit != 100):
            raise ValueError("Pagination only applies to discovery")
        return self


class WahaVersionCommand(Model):
    expected_version: Annotated[int, Field(ge=0)]


class WahaSelectionCommand(WahaVersionCommand):
    selected_ids: Annotated[list[Id], Field(max_length=100)]
    consent: Literal[True]

    @model_validator(mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if isinstance(value, dict) and type(value.get("consent")) is not bool:
            raise ValueError("Explicit boolean consent required")
        return value


class WahaChoice(Model):
    id: Id
    label: str
    selected: bool
    expires_at: UtcTimestamp | None
    kind: Literal["direct", "group"] = "direct"


class WahaIssueReviewCommand(Model):
    issue_ids: Annotated[list[Id], Field(min_length=1, max_length=100)]
    confirmed_no_import: Annotated[bool, Field(strict=True)]


class WahaIssueReviewResult(Model):
    reviewed: Annotated[int, Field(ge=1)]


class WahaControlResult(Model):
    id: Id
    connection_id: Id
    action: Literal["connect", "recover", "inspect", "discover"]
    state: Literal[
        "pending", "checking", "running", "succeeded", "failed", "result_unknown", "cancelled"
    ]
    control_version: Annotated[int, Field(ge=0)]
    error_code: str | None
    provider_state: str | None
    provider_observed_at: UtcTimestamp | None
    next_offset: Annotated[int, Field(ge=0)] | None = None


class WahaSyncCommand(WahaVersionCommand):
    chat_ids: Annotated[list[Id], Field(min_length=1, max_length=20)]
    since: UtcTimestamp
    until: UtcTimestamp
    max_records: Annotated[int, Field(ge=1, le=1000)] = 500
    consent: Annotated[bool, Field(strict=True)]
    issue_id: Id | None = None
    source_gap_id: Id | None = None


class WahaSyncResult(Model):
    id: Id
    connection_id: Id
    state: Literal["pending", "running", "succeeded", "failed", "cancelled"]
    chat_ids: list[Id]
    since: UtcTimestamp
    until: UtcTimestamp
    max_records: Annotated[int, Field(ge=1, le=1000)]
    issue_id: Id | None
    source_gap_id: Id | None
    imported: Annotated[int, Field(ge=0)]
    duplicates: Annotated[int, Field(ge=0)]
    skipped: Annotated[int, Field(ge=0)]
    pages: Annotated[int, Field(ge=0)]
    attempts: Annotated[int, Field(ge=0)]
    coverage: Literal["in_progress", "provider_exhausted", "limit_reached", "incomplete"]
    complete_history: Literal[False] = False
    error_code: str | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class WahaTimelineMessage(Model):
    id: Id
    chat_id: Id
    conversation_id: Id
    source_message_id: Id | None
    occurred_at: UtcTimestamp
    observed_at: UtcTimestamp
    origin: Literal["live", "history"]
    evidence: Literal["revision", "snapshot"]
    revision: Positive | None
    direction: Literal["incoming", "outgoing"]
    text: str | None
    revoked: bool
    kind: Literal["text", "image", "audio", "document", "video", "other"]
    mimetype: str | None
    filename: str | None
    sender_id: Id | None
    reply_to_id: Id | None
    attachment_reading: Literal["deferred", "not_applicable"]
    processing_state: str | None
    delivery_status: Literal["unknown", "sent", "delivered", "read"] | None


class WahaSourceGapView(Model):
    id: Id
    chat_id: Id
    observed_at: UtcTimestamp
    state: Literal["needs_lookup", "snapshot_found", "unavailable"]


class ConnectorMetrics(Model):
    rejected: Annotated[int, Field(ge=0)]
    retries: Annotated[int, Field(ge=0)]
    lease_recoveries: Annotated[int, Field(ge=0)]
    expired_leases: Annotated[int, Field(ge=0)]
    oldest_pending_seconds: Annotated[float, Field(ge=0)] | None
    timed_jobs: Annotated[int, Field(ge=0)]
    average_processing_ms: Annotated[float, Field(ge=0)] | None
    maximum_processing_ms: Annotated[int, Field(ge=0)] | None
    average_completion_latency_ms: Annotated[float, Field(ge=0)] | None
    last_error_code: Text | None
    last_rejection_at: UtcTimestamp | None


class RecoveryIssue(Model):
    id: Id
    connection_id: Id
    code: Text
    started_at: UtcTimestamp
    last_seen_at: UtcTimestamp
    recovered_at: UtcTimestamp | None
    acknowledged_at: UtcTimestamp | None
    resolution: Literal["reviewed_no_import", "needs_followup"] | None
    occurrences: Annotated[int, Field(ge=1)]


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
    api_health: ComponentHealth
    worker_health: ComponentHealth
    monitor_health: ComponentHealth
    provider_health: ComponentHealth
    pipeline_ready: bool
    review_required: bool
    unresolved_issues: Annotated[int, Field(ge=0)]
    metrics: ConnectorMetrics


class ConnectorReceipt(Model):
    event_id: Id
    duplicate: bool
    context_version: Annotated[int, Field(ge=0)]
    durable_acceptance: Literal[True]
    acceptance_kind: Literal["normalized_event", "observation"] = "normalized_event"


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


class AssignmentResult(StrEnum):
    matched = "matched"
    needs_review = "needs_review"


class ProposalCandidate(Model):
    work_order_id: Id
    confidence: Annotated[float, Field(ge=0, le=1)]


class ProposalChange(Model):
    field: Literal["schedule", "address", "summary", "quantity", "specification", "deadline"]
    old_value: FieldValue
    new_value: FieldValue
    field_status: Annotated[FieldStatus, Field(strict=False)]
    customer_confirmation: Annotated[CustomerConfirmation, Field(strict=False)]
    sources: Annotated[list[SourceRef], Field(min_length=1)]
    reason: Text
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"field_status": {"const": "missing"}}},
                    "then": {"properties": {"new_value": {"type": "null"}}},
                }
            ]
        },
    )


class ChangeProposal(Model):
    schema_version: Literal["0.1.0"]
    proposal_id: Id
    conversation_id: Id
    work_order_id: Id | None
    base_work_order_version: Positive | None
    base_context_version: Positive
    assignment: Annotated[AssignmentResult, Field(strict=False)]
    candidates: Annotated[list[ProposalCandidate], Field(min_length=0)]
    changes: Annotated[list[ProposalChange], Field(min_length=0)]
    unresolved_questions: Annotated[list[Text], Field(min_length=0)]
    draft_text: Text | None
    model_version: Text
    prompt_version: Text
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"assignment": {"const": "matched"}}},
                    "then": {
                        "properties": {
                            "work_order_id": {"type": "string", "format": "uuid"},
                            "base_work_order_version": {"type": "integer", "minimum": 1},
                        }
                    },
                },
                {
                    "if": {"properties": {"assignment": {"const": "needs_review"}}},
                    "then": {
                        "properties": {
                            "work_order_id": {"type": "null"},
                            "base_work_order_version": {"type": "null"},
                        }
                    },
                },
            ]
        },
    )

    @model_validator(mode="after")
    def no_executing_authority(self):
        # AI proposals may not be marked formally confirmed or authorize execution.
        for change in self.changes:
            if change.field_status == "confirmed":
                raise ValueError("AI proposals must not mark a field as confirmed")
        return self


class EvaluationCase(Model):
    case_id: Text
    scenario: Text
    data_classification: Literal["synthetic"]
    input_event: dict
    expected_assignment: Annotated[AssignmentResult, Field(strict=False)]
    expected_min_confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    expected_change_fields: list[
        Literal["schedule", "address", "summary", "quantity", "specification", "deadline"]
    ] = Field(default_factory=list)
    note: Text | None = None


class EvaluationRun(Model):
    run_id: Id
    started_at: UtcTimestamp
    finished_at: UtcTimestamp
    provider_name: Text
    model_version: Text
    prompt_version: Text
    case_count: Positive
    passed: Positive
    failed: Positive
    cases: Annotated[list[EvaluationCase], Field(min_length=0)]


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


class WahaMediaCommand(WahaVersionCommand):
    snapshot_id: Id
    consent_download: Literal[True]
    process: bool = False
    consent_model: bool = False
    timezone: Timezone | None = None

    @model_validator(mode="before")
    @classmethod
    def real_consent(cls, value):
        if isinstance(value, dict) and value.get("consent_download") is not True:
            raise ValueError("Explicit download consent required")
        return value

    @model_validator(mode="after")
    def processing_consent(self):
        if self.process and not self.consent_model:
            raise ValueError("Explicit processing consent required")
        return self


class WahaMediaSegment(Model):
    text: Annotated[str, Field(max_length=4000)]
    page: Annotated[int, Field(ge=1, le=200)] | None = None
    start_ms: Annotated[int, Field(ge=0, le=7200000)] | None = None
    end_ms: Annotated[int, Field(ge=0, le=7200000)] | None = None

    @model_validator(mode="after")
    def location(self):
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("Both time bounds are required")
        if self.end_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("Invalid time bounds")
        if self.page is not None and self.start_ms is not None:
            raise ValueError("Use a page or audio segment, not both")
        return self


class WahaMediaSuggestion(Model):
    field: Literal["summary", "schedule", "address", "requirements", "other"]
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    source_indices: Annotated[
        list[Annotated[int, Field(ge=0, le=199)]], Field(min_length=1, max_length=20)
    ]


class WahaMediaResult(Model):
    provider: Annotated[str, Field(min_length=1, max_length=80)]
    model_version: Annotated[str, Field(min_length=1, max_length=100)]
    prompt_version: Annotated[str, Field(min_length=1, max_length=100)]
    coverage: Literal["complete", "partial", "unknown"] = "unknown"
    segments: Annotated[list[WahaMediaSegment], Field(max_length=200)]
    summary: Annotated[str, Field(max_length=4000)] | None = None
    suggestions: Annotated[list[WahaMediaSuggestion], Field(max_length=30)] = Field(
        default_factory=list
    )
    unresolved_questions: Annotated[
        list[Annotated[str, Field(max_length=1000)]], Field(max_length=30)
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def bounded_sources(self):
        if sum(len(segment.text) for segment in self.segments) > 100000:
            raise ValueError("Extraction text limit exceeded")
        if any(i >= len(self.segments) for item in self.suggestions for i in item.source_indices):
            raise ValueError("Suggestion source is missing")
        return self


class WahaMediaReviewCommand(Model):
    expected_attachment_version: Annotated[int, Field(ge=1)]
    expected_context_version: Annotated[int, Field(ge=0)]
    expected_result_job_id: Id
    reviewed: Literal[True]
    note: Annotated[str, Field(max_length=2000)] = ""

    @model_validator(mode="before")
    @classmethod
    def explicit_review(cls, value):
        if isinstance(value, dict) and value.get("reviewed") is not True:
            raise ValueError("Explicit source review required")
        return value


class WahaMediaInputContext(Model):
    message_sent_at: UtcTimestamp | None = None
    timezone: Timezone | None = None
    timezone_source: Literal["merchant_choice", "unknown"] = "unknown"
    source_occurred_at: UtcTimestamp
    source_observed_at: UtcTimestamp


class WahaMediaEvidence(Model):
    schema_version: Literal["0.1.0"] = "0.1.0"
    account_id: Id
    conversation_id: Id
    snapshot_id: Id
    attachment_id: Id
    attachment_version: Annotated[int, Field(ge=1)]
    context_version: Annotated[int, Field(ge=0)]
    result_job_id: Id
    source_fingerprint: Text
    sha256: Text
    input_context: WahaMediaInputContext | None
    result: WahaMediaResult
    reviewed_at: UtcTimestamp
    review_note: str
    expires_at: UtcTimestamp
    business_confirmation_required: Literal[True] = True


class WahaAttachmentView(Model):
    id: Id
    snapshot_id: Id
    version: Annotated[int, Field(ge=1)]
    context_version: Annotated[int, Field(ge=0)]
    state: Literal["pending", "downloaded", "processed", "stale", "expired"]
    mimetype: str | None
    size_bytes: int | None
    sha256: str | None
    preview_available: bool
    source_fingerprint: str
    expires_at: UtcTimestamp
    result: WahaMediaResult | None
    result_job_id: Id | None
    reviewed_at: UtcTimestamp | None
    review_note: str | None
    latest_job_id: Id | None
    input_context: WahaMediaInputContext | None = None


class WahaMediaJobView(Model):
    id: Id
    attachment_id: Id
    state: Literal[
        "pending", "running", "retry_wait", "succeeded", "failed", "cancelled", "result_unknown"
    ]
    stage: Literal["download", "processing", "reconciling"]
    attempts: int
    error_code: str | None
    updated_at: UtcTimestamp


class WahaMediaCapabilities(Model):
    enabled: bool
    processor_configured: bool
    max_bytes: int
    accepted_types: list[str]


T = TypeVar("T")


class Detail(Model, Generic[T]):
    data: T
    request_id: Id


class Page(Model, Generic[T]):
    items: list[T]
    next_cursor: str | None
    request_id: Id
