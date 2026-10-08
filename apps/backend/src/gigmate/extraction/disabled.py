"""Disabled provider: refuses every extraction request explicitly.

Configured via ``GIGMATE_EXTRACTION_PROVIDER=disabled``. Useful for environments
that want the worker to keep durable processing but absolutely never emit AI
proposals even for synthetic Replay fixtures.
"""

from __future__ import annotations

import time
from uuid import uuid4

from gigmate.contracts import ChangeProposal

from .types import ExtractionOutcome, ExtractionRequest


class DisabledProvider:
    name = "disabled"
    model_version = "synthetic:disabled-v1"
    prompt_version = "0.1.0"

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome:
        began = time.monotonic()
        proposal = {
            "schema_version": "0.1.0",
            "proposal_id": str(uuid4()),
            "conversation_id": request.conversation_id,
            "work_order_id": None,
            "base_work_order_version": None,
            "base_context_version": request.context_version,
            "assignment": "needs_review",
            "candidates": [],
            "changes": [],
            "unresolved_questions": ["Extraction is disabled; no proposal generated."],
            "draft_text": None,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
        }
        validated = ChangeProposal.model_validate(proposal)
        return ExtractionOutcome(
            provider_name=self.name,
            proposal=validated,
            latency_ms=max(0, int((time.monotonic() - began) * 1000)),
            notes=("disabled",),
            refused_reason="provider disabled",
        )


__all__ = ["DisabledProvider"]
