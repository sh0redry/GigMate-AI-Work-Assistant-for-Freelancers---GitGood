"""Per-account daily budget for real text-model calls.

The provider contract forbids database access, so the budget is split in two:

* :func:`snapshot` runs in the worker and reads durable ``model_call_traces``
  rows for the current UTC day; it produces the counters attached to
  :class:`~gigmate.extraction.types.ExtractionRequest`.
* :class:`~gigmate.extraction.llm.LLMProvider` refuses the call before any
  network I/O when the snapshot is already exhausted.

Counting traces instead of keeping a separate counter means the evidence row
and the budget can never disagree: a call is "used" exactly when its trace was
committed. A trace whose tokens were not reported still counts as one call, so
a vendor that omits usage cannot make the budget look free. Traces from the
local ``deterministic`` / ``disabled`` providers are excluded because they cost
nothing; any other provider name counts, so a newly added vendor fails closed
rather than running unmetered.

Live-origin traffic requires at least one bound
(``GIGMATE_LLM_DAILY_CALL_BUDGET`` or ``GIGMATE_LLM_DAILY_TOKEN_BUDGET``).
Without an explicit bound the provider refuses with
``llm:budget-not-configured`` rather than running unmetered.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as SessionFactory

from gigmate.db import ModelCallTrace

CALL_BUDGET_ENV = "GIGMATE_LLM_DAILY_CALL_BUDGET"
TOKEN_BUDGET_ENV = "GIGMATE_LLM_DAILY_TOKEN_BUDGET"

# Providers that never contact a paid vendor.
_LOCAL_PROVIDERS = ("deterministic", "disabled")


def _read_limit(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{name} must not be negative, got {value}")
    return value


@dataclass(frozen=True)
class BudgetSnapshot:
    """Durable usage for one account in the current UTC day."""

    call_limit: int | None
    token_limit: int | None
    calls_used: int
    tokens_used: int

    @property
    def configured(self) -> bool:
        return self.call_limit is not None or self.token_limit is not None

    @property
    def exhausted(self) -> bool:
        if self.call_limit is not None and self.calls_used >= self.call_limit:
            return True
        return self.token_limit is not None and self.tokens_used >= self.token_limit

    def as_request_fields(self) -> dict[str, int | None]:
        return {
            "budget_call_limit": self.call_limit,
            "budget_token_limit": self.token_limit,
            "budget_calls_used": self.calls_used,
            "budget_tokens_used": self.tokens_used,
        }


def limits_from_env() -> tuple[int | None, int | None]:
    """Return ``(call_limit, token_limit)`` from the trusted server settings."""
    return _read_limit(CALL_BUDGET_ENV), _read_limit(TOKEN_BUDGET_ENV)


def _day_start(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def snapshot(db: SessionFactory, account_id: str, *, now: datetime | None = None) -> BudgetSnapshot:
    """Sum today's committed traces for ``account_id`` plus the configured limits."""
    call_limit, token_limit = limits_from_env()
    row = db.execute(
        select(
            func.count(ModelCallTrace.id),
            func.coalesce(func.sum(ModelCallTrace.total_tokens), 0),
        ).where(
            ModelCallTrace.account_id == account_id,
            ModelCallTrace.created_at >= _day_start(now),
            # Local providers cost nothing and must not eat a paid budget.
            # Anything else (including a provider added later) counts, so an
            # unrecognised vendor fails closed rather than running unmetered.
            ModelCallTrace.provider_name.not_in(_LOCAL_PROVIDERS),
        )
    ).one()
    return BudgetSnapshot(
        call_limit=call_limit,
        token_limit=token_limit,
        calls_used=int(row[0] or 0),
        tokens_used=int(row[1] or 0),
    )


__all__ = [
    "CALL_BUDGET_ENV",
    "TOKEN_BUDGET_ENV",
    "BudgetSnapshot",
    "limits_from_env",
    "snapshot",
]
