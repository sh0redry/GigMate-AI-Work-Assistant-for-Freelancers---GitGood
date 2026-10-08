# Role B extraction subsystem

Updated: 2026-10-08. [Chinese](../zh/role-b-extraction.md). Builds on
[team local development](role-a-team-local-development.md) and the
[handoff summary](role-a-waha-handoff.md).

## Scope

Role B owns the AI extraction pipeline: provider interface, prompt and model
version registry, evaluation harness and the durable evidence rows that the
worker writes alongside each job. Outputs are proposals and drafts, never
confirmed writes or external execution. See [ADRs](adr/README.md) for the
contract authority and [architecture](architecture.md) for the data flow.

This batch delivers:

- Provider interface (`gigmate.extraction.Provider`) plus two concrete
  implementations: `DeterministicProvider` (the shipping default) and
  `DisabledProvider` for environments that want zero AI proposals.
- A worker integration that replaces the previous `LIVE_EXTRACTION_PENDING`
  placeholder with provider routing; live jobs that do not match a known
  synthetic fixture end with `EXTRACTION_NEEDS_REVIEW` instead of being
  silently completed without evidence.
- Pydantic `ChangeProposal`, `ProposalChange`, `ProposalCandidate`,
  `AssignmentResult`, `EvaluationCase` and `EvaluationRun` models, exported
  alongside the existing domain schema.
- Persistence rows `proposals`, `model_call_traces`, `evaluation_runs` and
  `evaluation_cases` (migration `0005_extraction_evidence`).
- An offline evaluation harness driven by `scripts/run_evaluation.py` over
  `contracts/evaluation/manifest.json`.

Real-model integration (Anthropic, OpenAI or other concrete providers) is a
separately authorized batch. The seam exists so that adding a real provider
does not touch the worker, the contracts or the existing Replay behaviour.

## Boundaries

- AI never marks a field as `confirmed`; `ChangeProposal.no_executing_authority`
  enforces that at the type layer.
- AI never grants execution authority. The persisted `RequirementChange.proposer`
  is always `customer` or `merchant` (set from the source message), regardless
  of which provider emitted the proposal.
- Live traffic is refused by `DeterministicProvider` unless the text exactly
  matches one of the canonical synthetic fixtures used by the Replay smoke.
  Real content returns `assignment: needs_review` with empty `changes` and an
  `unresolved_questions` entry explaining that general extraction is not yet
  enabled. This preserves the
  `real content must never run through fictional fixed extraction templates`
  guard from `role-a-team-local-development.md` while keeping the seam
  readable.
- Multi-order ambiguity never silently merges. The provider always receives
  `candidate_work_order_ids`; if the count is not exactly one, the proposal
  becomes `needs_review`. The worker still records `ASSIGNMENT_NEEDS_REVIEW`
  for the legacy Replay branch.
- Proposals only target the current accepted `context_version`; older
  contexts cannot create actionable proposals because `messaging.ingest`
  demotes pending changes on context advance.

## Provider interface

The provider contract is `gigmate.extraction.Provider`:

```text
class Provider(Protocol):
    name: str
    model_version: str
    prompt_version: str

    def propose(self, request: ExtractionRequest) -> ExtractionOutcome: ...
```

`ExtractionRequest` is bounded and allowlisted. The worker is responsible for
populating it from the Inbox row, the latest `MessageRow` revision, the
`ConversationRow.context_version`, the candidate `WorkOrderRow`s and the
account. The provider never reads models, makes outbound network calls or
touches the database.

`ExtractionOutcome` carries the validated `ChangeProposal`, the provider
name, the call latency and an optional `refused_reason`. `ChangeProposal` is
re-validated by the worker before persistence so a buggy provider cannot
write malformed rows.

## Selection and override

Provider selection goes through `gigmate.extraction.provider()`:

| Setting | Behaviour |
| --- | --- |
| `GIGMATE_EXTRACTION_PROVIDER=deterministic` (default) | Default provider; recognizes only the two canonical Replay fixtures. |
| `GIGMATE_EXTRACTION_PROVIDER=disabled` | All extraction requests return `needs_review` with empty changes. |
| Unknown name | Raise at startup; never silently fall back. |

Tests inject providers through
`gigmate.extraction.registry._reset_provider_for_testing` to avoid touching
process-level state.

## Worker integration

`apps/backend/src/gigmate/worker.py` calls the provider in the WAHA branch
only. The Replay branch keeps the legacy
`gigmate.understanding.extract` entry point so existing smoke tests continue
to monkey patch `gigmate.worker.extract` without changes.

The provider path:

1. Re-validates context version, message revision and `revoked` flag.
2. Resolves candidate work order IDs from `conversation_orders`.
3. Builds `ExtractionRequest` with the current snapshot of the linked work
   order's fields.
4. Calls `provider()`.propose(request).
5. Persists `Proposal` and `ModelCallTrace` rows in the same transaction.
6. If `assignment = matched` and exactly one candidate exists, calls
   `persist_changes_for` to materialise `RequirementChange` rows and
   append them to the work order's `pending_change_ids`.
7. Marks the Job `completed` with `error_code = None` only when at least
   one `RequirementChange` was created; otherwise
   `error_code = EXTRACTION_NEEDS_REVIEW`.

Real WhatsApp content currently never reaches step 6 because the
deterministic provider refuses unknown text. This is intentional; lifting
the guard is a separately authorized batch that must add a real-model
provider and harden the seam with prompt-injection tests.

## Evaluation harness

`scripts/run_evaluation.py` runs every case in
`contracts/evaluation/manifest.json` through the configured provider,
persists `EvaluationRun` + `EvaluationCaseRecord` rows and writes a JSON
report. Cases assert assignment, minimum confidence and expected change
fields. Six synthetic cases currently cover known reschedule, known
available, unknown live text, no-order-linkage, multi-order ambiguity and
prompt-injection attempts.

```text
.venv/bin/python scripts/run_evaluation.py \
    --manifest contracts/evaluation/manifest.json \
    --database-url "$DATABASE_URL" \
    --json-out local-data/evaluations/run-$(date -Iseconds).json
```

The script exits `0` only when all cases pass. Missing or empty manifests
fail loudly rather than recording an empty run.

## Synthetic fixtures and privacy

Evaluation cases live under `contracts/evaluation/` and follow the same
`data_classification: synthetic` discipline as `contracts/examples/`.
Concrete WAHA content, real chat ids or any other operator-bound text must
never appear in tracked fixtures. Model credentials stay server-side; the
provider interface never accepts keys in its DTOs, and logs are limited to
IDs, latency and stable error codes.

## Verification

Authoritative checks for this batch:

```text
.venv/bin/python -m ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py
.venv/bin/python -m ruff format --check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py
.venv/bin/python scripts/export_contracts.py --check
.venv/bin/python -m alembic -c apps/backend/alembic.ini upgrade head
.venv/bin/python -m alembic -c apps/backend/alembic.ini check
.venv/bin/python -m pytest apps/backend/tests -q --basetemp=local-data/pytest
.venv/bin/python scripts/check_baseline.py
```

PostgreSQL tests are the meaningful run; SQLite does not prove row-locking
and only confirms conditional compatibility. Synthesize real WhatsApp
traffic is out of scope for this batch.

## Open follow-ups

- Real-model provider integration (Anthropic, OpenAI or another separately
  authorized provider), including prompt-injection regression suite and
  latency budget.
- D frontend review surface for `pending_change_ids` produced by real
  providers; current Replay cards already accept them but a real provider
  round-trip is required before frontend changes ship.
- Tighten `unresolved_questions` rendering for merchant review once a real
  provider exists.
