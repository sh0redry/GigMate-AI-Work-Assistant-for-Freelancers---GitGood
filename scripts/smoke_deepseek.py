"""Manual smoke test for the DeepSeek-backed LLM extraction provider.

This script is **not** part of CI. It exists so an operator with valid
credentials can run a single, end-to-end LLM call against a configured
vendor (DeepSeek by default) and inspect the raw response and the parsed
:class:`ChangeProposal`. Run it from the repository root:

    export GIGMATE_LLM_PROVIDER=deepseek
    export GIGMATE_LLM_MODEL=deepseek-chat
    export GIGMATE_LLM_API_KEY=sk-...
    export GIGMATE_LLM_LIVE=1
    # Optional: allow real WhatsApp-style content (default: refuse).
    # export GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1
    # Optional: point at a different OpenAI-compatible endpoint.
    # export GIGMATE_LLM_ENDPOINT=https://your-private-deployment.example.com
    python scripts/smoke_deepseek.py

The script exits non-zero on any misconfiguration so it can be wired into
operator-side alerting if needed. The CI suite uses ``mock httpx`` instead
of this script; see ``tests/test_extraction.py``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make ``apps/backend/src`` importable when running from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "apps" / "backend" / "src"))

from gigmate.extraction.llm import LLMProvider  # noqa: E402
from gigmate.extraction.types import ExtractionRequest  # noqa: E402

_REQUIRED = ("GIGMATE_LLM_PROVIDER", "GIGMATE_LLM_MODEL", "GIGMATE_LLM_API_KEY")

# ``notes`` values that mean "the model was never successfully invoked".
# Treat these as smoke-script failures (non-zero exit) so the script can
# be wired into operator-side alerting.
#
# ``llm:seam-pending``          – the skeleton lock is still on (PR #20).
# ``llm:not-configured``        – a required env var (vendor, model, API
#                                  key) is missing or the vendor is
#                                  unsupported.
# ``llm:live-gate-off``         – GIGMATE_LLM_LIVE=1 is not set (only
#                                  reachable once the skeleton lock is
#                                  lifted).
# ``llm:origin-live-refused``   – live-origin input without
#                                  GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1.
# ``llm:prompt-load-failed``    – the bundled prompt could not be read.
# ``llm:http-failed``           – all retry attempts returned an HTTP error.
# ``llm:response-malformed``    – the response was not parseable JSON / the
#                                  expected choices/message/content shape.
# ``llm:response-schema-failed`` – the parsed JSON did not satisfy
#                                  ChangeProposal.
_INFRA_FAILURE_NOTES = frozenset(
    {
        "llm:seam-pending",
        "llm:not-configured",
        "llm:live-gate-off",
        "llm:origin-live-refused",
        "llm:prompt-load-failed",
        "llm:http-failed",
        "llm:response-malformed",
        "llm:response-schema-failed",
        # Gate 2 (vendor/endpoint), gate 1 (provenance) and gate 4 (time
        # basis) guards. None of them means the model was actually invoked.
        "llm:vendor-unknown",
        "llm:vendor-endpoint-mismatch",
        "llm:endpoint-required",
        "llm:endpoint-invalid",
        "llm:response-provenance-failed",
        "llm:time-basis-missing",
        # Batch 2 cost accounting. None of them means the model was actually
        # invoked successfully: either the call was never priced (so never
        # issued) or it came back over budget and was refused.
        "llm:cost-budget-exceeded",
        "llm:cost-budget-invalid",
        "llm:cost-pricing-missing",
        "llm:cost-pricing-partial",
        "llm:cost-pricing-invalid",
    }
)


def _check_env() -> None:
    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        sys.stderr.write(
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\n"
            + "Set them (and optionally GIGMATE_LLM_LIVE=1) and rerun.\n"
        )
        sys.exit(2)
    if os.environ.get("GIGMATE_LLM_LIVE") != "1":
        sys.stderr.write(
            "GIGMATE_LLM_LIVE=1 is not set. The provider will refuse the call. "
            "Re-run with GIGMATE_LLM_LIVE=1 to actually hit the model.\n"
        )
        sys.exit(2)


def _build_request() -> ExtractionRequest:
    return ExtractionRequest(
        account_id="00000000-0000-4000-8000-000000000001",
        conversation_id="00000000-0000-4000-8000-000000000002",
        message_id="00000000-0000-4000-8000-0000000a0001",
        message_revision=1,
        message_text="改下星期四下午三点，地址我晚些发",
        context_version=5,
        candidate_work_order_ids=("00000000-0000-4000-8000-000000000003",),
        base_work_order_version=3,
        base_work_order_snapshot={
            "id": "00000000-0000-4000-8000-000000000003",
            "version": 3,
            "fields": {
                "schedule": {
                    "value": {
                        "kind": "timed",
                        "start_at": "2026-10-07T07:00:00Z",
                        "end_at": "2026-10-07T08:00:00Z",
                        "timezone": "Asia/Hong_Kong",
                    }
                }
            },
        },
        origin="synthetic",
        # Gate 4: without both values the provider refuses schedule changes
        # instead of converting relative dates against nothing.
        message_received_at="2026-10-07T00:00:00Z",
        workspace_timezone=os.environ.get("GIGMATE_WORKSPACE_TIMEZONE")
        or "Asia/Hong_Kong",
    )


def main() -> int:
    _check_env()
    provider = LLMProvider()
    request = _build_request()
    outcome = provider.propose(request)
    payload = {
        "provider": outcome.provider_name,
        "assignment": outcome.proposal.assignment.value,
        "work_order_id": outcome.proposal.work_order_id,
        "model_version": outcome.proposal.model_version,
        "prompt_version": outcome.proposal.prompt_version,
        "latency_ms": outcome.latency_ms,
        "notes": list(outcome.notes),
        "refused_reason": outcome.refused_reason,
        "request_id": outcome.request_id,
        # Cost accounting (batch 2). None while the seam is closed or when
        # the vendor omits its usage block; ``cost_note`` then explains why
        # (llm:cost-usage-missing / llm:cost-pricing-missing).
        "input_tokens": outcome.input_tokens,
        "output_tokens": outcome.output_tokens,
        "cost_usd": outcome.cost_usd,
        "cost_note": outcome.cost_note,
        "unresolved_questions": list(outcome.proposal.unresolved_questions),
        "changes": [
            {
                "field": change.field.value
                if hasattr(change.field, "value")
                else str(change.field),
                "new_value": change.new_value,
                "field_status": change.field_status.value
                if hasattr(change.field_status, "value")
                else str(change.field_status),
                "reason": change.reason,
            }
            for change in outcome.proposal.changes
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return _classify_exit_code(outcome)


def _classify_exit_code(outcome) -> int:  # pragma: no cover - exercised via tests
    """Map an :class:`ExtractionOutcome` to a shell exit code.

    Exit code semantics:

    * ``0`` – the model was invoked and produced a usable business result
      (``assignment: matched`` or an LLM-driven ``needs_review`` with the
      ``llm:needs-review`` note). This is what an operator wants to see
      when the live call succeeded; the conservative ``needs_review`` is
      not itself a smoke failure.
    * ``1`` – the model was **not** successfully invoked, for any
      configuration / transport / parse / schema / lock reason. Any note
      listed in :data:`_INFRA_FAILURE_NOTES` triggers this. The full list
      of reasons is in :mod:`gigmate.extraction.llm`; operators should
      treat exit 1 as a smoke-script failure even when the printed
      ``assignment`` is ``needs_review`` – the printed reason explains
      which guard fired.
    """
    if any(note in _INFRA_FAILURE_NOTES for note in outcome.notes):
        return 1
    if outcome.proposal.assignment.value == "matched":
        return 0
    if outcome.notes == ("llm:needs-review",):
        return 0
    # Conservative default: any unrecognised needs_review note is treated
    # as a smoke failure so the operator notices instead of getting a
    # silent green.
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
