# Role B extraction subsystem

2026-10-10 media batch 2: A now supplies frozen provider sending time/merchant-selected timezone and reviewed read-only evidence. B must implement real MediaProcessor.process/reconcile separately from text extraction; C must agree attachment provenance and revalidate before business promotion. Missing time stays unresolved, and this does not enable external sending. See [media protocol](role-a-media-ingestion.md).

2026-10-10 media handoff: [A's media agreement](role-a-media-ingestion.md) supplies scoped bytes, immutable request/source/hash identifiers, source/context-bound result storage and review. B owns the real OCR/ASR/parser/GenAI factory and read-only reconciliation. No real adapter has been added by A; retain the existing deterministic live-input guard. Media snapshot evidence must not be cast into an existing canonical message revision or directly materialized as a confirmed work-order change. Review also binds expected_result_job_id so a new result cannot inherit an old review.

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
| Unknown name | Raise at startup; never silently fall back. |

Tests inject providers through
`gigmate.extraction.registry._reset_provider_for_testing` to avoid touching
process-level state.

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

## Media processor (Role B for WAHA attachments)

Updated: 2026-10-10. This section ships the real-model processor that fills
the seam introduced by the [WAHA media ingestion batch](role-a-waha-handoff.md).
A owns storage, leases, authorization and review; B owns OCR / ASR / parsing
/ GenAI through this processor. The processor only emits
`WahaMediaResult` proposals — merchant confirmation is enforced downstream by
`WahaMediaEvidence.business_confirmation_required`, never on the B side.

### Seam contract

`gigmate.media_processing.MediaProcessor` (Protocol) defines two methods:

* `process(request: MediaInput) -> WahaMediaResult` — B uses `request_id` for
  vendor-side idempotency and reconciliation; output is proposals only.
* `reconcile(request_id) -> WahaMediaResult | None` — read-only lookup; never
  resubmit. `None` means the result is still unknown; the worker must call
  this on the next tick rather than re-issuing `process()`.

A loads the implementation through the environment variable
`GIGMATE_MEDIA_PROCESSOR_FACTORY="gigmate.media.processor:MediaProcessorImpl"`.
`MediaInput` deliberately exposes no `api_key`, `provider_url` or
`authorization` attribute; the seam test in `test_waha_media.py` and the type
test in `test_media_processor.py` lock this down.

### Two-gate safety net

Two gates must be open before the processor contacts any vendor:

1. **Module-level `_ENABLED` flag** in
   `apps/backend/src/gigmate/media/processor.py` — `False` in this batch. While
   `False` the processor refuses every call with `ProcessingUnavailable`
   *before* it reads any environment variable. This is the safety net that
   prevents a future contributor from silently turning the seam on by exporting
   the operator switch.
2. **`GIGMATE_MEDIA_LIVE=1`** — operator switch. Even after the class flag is
   flipped to `True`, the processor still refuses every call unless this
   variable is exported. The two are checked in order: seam flag → live gate
   → API key present → live-origin guard → vendor call. With the seam flag
   `False` the call is refused before any configuration is read, so a
   misconfigured deployment cannot accidentally emit a real network request.

Additional guards:

* `GIGMATE_MEDIA_API_KEY` must be set, otherwise `ProcessingUnavailable`.
* `GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN=1` is required to send real customer
  attachments to the model; without it the processor refuses
  `request.origin == "live"` and requires synthetic origin.
* The processor never accepts credentials or model endpoints over HTTP. The
  factory string comes from a server-side env var and is parsed by
  `importlib`; no HTTP argument can inject code.

### Vendor routing and configuration

| Variable | Purpose |
| --- | --- |
| `GIGMATE_MEDIA_CHAT_VENDOR` | Chat-completions vendor (`deepseek`, `openai`, `custom`). Default `deepseek`. |
| `GIGMATE_MEDIA_CHAT_MODEL` | Model identifier for chat-completions (e.g. `deepseek-chat`, `gpt-4o-mini`). Default per vendor. |
| `GIGMATE_MEDIA_AUDIO_VENDOR` | Transcription vendor (`openai`, `custom`). Default `openai`. |
| `GIGMATE_MEDIA_AUDIO_MODEL` | Model identifier for transcriptions (e.g. `whisper-1`). |
| `GIGMATE_MEDIA_ENDPOINT` | Optional base URL override for both vendors. |
| `GIGMATE_MEDIA_PROMPT_PATH` | Optional override of the bundled prompt file. |

MIME routing (in `gigmate.media.routing`):

| MIME | Dispatch | Vendor adapter |
| --- | --- | --- |
| `image/png`, `image/jpeg`, `image/webp` | `ocr` | chat-completions with vision input |
| `audio/ogg`, `audio/mpeg`, `audio/wav`, `audio/mp4`, `audio/x-m4a` | `asr` | `/v1/audio/transcriptions` |
| `application/pdf` | `pdf` | chat-completions with text extraction |
| `text/plain` | `text` | chat-completions |

Anything outside this set is refused with `ProcessingUnavailable` before the
vendor is contacted. A's whitelist remains authoritative; B only consumes
the canonical types.

### Exception semantics

The processor follows the contract documented in
`gigmate.media_processing`:

* `ProcessingUnavailable` — no vendor request was submitted. Raised when the
  gates are closed, the vendor is unknown, the API key is missing, the prompt
  file is malformed, or the MIME is unsupported. The worker translates this
  to `MEDIA_PROCESSOR_NOT_CONFIGURED` and the download artefact is preserved
  for retry.
* `ProcessingUncertain` — the vendor call may have been submitted (charged).
  Raised on 4xx, 5xx, timeouts, network errors and vendor-side schema
  failures. The worker translates this to
  `MEDIA_PROCESSING_RESULT_UNKNOWN` and uses `reconcile()` rather than
  automatic resubmission.
* `MediaIntegrationPending` (private) — raised inside the vendor adapter when
  configuration is incomplete; the processor translates to
  `ProcessingUnavailable`.
* `MediaVendorRejected` (private) — raised inside the vendor adapter on 4xx
  / 5xx; the processor translates to `ProcessingUncertain`.

`reconcile()` returns `None` in this batch because chat-completions vendors
do not expose a stable request-id lookup. Operators that need vendor-side
lookup must extend the processor explicitly; the default never silently
resubmits.

### Prompt loading failure modes

The prompt is loaded from
`apps/backend/src/gigmate/media/prompts/role_b_media_v1.txt` by default
(overridable via `GIGMATE_MEDIA_PROMPT_PATH`). The first line matching
`prompt_version: X.Y.Z` is read into the `prompt_version` field on the
result. Every failure mode is caught explicitly:

* File missing / `OSError` → refusal with `ProcessingUnavailable`.
* Non-UTF-8 bytes (`UnicodeDecodeError`) → refusal with `ProcessingUnavailable`.
* `prompt_version:` header line absent → refusal with `ProcessingUnavailable`.
* Header present but value empty → refusal with `ProcessingUnavailable`.

In every case the worker records the refusal as
`MEDIA_PROCESSOR_NOT_CONFIGURED` rather than retrying into a malformed
prompt.

### Operator smoke

`scripts/smoke_media.py` is the operator-side manual smoke (not in CI). It
requires both gates to be open and prints the parsed proposal JSON:

```text
.venv/bin/python scripts/smoke_media.py --mime image/png --file path/to/sample.png
.venv/bin/python scripts/smoke_media.py --mime audio/ogg --file path/to/sample.ogg
```

Without the seam flag the script prints the refusal reason and exits `0`.
CI does not run this script; a real call requires the operator's vendor key.

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
.venv/bin/python -m ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/smoke_media.py scripts/run_evaluation.py
.venv/bin/python -m ruff format --check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/smoke_media.py scripts/run_evaluation.py
.venv/bin/python scripts/export_contracts.py --check
.venv/bin/python -m alembic -c apps/backend/alembic.ini upgrade head
.venv/bin/python -m alembic -c apps/backend/alembic.ini check
.venv/bin/python -m pytest apps/backend/tests/test_media_processor.py apps/backend/tests -q --basetemp=local-data/pytest
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
- Vendor-side `reconcile()` for media: chat-completions vendors do not expose
  a stable request-id lookup, so the current implementation returns `None`
  and the worker must wait for a manual retry. A future batch can add a
  vendor-specific lookup once the seam flag is open and operators need it.
- B-side prompt-injection regression suite for media attachments (image OCR
  + audio ASR + PDF parsing). The processor trusts the bundled prompt today
  and refuses the call only on malformed input; a separately authorized batch
  should add fixtures for adversarial inputs.
