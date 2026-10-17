"""Opt-in text provider with an interruptible process boundary and no paid retry.

The historical ``llm`` registration remains a closed compatibility seam.
Operators select ``reviewed_llm`` explicitly after validating deployment and pricing.
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, replace
from uuid import uuid4

from gigmate.contracts import ChangeProposal

from .llm import LLMProvider
from .types import ExtractionOutcome, ExtractionRequest

CALL_DEADLINE_SECONDS = 20
MAX_RESULT_BYTES = 2 * 1024 * 1024


class ReviewedLLMProvider(LLMProvider):
    name = "reviewed_llm"
    _SKELETON_SEAM = False

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome:
        began = time.monotonic()
        prompt_version = self._read_prompt_version()
        # These branches are guaranteed refusals; reuse the canonical diagnostics.
        if (
            self._prompt_load_error is not None
            or self._refusal_reason(request) is not None
            or (request.origin != "synthetic" and not self._allow_live_origin)
        ):
            return super().propose(request)
        # A static historical price table is not deployment pricing acceptance.
        if not all(
            os.environ.get(k)
            for k in (
                "GIGMATE_LLM_COST_INPUT_USD_PER_1K",
                "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K",
            )
        ):
            return self._needs_review(
                request,
                reason="llm:operator-pricing-required",
                latency_ms=0,
                prompt_version=prompt_version,
                model_version=self._model_version(),
                notes=("llm:operator-pricing-required",),
            )
        request_id = request.extra.get("request_id") or uuid4().hex
        request = replace(request, extra={**request.extra, "request_id": request_id})
        code = "llm:result-unknown"
        try:
            # communicate(timeout) bounds DNS, headers and a slowly dripping body too.
            # TimeoutExpired is followed by kill + wait inside subprocess.run.
            result = subprocess.run(
                [sys.executable, "-m", "gigmate.extraction.reviewed"],
                input=json.dumps(asdict(request), ensure_ascii=False).encode(),
                capture_output=True,
                timeout=CALL_DEADLINE_SECONDS,
                check=False,
            )
            if result.returncode == 0 and len(result.stdout) <= MAX_RESULT_BYTES:
                value = json.loads(result.stdout)
                proposal = ChangeProposal.model_validate_json(json.dumps(value.pop("proposal")))
                outcome = ExtractionOutcome(proposal=proposal, **value)
                # Never trust a different identity, even across our own subprocess.
                if (
                    outcome.request_id == request_id
                    and proposal.conversation_id == request.conversation_id
                    and proposal.base_context_version == request.context_version
                ):
                    return outcome
                code = "llm:child-result-invalid"
        except subprocess.TimeoutExpired:
            code = "llm:result-unknown:deadline"
        except (OSError, ValueError, TypeError, KeyError):
            code = "llm:result-unknown:process"
        return self._needs_review(
            request,
            reason=code,
            latency_ms=int((time.monotonic() - began) * 1000),
            prompt_version=prompt_version,
            model_version=self._model_version(),
            notes=(code,),
            request_id=request_id,
        )


def configured_for_live() -> bool:
    """Availability only; this is not proof of vendor/phone acceptance."""
    from .llm import validate_provider_config

    if os.environ.get("GIGMATE_EXTRACTION_PROVIDER") != "reviewed_llm":
        return False
    selected = ReviewedLLMProvider()
    return (
        selected._configured_live
        and selected._allow_live_origin
        and selected._refusal_reason(None) is None
        and not validate_provider_config()
        and all(
            os.environ.get(k)
            for k in ("GIGMATE_LLM_COST_INPUT_USD_PER_1K", "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K")
        )
    )


def main():
    # Only this short-lived process may issue a paid text request.
    # A request header is correlation, not a vendor idempotency guarantee.
    from . import llm

    llm._MAX_RETRIES = 0
    raw = sys.stdin.buffer.read(MAX_RESULT_BYTES + 1)
    if len(raw) > MAX_RESULT_BYTES:
        return 2
    request = ExtractionRequest(**json.loads(raw))
    instance = LLMProvider()
    instance._SKELETON_SEAM = False
    outcome = instance.propose(request)
    # Closed/pre-call refusals still correlate with the persisted worker fence.
    outcome = replace(outcome, request_id=outcome.request_id or request.extra.get("request_id"))
    value = asdict(outcome)
    value["proposal"] = outcome.proposal.model_dump(mode="json")
    payload = json.dumps(value, ensure_ascii=False).encode()
    if len(payload) > MAX_RESULT_BYTES:
        return 3
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
