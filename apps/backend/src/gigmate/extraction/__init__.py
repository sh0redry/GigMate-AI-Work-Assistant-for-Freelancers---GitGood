"""AI extraction subsystem: providers, registry, evaluator and durable evidence.

The shipping default provider is deterministic and intentionally narrow: it only
returns structured proposals for the canonical synthetic fixtures used by the
Replay smoke flow. For any other input (live WhatsApp content, unknown Replay
text) it returns ``assignment: needs_review`` with no changes, so live traffic
never receives confirmation or execution authority from this milestone.

Real-model integration is a separately authorized batch; the seam is here.
"""

from .evaluator import (
    EvaluationOutcome,
    EvaluationRunSummary,
    evaluate_case,
    evaluate_manifest,
)
from .persistence import persist_changes_for, persist_proposal
from .registry import build_provider, provider, registered_providers
from .types import ExtractionOutcome, ExtractionRequest, Provider

__all__ = [
    "EvaluationOutcome",
    "EvaluationRunSummary",
    "ExtractionOutcome",
    "ExtractionRequest",
    "Provider",
    "build_provider",
    "evaluate_case",
    "evaluate_manifest",
    "persist_changes_for",
    "persist_proposal",
    "provider",
    "registered_providers",
]
