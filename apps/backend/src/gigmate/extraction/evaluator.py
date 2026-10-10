"""Offline evaluation harness for extraction providers.

Runs every case in a synthetic manifest through the chosen provider and asserts
the expected assignment + change fields + confidence floor. Results are
persisted to ``evaluation_runs`` and ``evaluation_cases`` so that prompt and
model versions can be compared over time without replaying live content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from gigmate.contracts import EvaluationCase as EvaluationCaseModel
from gigmate.db import EvaluationCaseRecord, EvaluationRun

from .registry import build_provider
from .types import ExtractionRequest, Provider


@dataclass
class EvaluationOutcome:
    case_id: str
    scenario: str
    expected_assignment: str
    actual_assignment: str
    actual_confidence: float
    expected_min_confidence: float | None
    expected_change_fields: list[str]
    actual_change_fields: list[str]
    status: str  # "pass" | "fail"
    message: str | None


@dataclass
class EvaluationRunSummary:
    run_id: str
    cases: list[EvaluationOutcome]
    run_row: EvaluationRun


def _resolve_manifest_path(relative: str | Path) -> Path:
    path = Path(relative).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _build_request(case_payload: dict[str, Any], provider_name: str) -> ExtractionRequest:
    payload = case_payload.get("input_event", {})
    base_snapshot = payload.get("base_work_order_snapshot") or {}
    return ExtractionRequest(
        account_id=payload.get("account_id", "00000000-0000-4000-8000-000000000000"),
        conversation_id=payload.get("conversation_id", "00000000-0000-4000-8000-000000000000"),
        message_id=payload.get("message_id", "00000000-0000-4000-8000-000000000000"),
        message_revision=int(payload.get("message_revision", 1)),
        message_text=payload.get("text"),
        context_version=int(payload.get("context_version", 1)),
        candidate_work_order_ids=tuple(payload.get("candidate_work_order_ids", ())),
        base_work_order_version=payload.get("base_work_order_version"),
        base_work_order_snapshot=base_snapshot or None,
        # Evaluation manifests are synthetic-only by contract; a case may still
        # declare origin "live" to assert that live input is refused.
        origin=payload.get("origin", "synthetic"),
        extra={"provider_name": provider_name, "case_id": case_payload.get("case_id")},
    )


def _field_name(change) -> str:
    return change.field.value if hasattr(change.field, "value") else str(change.field)


def evaluate_case(provider: Provider, case_payload: dict[str, Any]) -> EvaluationOutcome:
    expected = EvaluationCaseModel.model_validate(case_payload)
    request = _build_request(case_payload, provider.name)
    outcome = provider.propose(request)
    actual_change_fields = [_field_name(change) for change in outcome.proposal.changes]
    actual_confidence = max(
        (candidate.confidence for candidate in outcome.proposal.candidates), default=0.0
    )
    issues: list[str] = []
    if outcome.proposal.assignment.value != expected.expected_assignment.value:
        issues.append(
            f"assignment {outcome.proposal.assignment.value} != expected {expected.expected_assignment.value}"
        )
    if (
        expected.expected_min_confidence is not None
        and outcome.proposal.assignment.value == "matched"
        and actual_confidence < expected.expected_min_confidence
    ):
        issues.append(
            f"confidence {actual_confidence} below expected minimum {expected.expected_min_confidence}"
        )
    if expected.expected_change_fields:
        missing = sorted(set(expected.expected_change_fields) - set(actual_change_fields))
        if missing:
            issues.append(f"missing fields: {missing}")
    return EvaluationOutcome(
        case_id=expected.case_id,
        scenario=expected.scenario,
        expected_assignment=expected.expected_assignment.value,
        actual_assignment=outcome.proposal.assignment.value,
        actual_confidence=actual_confidence,
        expected_min_confidence=expected.expected_min_confidence,
        expected_change_fields=list(expected.expected_change_fields),
        actual_change_fields=actual_change_fields,
        status="pass" if not issues else "fail",
        message="; ".join(issues) or None,
    )


def evaluate_manifest(
    db,
    manifest_path: str | Path,
    *,
    provider_name: str | None = None,
) -> EvaluationRunSummary:
    path = _resolve_manifest_path(manifest_path)
    provider = build_provider(provider_name)
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", ())
    if not cases:
        raise ValueError(f"Manifest {path} has no cases; refusing to record an empty run.")
    started = datetime.now(UTC)
    per_case: list[EvaluationOutcome] = []
    skipped = 0
    for case in cases:
        case_provider = case.get("provider") if isinstance(case, dict) else None
        if case_provider and case_provider != provider.name:
            skipped += 1
            continue
        per_case.append(evaluate_case(provider, case))
    if not per_case:
        names = sorted({case.get("provider") for case in cases if isinstance(case, dict)})
        raise ValueError(
            f"Manifest {path} has no cases targeting provider {provider.name!r}; "
            f"manifest only targets {names}."
        )
    finished = datetime.now(UTC)
    account_id = "00000000-0000-4000-8000-000000000eee"
    run_id = str(uuid4())
    passed = sum(1 for item in per_case if item.status == "pass")
    failed = len(per_case) - passed
    run_row = EvaluationRun(
        id=run_id,
        account_id=account_id,
        started_at=started,
        finished_at=finished,
        provider_name=provider.name,
        model_version=provider.model_version,
        prompt_version=provider.prompt_version,
        case_count=len(per_case),
        passed=passed,
        failed=failed,
        manifest_path=str(path),
    )
    db.add(run_row)
    db.flush()
    for outcome in per_case:
        db.add(
            EvaluationCaseRecord(
                id=str(uuid4()),
                run_id=run_id,
                account_id=account_id,
                case_id=outcome.case_id,
                scenario=outcome.scenario,
                expected_assignment=outcome.expected_assignment,
                actual_assignment=outcome.actual_assignment,
                actual_confidence=outcome.actual_confidence,
                expected_min_confidence=outcome.expected_min_confidence,
                status=outcome.status,
                expected_change_fields=outcome.expected_change_fields,
                actual_change_fields=outcome.actual_change_fields,
                message=outcome.message,
                created_at=started,
            )
        )
    return EvaluationRunSummary(run_id=run_id, cases=per_case, run_row=run_row)


__all__ = [
    "EvaluationOutcome",
    "EvaluationRunSummary",
    "evaluate_case",
    "evaluate_manifest",
]
