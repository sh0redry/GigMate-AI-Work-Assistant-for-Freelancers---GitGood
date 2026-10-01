# Repository instructions

## Scope and authority

This repository is at engineering baseline v0.1. Build only the requested milestone. Do not describe planned services as implemented. Use a single repository with a modular backend and a separate worker.

Read `docs/en/architecture.md`, relevant accepted ADRs, and `contracts/README.md` before changing shared behavior. Schemas govern field names and enums; accepted ADRs govern architecture; the API contract governs endpoint behavior. English documentation explains the baseline; Chinese documentation provides internal checks. Update affected documents together and resolve contradictions. `docs/project-kickoff-plan.md` is historical planning, not the active standard.

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

Install the pinned validator first as documented in `docs/en/getting-started.md`. Missing schema dependencies must fail clearly, not silently skip validation. Application tests and lint do not exist yet; add actual verified commands at the skeleton milestone. Future behavior changes need relevant normal and failure-path tests, especially ownership, stale approval, duplicates and unknown outcomes.

Do not commit or push unless requested. Do not add links to `docs/zh/` in root README. Never include real conversations, credentials, QR codes or session files in tracked files. Report exactly what was verified and any limits.
