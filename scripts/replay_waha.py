"""Offline A-01 fixture acceptance; never contacts WAHA or processes real chat."""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend/src"))

try:
    from gigmate.waha_adapter import AdapterError, normalize_event, semantic_digest
    from gigmate.waha_replay import ReplayLedger, load_cases
except ImportError:
    raise SystemExit(
        "Missing backend dependencies. Use .venv and install apps/backend/requirements.lock."
    ) from None


def run_sequence(cases, receipt, show_events):
    ledger = ReplayLedger()
    by_name = {case["name"]: case for case in cases}
    steps = [
        ("text-created", {"duplicate": False, "context_version": 1}),
        ("text-created", {"duplicate": True, "context_version": 1}),
        ("delivery-read", {"duplicate": False, "context_version": 1}),
        ("text-revoked", {"error": "VERSION_CONFLICT"}),
        ("text-edited", {"duplicate": False, "context_version": 2}),
        ("text-revoked", {"duplicate": False, "context_version": 3}),
        ("text-revoked", {"duplicate": True, "context_version": 3}),
    ]
    failures = 0
    for number, (name, expected) in enumerate(steps, 1):
        item = by_name[name]
        try:
            event = normalize_event(
                item["raw"],
                item["context"],
                received_at=receipt + timedelta(seconds=number),
            )
            accepted = ledger.accept(event)
            outcome = {
                "duplicate": accepted.duplicate,
                "context_version": accepted.context_version,
            }
            passed = outcome == expected
            if show_events:
                outcome["event"] = event
        except AdapterError as exc:
            outcome = {"error": exc.code}
            passed = outcome == expected
        failures += not passed
        print(json.dumps({"step": number, "case": name, "pass": passed, **outcome}))
    print(
        json.dumps(
            {"mode": "synthetic_only", "steps": len(steps), "failures": failures}
        )
    )
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Synthetic WAHA A-01 acceptance; no network/DB"
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--case", help="Run one named synthetic case")
    modes.add_argument("--list", action="store_true", help="List available case names")
    modes.add_argument(
        "--sequence", action="store_true", help="Demo in-memory dedup/revision recovery"
    )
    parser.add_argument(
        "--show-events", action="store_true", help="Print synthetic normalized text"
    )
    args = parser.parse_args(argv)
    cases = load_cases()
    receipt = datetime(2026, 10, 2, 0, 0, 10, tzinfo=UTC)
    if args.sequence:
        return run_sequence(cases, receipt, args.show_events)
    if args.list:
        for case in cases:
            print(case["name"])
        return 0
    selected = [
        case for case in cases if args.case is None or case["name"] == args.case
    ]
    if not selected:
        parser.error("Unknown synthetic case; use --list")
    failures = 0
    for case in selected:
        try:
            event = normalize_event(case["raw"], case["context"], received_at=receipt)
            expected = case["expect"]
            passed = "error" not in expected and all(
                event[key] == value for key, value in expected.items()
            )
            result = {
                "event_type": event["event_type"],
                "event_id": event["event_id"],
                "digest": semantic_digest(event),
            }
            if args.show_events:
                result["event"] = event
        except AdapterError as exc:
            passed = case["expect"].get("error") == exc.code
            result = {"error": exc.code}
        failures += not passed
        print(
            json.dumps(
                {"case": case["name"], "pass": passed, **result}, ensure_ascii=False
            )
        )
    print(
        json.dumps(
            {"mode": "synthetic_only", "cases": len(selected), "failures": failures}
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AdapterError as exc:
        print(json.dumps({"error": exc.code}), file=sys.stderr)
        raise SystemExit(1) from None
