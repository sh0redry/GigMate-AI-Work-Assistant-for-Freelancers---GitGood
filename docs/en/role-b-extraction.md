# Role B extraction subsystem

2026-10-09 integration update: [WAHA/extraction acceptance](role-a-integration-acceptance.md) records the merged control/worker handoff. Current Alembic head is `0007_merge_waha_extraction`, joining the unchanged B evidence migration and A's controls/provider-sample branch. Windows tests use pytest-owned temporary files; the default provider still refuses live extraction and no real-model/network integration was added.

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

This batch ships the provider as a skeleton on purpose: the next authorized
batch must replace `_invoke_model` and `_parse_response` *and* flip the
class flag `LLMProvider._SKELETON_SEAM` to `False`. Until then the module
performs no real network calls regardless of which environment variables are
exported, and only `GIGMATE_LLM_API_KEY` is read; `OPENAI_API_KEY` /
`ANTHROPIC_API_KEY` are deliberately not consulted so model credentials stay
under the operator's explicit control.

Configuration (environment variables, all optional until the seam is filled):

| Variable | Purpose |
| --- | --- |
| `GIGMATE_LLM_PROVIDER` | Vendor name (`deepseek`, `openai`, `custom`). Used in `model_version` and as a sanity check that the operator picked a vendor this build supports. |
| `GIGMATE_LLM_MODEL` | Model identifier (e.g. `deepseek-chat`, `gpt-4o-mini`). Default marker `skeleton:pending` until configured. |
| `GIGMATE_LLM_API_KEY` | Server-side only. The provider reads this on every call; it is never stored on the instance or logged. |
| `GIGMATE_LLM_ENDPOINT` | Optional base URL override (defaults to `https://api.deepseek.com`). |
| `GIGMATE_LLM_PROMPT_PATH` | Optional override of the bundled prompt file. |
| `GIGMATE_LLM_LIVE=1` | The explicit live gate. Required to actually invoke the model once `_SKELETON_SEAM` is flipped; until then it is the second line of defence after the class flag. |
| `GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1` | Opt-in switch that lets `request.origin == "live"` traffic reach the model once the skeleton flag is open. Defaults to off. |

#### Two-gate safety net

Two gates must be open before `_invoke_model` runs:

1. **Class flag `LLMProvider._SKELETON_SEAM`** — `True` in this batch.
   While `True` the provider refuses every call with `llm:seam-pending` no
   matter which environment variables are exported. This is the safety
   net that prevents a future implementation of `_invoke_model` from
   silently flipping into "real call" mode if the next batch only fills
   in the seam method.
2. **`GIGMATE_LLM_LIVE=1`** — operator switch. Even after the class flag
   is flipped to `False`, the provider still refuses every call unless
   `GIGMATE_LLM_LIVE=1` is exported.

The two are checked in order: skeleton flag → live gate → wire check
(vendor known, key set) → live-origin guard → `_invoke_model`. With the
skeleton flag `True` the call is refused before configuration is even
read, so a misconfigured deployment cannot accidentally emit a real
network request.

#### Prompt loading failure modes

The prompt is loaded from
`apps/backend/src/gigmate/extraction/prompts/role_b_extraction_v1.txt` by
default (overridable via `GIGMATE_LLM_PROMPT_PATH`). The first line that
matches `prompt_version: X.Y.Z` is read into `prompt_version`. Every
failure mode is caught explicitly and recorded on
`LLMProvider._prompt_load_error`:

- File missing / `OSError` → placeholder `0.0.0-skeleton` + refusal.
- Non-UTF-8 bytes (`UnicodeDecodeError`) → placeholder + refusal.
- `prompt_version:` header line absent → placeholder + refusal.
- `prompt_version:` header present but value empty → placeholder + refusal.

In every case the outcome carries `notes=("llm:prompt-malformed",)` with a
descriptive `refused_reason`, the `Proposal` row records
`prompt_version = "0.0.0-skeleton"` and the `ModelCallTrace` row keeps
the descriptive cause — the worker never raises into its broad
`except Exception` handler, so a malformed prompt file cannot cause a
`PROCESSING_FAILED` retry storm.

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

- Real-model provider integration: the next authorized batch must
  (a) replace `gigmate.extraction.llm.LLMProvider._invoke_model` and
  `_parse_response` with a real SDK call, (b) flip
  `LLMProvider._SKELETON_SEAM` to `False`, and (c) gate real
  authorization + live-origin flow with their own dedicated review
  (the live-origin guard currently lives in this provider but is
  unreachable while the seam flag is `True`). Adding the
  prompt-injection regression suite + latency budget is also part of
  that batch. The seam, prompt-versioning fallback chain,
  `llm:prompt-malformed` and `llm:seam-pending` trace notes, the
  `case-008-llm-skeleton-needs-review` evaluation case and the
  `_prompt_load_error` audit attribute are all in place.
- D frontend review surface for `pending_change_ids` produced by real
  providers; current Replay cards already accept them but a real provider
  round-trip is required before frontend changes ship.
- Tighten `unresolved_questions` rendering for merchant review once a real
  provider exists.
