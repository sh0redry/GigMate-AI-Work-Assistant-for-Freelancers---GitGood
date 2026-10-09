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
This batch ships the `llm` provider as a non-emitting skeleton: registry
selection, configuration, prompt versioning and the call shape are wired in
place, so the next batch only has to fill in
`gigmate.extraction.llm.LLMProvider._invoke_model`.

## Boundaries

- AI never marks a field as `confirmed`; `ChangeProposal.no_executing_authority`
  enforces that at the type layer.
- AI never grants execution authority. The persisted `RequirementChange.proposer`
  is always `customer` or `merchant` (set from the source message), regardless
  of which provider emitted the proposal.
- Live traffic is refused by `DeterministicProvider` on two independent
  conditions: the request's `origin` must be `synthetic` (trusted Replay or
  evaluation channel) **and** the text must exactly match one of the canonical
  synthetic fixtures. Live-origin input returns `assignment: needs_review`
  even when its text equals a fixture, so real content can never be promoted
  through the fixed-date templates. Real content returns
  `assignment: needs_review` with empty `changes` and an
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

### Origin trust boundary

`ExtractionRequest.origin` is set server-side and is the trust boundary
between synthetic and live input:

- `origin="synthetic"` — set only by the trusted Replay legacy path
  (`gigmate.understanding.extract`) and the offline evaluation harness. This
  is the only origin for which fixed-template providers may emit `matched`.
- `origin="live"` (the default) — set by the worker's WAHA branch for every
  real connector event. Unmarked requests default to `live`, so a caller that
  forgets to classify its input can never be treated as synthetic.

A provider that wants to mark live content `matched` is a separately
authorized batch; the evaluation manifest's `case-007-live-origin-with-fixture-text`
pins this behaviour.

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
| `GIGMATE_EXTRACTION_PROVIDER=llm` | Real-model skeleton; returns `needs_review` with a clear reason until the seam is filled in. |
| Unknown name | Raise at startup; never silently fall back. |

Tests inject providers through
`gigmate.extraction.registry._reset_provider_for_testing` to avoid touching
process-level state.

### `llm` provider skeleton

`gigmate.extraction.llm.LLMProvider` is the non-emitting seam for the
separately authorized real-model batch. It honours the same
`ExtractionRequest.origin` trust boundary as the deterministic provider, reads
a versioned prompt file from `gigmate/extraction/prompts/`, and persists the
configured model and prompt versions in `ModelCallTrace` so reviewers can see
why a request was refused.

Configuration (environment variables, all optional until the seam is filled):

| Variable | Purpose |
| --- | --- |
| `GIGMATE_LLM_PROVIDER` | Vendor name (`openai`, `anthropic`, ...). Used in `model_version`. |
| `GIGMATE_LLM_MODEL` | Model identifier. Default marker `skeleton:pending` until configured. |
| `GIGMATE_LLM_API_KEY` | Server-side only. Read by the seam when the next batch lands. |
| `GIGMATE_LLM_ENDPOINT` | Optional base URL override (testing). |
| `GIGMATE_LLM_PROMPT_PATH` | Optional override of the bundled prompt file. |
| `GIGMATE_LLM_LIVE=1` | The live gate. Required to leave the skeleton state; with the gate on and the seam unimplemented the provider returns `needs_review` with a `llm:seam-pending` note and an explanatory `refused_reason` so a misconfiguration in production surfaces immediately in the trace rather than silently falling back to a real model. |

The prompt is loaded from
`apps/backend/src/gigmate/extraction/prompts/role_b_extraction_v1.txt` by
default. The first line `prompt_version: X.Y.Z` is read into
`prompt_version`; missing or malformed files fall back to `0.0.0-skeleton`
so the trace still shows the placeholder state. The bundled file encodes the
hard rules (never emit `confirmed`, never grant execution authority, respect
the origin trust boundary) and is the single seam the next batch edits.

`case-008-llm-skeleton-needs-review` in the evaluation manifest pins the
skeleton behaviour when the manifest is run with `--provider llm`. Universal
needs_review cases (3, 4, 5, 6, 7) also pass under `llm` because the skeleton
refuses everything. The matched cases (1, 2) are expected to fail under `llm`
because the skeleton has no real model to call yet; they pass under the
default deterministic provider.

The switch applies to **both** paths: the worker's WAHA branch and the legacy
Replay `gigmate.understanding.extract` entry point both resolve the provider
through `gigmate.extraction.provider()`. With
`GIGMATE_EXTRACTION_PROVIDER=disabled`, Replay jobs end with
`STUB_UNSUPPORTED_INPUT` (no change rows) and live jobs end with
`EXTRACTION_NEEDS_REVIEW` (evidence retained, no change rows). Unknown
provider names raise instead of silently falling back.

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

Real WhatsApp content currently never reaches step 6 because the worker marks
every WAHA request `origin="live"` and the deterministic provider refuses
live-origin input regardless of text. This is intentional; lifting the guard
is a separately authorized batch that must add a real-model provider and
harden the seam with prompt-injection tests.

### Retention

`Proposal` and `ModelCallTrace` rows reference the inbox receipt
(`proposals.event_id`) and share its 30-day retention window.
`waha_ingress.purge_expired` deletes traces, then proposals, then receipts in
that order so the foreign keys stay satisfied; the purge result counts both
(`deleted_proposals`, `deleted_traces`). Confirmed business changes live on
the work order (`requirement_changes`) and are intentionally retained past
the receipt window.

## Evaluation harness

`scripts/run_evaluation.py` runs every case in
`contracts/evaluation/manifest.json` through the configured provider,
persists `EvaluationRun` + `EvaluationCaseRecord` rows and writes a JSON
report. Cases assert assignment, minimum confidence and expected change
fields. Seven synthetic cases currently cover known reschedule, known
available, unknown live text, no-order-linkage, multi-order ambiguity,
prompt-injection attempts and live-origin input with fixture-equal text.

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

- Real-model provider integration: replace
  `gigmate.extraction.llm.LLMProvider._invoke_model` and `_parse_response`
  with a real SDK call, wire credentials server-side, remove the live gate,
  and add the prompt-injection regression suite + latency budget. The seam,
  registry entry, prompt versioning, `llm:seam-pending` trace notes and
  `case-008-llm-skeleton-needs-review` evaluation case are all in place so
  this batch only has to fill in the two seam methods.
- D frontend review surface for `pending_change_ids` produced by real
  providers; current Replay cards already accept them but a real provider
  round-trip is required before frontend changes ship.
- Tighten `unresolved_questions` rendering for merchant review once a real
  provider exists.
