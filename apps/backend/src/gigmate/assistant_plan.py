"""Independently versioned AI output contracts for the bounded merchant assistant (ADR 0011).

Batch 0 defines shapes only; no route, worker job or provider call uses them yet.

The model never answers free-form. It returns two strictly validated objects:

* ``AssistantPlan`` (phase 1): which supported intent the merchant asked for and
  which *read-only* tools the server should run. Tools address data through the
  merchant's explicit selection (``target="selected"``), never through IDs the
  model invents, so a prompt-injected message cannot point a tool at another
  conversation or account.
* ``AssistantComposition`` (phase 2, reply/polish only): draft text plus the
  exact customer message revisions it answers. It is text for the merchant to
  review. It carries no recipient, approval, confirmation or sending field, and
  the server still owns every binding (conversation, order and context version).

Availability and order answers are rendered by the server from tool results;
the model does not state times, counts or order facts itself.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gigmate.contracts import SourceRef

SCHEMA_VERSION = "1.0.0"
MAX_TOOL_CALLS = 3
MAX_SLOT_WINDOW_DAYS = 31

Intent = Literal["availability", "order_status", "reply_draft", "polish", "clarify", "unsupported"]
Language = Literal["zh-Hans", "zh-Hant", "en"]
OrderStatusFilter = Literal[
    "pending_confirmation", "confirmed", "in_progress", "waiting_customer", "open"
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FindFreeSlots(_Strict):
    """Server runs scheduling.free_slots over the merchant's own calendar."""

    tool: Literal["find_free_slots"]
    duration_minutes: Annotated[int, Field(ge=15, le=720)]
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def _window(self):
        days = (self.to_date - self.from_date).days
        if days < 0 or days > MAX_SLOT_WINDOW_DAYS:
            raise ValueError(f"slot window must be 0..{MAX_SLOT_WINDOW_DAYS} days")
        return self


class ListWorkOrders(_Strict):
    """Account-owned orders, optionally limited to the selected conversation."""

    tool: Literal["list_work_orders"]
    status: OrderStatusFilter = "open"
    scope: Literal["account", "selected_conversation"] = "account"


class GetWorkOrder(_Strict):
    """The merchant's explicitly selected order only."""

    tool: Literal["get_work_order"]
    target: Literal["selected"]


class ReadConversation(_Strict):
    """Bounded, consent-checked recent context of the selected conversation."""

    tool: Literal["read_conversation"]
    target: Literal["selected"]


ToolCall = Annotated[
    FindFreeSlots | ListWorkOrders | GetWorkOrder | ReadConversation,
    Field(discriminator="tool"),
]

# Which tools each intent may request. Anything else is rejected, not ignored.
ALLOWED_TOOLS: dict[str, frozenset[str]] = {
    "availability": frozenset({"find_free_slots", "get_work_order"}),
    "order_status": frozenset({"list_work_orders", "get_work_order"}),
    "reply_draft": frozenset(
        {"read_conversation", "get_work_order", "find_free_slots", "list_work_orders"}
    ),
    "polish": frozenset({"read_conversation"}),
    "clarify": frozenset(),
    "unsupported": frozenset(),
}


class AssistantPlan(_Strict):
    schema_version: Literal["1.0.0"]
    intent: Intent
    language: Language
    tool_calls: Annotated[list[ToolCall], Field(max_length=MAX_TOOL_CALLS)] = []
    # Asked back to the merchant (never to the customer) when the request is ambiguous,
    # for example several open orders in one chat and none selected.
    clarification_question: Annotated[str, Field(min_length=1, max_length=300)] | None = None

    @model_validator(mode="after")
    def _consistent(self):
        allowed = ALLOWED_TOOLS[self.intent]
        for call in self.tool_calls:
            if call.tool not in allowed:
                raise ValueError(f"tool {call.tool} is not allowed for intent {self.intent}")
        if self.intent == "clarify" and self.clarification_question is None:
            raise ValueError("clarify requires clarification_question")
        if self.intent != "clarify" and self.clarification_question is not None:
            raise ValueError("clarification_question is only for intent clarify")
        if self.intent in {"availability", "order_status"} and not self.tool_calls:
            raise ValueError(f"{self.intent} requires at least one read tool")
        return self


class AssistantComposition(_Strict):
    """Phase-2 reply or polish text. A proposal surface only."""

    schema_version: Literal["1.0.0"]
    kind: Literal["reply_draft", "polish"]
    language: Language
    text: Annotated[str, Field(min_length=1, max_length=1000)]
    # Customer message revisions this reply answers. Polish of merchant-written text
    # may have none; a reply draft must cite at least one.
    sources: Annotated[list[SourceRef], Field(max_length=8)] = []
    # Facts the draft relies on but the tools did not establish (for example a price).
    # The server surfaces these for explicit merchant review instead of trusting them.
    unverified_claims: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=200)]], Field(max_length=5)
    ] = []

    @model_validator(mode="after")
    def _sources(self):
        if self.kind == "reply_draft" and not self.sources:
            raise ValueError("reply_draft must cite at least one customer message revision")
        keys = [(s.message_id, s.message_revision) for s in self.sources]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate source")
        return self
