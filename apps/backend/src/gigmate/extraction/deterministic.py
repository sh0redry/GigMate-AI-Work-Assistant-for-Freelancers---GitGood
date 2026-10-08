"""Deterministic default extraction provider.

Intentionally narrow: it only recognizes the two synthetic fixture texts used by
the Replay smoke flow, and only for requests whose ``origin`` is ``"synthetic"``
(trusted Replay/evaluation channel). Live connector input is always
``assignment: needs_review`` even when its text happens to equal a fixture, so
real content can never be promoted through fictional fixed-date templates.
"""

from __future__ import annotations

import copy
import time
from uuid import uuid4

from gigmate.contracts import ChangeProposal
from gigmate.messaging import fixture

from .types import ExtractionOutcome, ExtractionRequest

_KNOWN_RESCHEDULE = fixture("message-reschedule")["payload"]["text"]
_KNOWN_AVAILABLE = "确认下星期四下午四点半到五点半，地址晚些发"
_PROPOSAL_TEMPLATE = fixture("proposal-reschedule")


class DeterministicProvider:
    name = "deterministic"
    model_version = "synthetic:fixed-stub-v1"
    prompt_version = "0.1.0"

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome:
        began = time.monotonic()
        if request.origin != "synthetic":
            return self._needs_review(
                request,
                reason=(
                    "Deterministic provider only processes trusted synthetic "
                    "Replay/evaluation input; live content requires a separately "
                    "authorized provider."
                ),
                latency_ms=self._elapsed(began),
            )
        text = (request.message_text or "").strip()
        if text not in {_KNOWN_RESCHEDULE, _KNOWN_AVAILABLE}:
            return self._needs_review(
                request,
                reason=(
                    "Deterministic provider does not recognize this message text; "
                    "general extraction requires a separately authorized provider."
                ),
                latency_ms=self._elapsed(began),
            )
        if len(request.candidate_work_order_ids) != 1 or request.base_work_order_version is None:
            return self._needs_review(
                request,
                reason="Conversation is not unambiguously linked to a single work order.",
                latency_ms=self._elapsed(began),
            )
        order_id = request.candidate_work_order_ids[0]
        proposal = copy.deepcopy(_PROPOSAL_TEMPLATE)
        proposal.update(
            proposal_id=str(uuid4()),
            conversation_id=request.conversation_id,
            work_order_id=order_id,
            base_work_order_version=request.base_work_order_version,
            base_context_version=request.context_version,
        )
        proposal["candidates"] = [{"work_order_id": order_id, "confidence": 1.0}]
        proposal["unresolved_questions"] = [] if text == _KNOWN_RESCHEDULE else ["见面地址尚未提供"]
        change = proposal["changes"][0]
        if request.base_work_order_snapshot is not None:
            change["old_value"] = request.base_work_order_snapshot["fields"]["schedule"]["value"]
        change["sources"] = [
            {
                "message_id": request.message_id,
                "message_revision": request.message_revision,
            }
        ]
        change["customer_confirmation"] = "confirmed" if text == _KNOWN_AVAILABLE else "pending"
        if text == _KNOWN_AVAILABLE:
            change["new_value"]["start_at"] = "2026-10-08T08:30:00Z"
            change["new_value"]["end_at"] = "2026-10-08T09:30:00Z"
        validated = ChangeProposal.model_validate(proposal)
        return ExtractionOutcome(
            provider_name=self.name,
            proposal=validated,
            latency_ms=self._elapsed(began),
            notes=("deterministic:matched-known-fixture",),
        )

    def _needs_review(
        self, request: ExtractionRequest, *, reason: str, latency_ms: int
    ) -> ExtractionOutcome:
        proposal = {
            "schema_version": "0.1.0",
            "proposal_id": str(uuid4()),
            "conversation_id": request.conversation_id,
            "work_order_id": None,
            "base_work_order_version": None,
            "base_context_version": request.context_version,
            "assignment": "needs_review",
            "candidates": [
                {"work_order_id": identifier, "confidence": 0.0}
                for identifier in request.candidate_work_order_ids
            ],
            "changes": [],
            "unresolved_questions": [reason],
            "draft_text": None,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
        }
        validated = ChangeProposal.model_validate(proposal)
        return ExtractionOutcome(
            provider_name=self.name,
            proposal=validated,
            latency_ms=latency_ms,
            notes=("deterministic:needs_review",),
            refused_reason=reason,
        )

    @staticmethod
    def _elapsed(began: float) -> int:
        return max(0, int((time.monotonic() - began) * 1000))


__all__ = ["DeterministicProvider"]
