"""Run the offline extraction evaluation harness and persist results.

Examples::

    .venv/bin/python scripts/run_evaluation.py \\
        --manifest contracts/evaluation/manifest.json \\
        --database-url $DATABASE_URL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC
from pathlib import Path

from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend/src"))

from gigmate.db import Base, make_engine
from gigmate.extraction import evaluate_manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="Path to the synthetic evaluation manifest JSON file.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Override GIGMATE_EXTRACTION_PROVIDER for the duration of the run.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "sqlite:///./local-data/gigmate.db"),
        help="Target database URL. Defaults to DATABASE_URL or local sqlite.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path for a JSON summary report.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.provider:
        os.environ["GIGMATE_EXTRACTION_PROVIDER"] = args.provider
    engine = make_engine(args.database_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        summary = evaluate_manifest(db, args.manifest, provider_name=args.provider)
    report = {
        "started_at": summary.run_row.started_at.astimezone(UTC).isoformat(),
        "finished_at": summary.run_row.finished_at.astimezone(UTC).isoformat(),
        "provider_name": summary.run_row.provider_name,
        "model_version": summary.run_row.model_version,
        "prompt_version": summary.run_row.prompt_version,
        "case_count": summary.run_row.case_count,
        "passed": summary.run_row.passed,
        "failed": summary.run_row.failed,
        "manifest_path": summary.run_row.manifest_path,
        "cases": [
            {
                "case_id": outcome.case_id,
                "scenario": outcome.scenario,
                "status": outcome.status,
                "expected_assignment": outcome.expected_assignment,
                "actual_assignment": outcome.actual_assignment,
                "expected_change_fields": outcome.expected_change_fields,
                "actual_change_fields": outcome.actual_change_fields,
                "actual_confidence": outcome.actual_confidence,
                "message": outcome.message,
            }
            for outcome in summary.cases
        ],
    }
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    if summary.run_row.failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
