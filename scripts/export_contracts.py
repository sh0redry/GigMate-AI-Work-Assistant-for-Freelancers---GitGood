"""Export canonical Pydantic domain schemas and implemented API OpenAPI; --check detects drift."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend/src"))

from gigmate import contracts as c  # noqa: E402
from gigmate.api import app  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402


def domain_schema():
    definitions = {}
    models = [
        c.SourceRef,
        c.ConnectorStatus,
        c.ConnectorReceipt,
        c.RecoveryIssue,
        c.WahaSetup,
        c.WahaControlCommand,
        c.WahaVersionCommand,
        c.WahaSelectionCommand,
        c.WahaChoice,
        c.WahaIssueReviewCommand,
        c.WahaIssueReviewResult,
        c.WahaControlResult,
        c.WahaSyncCommand,
        c.WahaSyncResult,
        c.WahaTimelineMessage,
        c.WahaSourceGapView,
        c.WahaMediaCommand,
        c.WahaMediaCapabilities,
        c.WahaMediaJobView,
        c.WahaAttachmentView,
        c.WahaMediaResult,
        c.WahaMediaReviewCommand,
        c.WahaMediaInputContext,
        c.WahaMediaEvidence,
        c.ProvenancedField,
        c.WorkOrder,
        c.AccountConsent,
        c.Conversation,
        c.ConversationMessage,
        c.RequirementChange,
        c.ProposalCandidate,
        c.ProposalChange,
        c.ChangeProposal,
        c.EvaluationCase,
        c.EvaluationRun,
        c.Task,
        c.CalendarEvent,
        c.ApprovalAction,
        c.AuditLog,
        c.ConfirmChangeCommand,
        c.RejectCommand,
        c.ApproveActionCommand,
        c.RejectActionCommand,
    ]
    for model in models:
        schema = model.model_json_schema()
        definitions.update(schema.pop("$defs", {}))
        definitions[model.__name__] = schema
    for name in [
        "Id",
        "UtcTimestamp",
        "Timezone",
        "ScheduleValue",
        "DeadlineValue",
        "FieldValue",
    ]:
        schema = TypeAdapter(getattr(c, name)).json_schema()
        definitions.update(schema.pop("$defs", {}))
        definitions[name] = schema
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "GigMate domain models",
        "description": "Generated from apps/backend/src/gigmate/contracts.py; do not edit manually",
        "x-version": "0.1.0",
        "$defs": dict(sorted(definitions.items())),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for relative, value in [
        ("contracts/domain/models.schema.json", domain_schema()),
        ("contracts/openapi.json", app.openapi()),
    ]:
        path = ROOT / relative
        content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(
                    f"Generated contract drift: {relative}; run python scripts/export_contracts.py"
                )
        else:
            path.write_text(content, encoding="utf-8")
    print("Generated domain schema and implemented API OpenAPI are synchronized.")


if __name__ == "__main__":
    main()
