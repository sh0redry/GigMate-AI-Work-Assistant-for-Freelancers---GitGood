"""Bridge from the legacy :func:`understanding.extract` signature to the provider registry.

Kept so existing Replay smoke tests (``test_workflow.py``) continue to monkey
patch ``gigmate.worker.extract`` without provider plumbing leaking into them.
The legacy helper goes through the configured provider
(``GIGMATE_EXTRACTION_PROVIDER``) and marks its input as trusted synthetic
Replay content, returning the same plain dict the historical stub produced so
no schema or fixture changes are needed.
"""

from __future__ import annotations

from gigmate.extraction.registry import provider
from gigmate.extraction.types import ExtractionRequest


def _legacy_extract(event: dict, order: dict, context_version: int) -> dict | None:
    text = (event.get("payload") or {}).get("text")
    message_id = (event.get("payload") or {}).get("message_id")
    message_revision = event.get("message_revision")
    if not text or not message_id or not message_revision or order.get("id") is None:
        return None
    request = ExtractionRequest(
        account_id=event.get("account_id", "00000000-0000-4000-8000-000000000000"),
        conversation_id=event.get("conversation_id", "00000000-0000-4000-8000-000000000000"),
        message_id=message_id,
        message_revision=message_revision,
        message_text=text,
        context_version=context_version,
        candidate_work_order_ids=(order["id"],),
        base_work_order_version=order.get("version"),
        base_work_order_snapshot=order,
        origin="synthetic",
    )
    outcome = provider().propose(request)
    if outcome.proposal.assignment.value == "needs_review":
        return None
    return outcome.proposal.model_dump(mode="json")


__all__ = ["_legacy_extract"]
