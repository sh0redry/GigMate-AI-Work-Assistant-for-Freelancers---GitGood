# Repository instructions

## Scope and authority

This repository is at engineering skeleton v0.2, supporting synthetic replay. Build only the requested milestone. Live integration, general extraction and sending remain pending. Use a single repository with a modular backend and separate worker.

Read docs/en/architecture.md, relevant ADRs and contracts/README.md. Pydantic models in apps/backend/src/gigmate/contracts.py govern domain shapes; scripts/export_contracts.py generates the domain schema and implemented OpenAPI. Never edit generated files manually. Event/AI schemas remain independently versioned. API documentation distinguishes implementation from targets. Update related English/Chinese documentation together. docs/project-kickoff-plan.md is planning history.

## Required rules

- AI outputs proposals and drafts, never confirmed writes or external execution. Keep connector credentials out of model and frontend contexts.
- Customer proposals, customer confirmations and merchant approvals are separate facts.
- A conversation can contain multiple work orders. Ambiguous assignment needs review.
- Critical fields retain source message revisions. Unknown values remain missing.
- Authenticate, resolve ownership server-side, and allowlist conversations before business-content storage or model calls.
- Approval binds recipient, content/mutation, work-order version, context version, expiry and action revision. Revalidate before execution.
- Relevant messages/edits/revocations invalidate queued approvals. API send echoes update context without recursive replies or retroactive cancellation of already dispatched sends.
- Persist jobs and state; use version checks, unique constraints, leases and a transactional outbox. Do not promise external exactly-once delivery.
- Unknown send outcomes require reconciliation, never blind resend.

## Changes and verification

Preserve unrelated user files. Use focused changes and do not fill the repository with unused directories. Add versioned migrations when implementation exists; do not rewrite shared migrations.

Current check from the repository root:

```text
python scripts/check_baseline.py
```

Use the project .venv and backend lock. Verified commands and PostgreSQL test setup are in docs/en/getting-started.md. Run applicable Ruff check/format, export_contracts.py --check, check_baseline.py, pytest and frontend check:api/format:check/build. SQLite tests do not prove PostgreSQL locking. Record completed work and actual evidence in docs/en/implementation-status.md and docs/zh/progress.md. Missing dependencies must fail clearly; test meaningful normal/failure paths.

Do not commit or push unless requested. Do not add links to `docs/zh/` in root README. Never include real conversations, credentials, QR codes or session files in tracked files. Report exactly what was verified and any limits.
