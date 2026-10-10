"""AI extraction subsystem: providers, registry, evaluator and durable evidence.

The shipping default provider is deterministic and intentionally narrow: it only
returns structured proposals for the canonical synthetic fixtures used by the
Replay smoke flow. For any other input (live WhatsApp content, unknown Replay
text) it returns ``assignment: needs_review`` with no changes, so live traffic
never receives confirmation or execution authority from this milestone.

The ``llm`` provider is the separately authorized real-model seam; it ships as
a non-emitting skeleton that returns ``needs_review`` with a clear reason
until the real-model batch lands. The configuration, prompt versioning and
registry wiring are all in place so the next batch only has to fill in
``gigmate.extraction.llm.LLMProvider._invoke_model``.
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
