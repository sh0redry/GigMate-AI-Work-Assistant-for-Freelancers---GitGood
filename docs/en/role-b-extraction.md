# Role B extraction subsystem

## Pre-activation review fixes, round 2 (PR #31) — 2026-10-17

The five review threads of [PR #31](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/31) stayed open after the first fix batch: each finding was re-reproduced against synthetic data with a fake transport and a fake clock, and the first fix turned out to be insufficient for the case the reviewer actually described. All five are re-fixed here, still **without** flipping the seam: `LLMProvider._SKELETON_SEAM` stays `True`, `gigmate.media.processor._ENABLED` stays `False`, and no real vendor request, credential, network call or customer message is involved. This is a correctness batch, not an activation.

- **P2-1 — a scalar `httpx` timeout does not bound one attempt.** Round 1 granted each attempt the *remaining* budget as its timeout, but `httpx` copies one timeout value into connect / read / write / pool **separately**, so a request granted "30 s" could spend 30 s connecting and then 30 s reading. The clock was only consulted between attempts, so one extraction still ran 60 s against the declared 45 s deadline. `_attempt_timeout()` now splits the remaining budget across the operations — connect ≤ 5 s, write ≤ 5 s, pool ≤ 1 s, read = what is left, capped by `_REQUEST_TIMEOUT_S` — so the largest wall time one attempt can spend is the remaining budget itself, and an attempt whose read budget would fall below `_MIN_REQUEST_TIMEOUT_S = 1s` is not issued. Measured with a fake clock that spends the whole granted budget: **20.0 s**, the total budget — see below, it is deliberately below the worker's 30 s lease (previously 60.0 s against a declared 45 s).
- **P2-2 — a zero budget still reached the vendor.** Round 1 compared the bounded worst case of one attempt against its share of the budget. With a zero-priced vendor (`GIGMATE_LLM_COST_INPUT_USD_PER_1K=0` / `GIGMATE_LLM_COST_OUTPUT_USD_PER_1K=0`, e.g. a local model) the worst case is `0` as well, and `0 > 0` is false, so the request was issued against a budget of zero. `_cost_plan` now refuses a non-positive budget before any pricing arithmetic (`llm:cost-budget-exceeded`), and `validate_provider_config()` reports a *negative* budget at startup as `llm:cost-budget-invalid`.
- **P2-3 — equality is not identity for the context version.** The guard compared the echoed `base_context_version` with `!=`, but `7.0 == 7` and `True == 1` in Python, so a non-integer echo of the server's version was accepted. The model-supplied value must now be an `int` (and not a `bool`) equal to `request.context_version`; anything else is `llm:response-provenance-failed:base_context_version`.
- **P2-4 — the shape guard is complete.** `changes` and `sources` were checked, but `candidates`, `unresolved_questions` and the suggestion's `missing_fields` / `unresolved_questions` still reached Pydantic unvalidated, so a wrong shape there surfaced as a schema code after the model's version of the facts had already been read. Every collection the guard reads is now shape-checked first, each with its own stable code (`…:candidates-shape`, `…:unresolved-questions-shape`, `…:missing-fields-shape`, `…:suggested-questions-shape`).
- **P2-5 — the date guard is keyed on the field, not only on the value shape.** Round 1 covered `kind: instant`, but `FieldValue` also admits free text and numbers, so a model that wrote `"明天下午三点"` — or a bare `"2026-10-18"` with no timezone — into a `deadline` / `schedule` change still produced a date the customer never stated, and it was promoted as `matched`. Any non-null value on a date-bearing field now needs the basis; only a missing value (`None`, "the customer has not said yet") is exempt. New regressions cover `instant`, a missing basis, an unparseable or zone-less `message_received_at`, and a real relative date (2026-10-07 in `Asia/Hong_Kong` + "下星期四" → `2026-10-15T07:00:00Z`) that is accepted with the basis and refused without it.

Evidence, all synthetic: `apps/backend/tests/test_extraction_gates.py` **62 passed** (39 before this round), the pre-activation suite (gates + batch2 + batch3 + batch3_provider + extraction) **169 passed**; full backend suite **829 passed / 25 skipped / 12 failed**, the 12 being the pre-existing native-macOS PDF refusals (`MEDIA_PDF_LIMIT_UNAVAILABLE`) that fail identically on unmodified main. Ruff check/format **105 files**, `scripts/export_contracts.py --check` synchronized, `check_baseline.py` **84 Markdown / 993 local links**, `alembic check` clean with single head `0018_model_call_cost`, offline evaluation harness **7 passed / 0 failed** at prompt 1.2.0. No new migration, contract or API surface: the changes are internal to `gigmate.extraction.llm` plus regression tests. Not verified: PostgreSQL concurrency/locking (no `TEST_DATABASE_URL`), the Linux-container PDF re-run, and any real vendor behaviour — in particular whether a real vendor respects a split timeout, which only a live run can show.

## Pre-activation review fixes (PR #31) — 2026-10-16

Independent review of [PR #31](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/31) at `a4e6b8a` raised five P2 findings, each reproduced by the reviewer against synthetic data with a fake transport and a fake clock — not from static reading. All five are fixed here, still **without** flipping the seam: `LLMProvider._SKELETON_SEAM` stays `True`, `gigmate.media.processor._ENABLED` stays `False`, and no real vendor request, credential, network call or customer message is involved. This is a correctness batch, not an activation.

- **P2-1 — the total deadline now applies to every request.** `_call_chat_completion` used to hand every attempt the fixed 30 s per-attempt timeout and only check the total budget after a failure, so a 30 s timeout followed by a retry ran 60 s against the declared 45 s deadline. Each attempt now inherits the *remaining* total budget as its own timeout (`min(_REQUEST_TIMEOUT_S, remaining)`); an attempt that would get less than `_MIN_REQUEST_TIMEOUT_S = 1s` is not issued at all; and a response that only arrives after `_TOTAL_DEADLINE_S` is refused with the stable code `llm:deadline-exceeded` — a late success is worthless once the worker's lease has run out, and it is never retried. Round 2 (above) replaced the scalar timeout with a per-operation split, because `httpx` applies one value to each operation and a single attempt could still spend the budget twice.
- **P2-2 — the cost ceiling is enforced before the call is paid for.** The old cost check ran after the vendor had already spent the money, so it could only refuse a proposal, never a payment; with the budget set to 0 the call was still issued. `_cost_plan` now runs first: the budget is divided across the `_MAX_RETRIES + 1` attempts and the bounded worst case of one attempt (estimated prompt tokens + the configured output ceiling) must fit its share, otherwise the request is never issued (`llm:cost-budget-exceeded`, or `llm:cost-input-too-large` when the prompt itself exceeds `GIGMATE_LLM_MAX_INPUT_TOKENS`). The request carries that output ceiling as `max_tokens`, so the vendor is told the bound the budget was computed from, and non-positive ceilings are reported at startup as `llm:cost-tokens-invalid`. The post-call check is kept as the second line of defence: a vendor that bills more than the budget allows still cannot promote a proposal.
- **P2-3 — the model's context version is bound too.** The provenance guard validated `base_work_order_version` but not `base_context_version`, and the later `setdefault` could not overwrite a model-supplied value, so a response carrying `base_context_version=999` against a `context_version=7` request still reached a `matched` proposal whose version then flowed into `Proposal` / `RequirementChange`. A differing value is now refused with `llm:response-provenance-failed:base_context_version`, and the server's own value is assigned afterwards.
- **P2-4 — collections are type-checked before they are iterated.** The provenance guard runs before Pydantic and iterated unvalidated `changes` / `sources`, so legal JSON such as `"changes": 17` or `"changes": true` raised an uncaught `TypeError` out of `propose` — the worker would have retried the whole job and paid for the same call twice instead of recording a stable `needs_review`. Those shapes now return `llm:response-provenance-failed:changes-shape` / `:source-shape` (and the suggestion equivalents).
- **P2-5 — the time-basis guard covers `instant`.** The check only accepted `timed` / `date_only`, so `InstantDeadline` (`kind: instant`, the "明天交稿" shape) — the most common relative date a customer types — walked straight through gate 4 with a model-invented timestamp. All date-bearing kinds are now guarded, on both the old and the new value.

Evidence, all synthetic: the five findings' counter-cases are now regression tests. `apps/backend/tests/test_extraction_gates.py` **39 passed** (27 at `a4e6b8a`) and `test_extraction_batch2.py` **50 passed** (40 at `a4e6b8a`); the pre-activation suite measured in this working tree, which also carries the in-progress batch-3 files, is **106 passed**. Full backend suite **745 passed / 25 skipped / 12 failed**, the 12 being the pre-existing native-macOS PDF refusals (`MEDIA_PDF_LIMIT_UNAVAILABLE`) that fail identically on unmodified main. Ruff check/format **100 files**, `scripts/export_contracts.py --check` synchronized, `check_baseline.py` **82 Markdown / 967 local links**, Alembic single head `0018_model_call_cost` with a SQLite upgrade→downgrade→upgrade round trip and no drift (`alembic check` clean), offline evaluation harness **7 passed / 0 failed** at prompt 1.2.0. No new migration, contract or API surface: the changes are internal to `gigmate.extraction.llm` plus the two new `GIGMATE_LLM_MAX_*_TOKENS` operator settings. Not verified: PostgreSQL concurrency/locking (no `TEST_DATABASE_URL` configured), the Linux-container PDF re-run, and any real vendor behaviour.

## Pre-activation review fixes, round 2 continued — the findings at `038ae3b` — 2026-10-17

Independent review of this PR at `038ae3b` confirmed P2-3, P2-4, P2-5 and the zero-budget part of P2-2 really were fixed, and raised four remaining holes. All four are closed here, again **without** flipping the seam (`LLMProvider._SKELETON_SEAM` stays `True`, `gigmate.media.processor._ENABLED` stays `False`) and with no real vendor, credential, network call or customer message.

- **P2-1 (round 2) — the deadline stops the transfer, not just the wait.** Bounding each httpx phase still let a body that kept arriving before every read timeout outlive the total budget: `client.post()` read the whole response before the clock was looked at again, and the reviewer measured about 0.36 s against a 0.18 s budget with real loopback HTTP. `_call_chat_completion` now reads with `client.stream(...)`, re-checks the wall clock between chunks, and closes the stream before giving up — closing tears the connection down instead of returning early while data keeps arriving. `_TOTAL_DEADLINE_S` also drops from 45 s to 20 s: `gigmate.worker` reclaims a job after 30 s, so a longer budget let a second worker start the same extraction while the first was still in flight (`test_gate3_total_deadline_fits_inside_the_worker_lease` asserts the relation, and `_WORKER_LEASE_S` documents it).
- **P2-2 (round 2) — the token bound can no longer under-count.** `ceil(len / 3)` is an average, not a bound: with the real tokenizer every CJK character is a token (three bytes), so Chinese prompts were priced at roughly a third of their real worst case. `_estimate_tokens` now returns a provable upper bound — the UTF-8 byte count, which bounds every byte-level BPE because each token covers at least one byte — plus `_CHAT_FRAMING_TOKENS` for the role markers and separators that are billed on top of the rendered text. A model whose tokenizer carries no such guarantee (see `_BYTE_LEVEL_BPE_MODELS`) is refused with `llm:cost-estimate-unsupported` rather than having an average reported as a ceiling, so the hard-ceiling gate stays honestly unmet. `GIGMATE_LLM_MAX_INPUT_TOKENS` now defaults to 16000 because it is compared against that bound, which runs roughly 3–4 bytes per real token.
- **P2-6 — the vendor envelope is type-checked before it is subscripted.** `{"choices": 17}` and `{"choices": [{"message": 17}]}` are legal JSON and raised `TypeError: 'int' object is not subscriptable` straight out of the vendor boundary, which the worker turned into a job failure and retry with no evidence row — and, after activation, repeated payment for the same call. `_envelope_content` checks every level and `_MalformedVendorResponse` maps every violation to the recorded note `llm:response-malformed` together with its request id.
- **P2-7 — money that cannot bound money is refused at startup.** `Decimal` accepts `NaN` and `Infinity`, so `GIGMATE_LLM_COST_BUDGET_USD=NaN` passed `validate_provider_config()` and could later raise `InvalidOperation` inside a paid comparison. `_money` requires a finite, non-negative amount; anything else is reported as `llm:cost-budget-invalid` / `llm:cost-pricing-invalid` at boot and refuses the call before any request is issued. A finite zero budget still refuses in `_cost_plan` exactly as before.

Evidence, all synthetic: new `apps/backend/tests/test_extraction_boundaries.py` **24 passed**, including a 400-chunk trickle body that is abandoned in under a second against a 0.05 s deadline with the producer generator closed (the review's complaint was precisely that returning early while the transfer continues is not an abort), five malformed envelopes, the CJK bound, the unbounded-tokenizer refusal, and NaN/Infinity/negative money. Existing extraction suites after the switch to streaming plus the new boundaries: `test_extraction.py`, `test_extraction_batch2.py`, `test_extraction_batch3.py`, `test_extraction_batch3_provider.py`, `test_extraction_gates.py` and `test_extraction_boundaries.py` **194 passed** — their fake clients now answer `stream` through `_StreamedResponse`, because a double that only answers `post` no longer describes a real httpx client. Full backend suite **854 passed / 25 skipped / 12 failed**, the 12 being the pre-existing native-macOS PDF refusals that fail identically on unmodified main. Ruff check/format **104 files**, `scripts/export_contracts.py --check` synchronized, `check_baseline.py` **84 Markdown / 995 local links**. Not verified: PostgreSQL concurrency/locking, the containerized PDF re-run, real vendor behaviour, and any live token count — the bound is proven structurally from byte-level BPE, not measured against a vendor reply.

## Pre-activation gates implemented — 2026-10-16

All five ["Pre-activation acceptance gates"](#pre-activation-acceptance-gates) below now have implementation and regression coverage in `apps/backend/tests/test_extraction_gates.py`. The seam is still closed: `LLMProvider._SKELETON_SEAM` remains `True` and `gigmate.media.processor._ENABLED` remains `False`, so no real vendor request, real credential or live customer message is involved. This batch does **not** authorize activation.

What changed:

- **Gate 1 — provenance re-binding.** `_parse_response` re-binds `conversation_id`, `work_order_id` (must be a member of `candidate_work_order_ids`), `base_work_order_version` (must equal the version the worker resolved), `base_context_version` (added by the P2-3 review fix) and every `sources[].message_id` / `message_revision` to the request actually issued. A mismatch returns `needs_review` with the stable note `llm:response-provenance-failed` and a `llm:response-provenance-failed:<field>` reason; it can never become `matched`. Collections are type-checked before they are iterated (P2-4), so a non-list `changes` / `sources` is a stable refusal rather than an uncaught `TypeError`.
- **Gate 2 — vendor/endpoint semantics.** Each known vendor ships its own documented default endpoint (`deepseek` → `https://api.deepseek.com`, `openai` → `https://api.openai.com`); `custom` has none and requires `GIGMATE_LLM_ENDPOINT`. Unknown vendors are refused with `llm:vendor-unknown`, a non-URL override with `llm:endpoint-invalid`, and an override that equals another vendor's documented default with `llm:vendor-endpoint-mismatch`.
- **Gate 3 — retry, budget and correlation.** Total wall time per extraction is bounded (`_TOTAL_DEADLINE_S = 45s`) and a retry is only issued while budget remains; only transient classes are retried (`httpx` timeouts/connect errors/resets and HTTP `5xx`) — `4xx`, parse and shape failures are never retried. Every attempt carries one persistent `X-Gigmate-Request-Id` header, and that id is persisted on `model_call_traces.request_id` (migration `0017_model_call_request_id`) so a trace can be correlated with the vendor's log. The P2-1 review fix makes the deadline a per-request budget as well: every attempt is granted only the *remaining* time, an attempt that cannot get at least `_MIN_REQUEST_TIMEOUT_S = 1s` is not issued, and a response arriving after the deadline is refused with `llm:deadline-exceeded` instead of being promoted. The round-2 fix splits that remaining budget across the `httpx` operations (`_attempt_timeout`) so their **sum** — not each one separately — is what one attempt may spend.
- **Gate 4 — real time basis.** `ExtractionRequest` carries server-attached `message_received_at` (the connector's sending time, UTC `Z`) and `workspace_timezone` (operator IANA setting, `GIGMATE_WORKSPACE_TIMEZONE`). The prompt (`role_b_extraction_v1.txt`, bumped to **1.1.0**) now tells the model to resolve relative dates only against `time_basis`, and to emit UTC `Z`. When the basis is missing or invalid the provider refuses any date-bearing change with `llm:time-basis-missing` instead of guessing; non-date fields (address/summary) are unaffected. The P2-5 review fix extends "date-bearing" to every contract kind — `timed`, `date_only` **and** `instant` (`InstantDeadline`, the "明天交稿" shape) — on both the old and the new value; the round-2 fix makes the guard field-keyed, so a date written as free text or a bare number on `schedule` / `deadline` needs the basis too. The worker also re-reads the conversation context and work-order version after the call and discards a result computed against a stale snapshot, as well as any result produced after its own lease expired.
- **Gate 5 — sanitised diagnostics.** Failure reasons are stable codes (`llm:http-failed:timeout`, `llm:http-failed:status-5xx`, `llm:response-malformed:json`, `llm:response-schema-failed:<field path>`, `llm:prompt-load-failed:…`). No exception class name, exception message, endpoint host, vendor name or key fragment is echoed into `refused_reason`.

Still open before activation (not blocked by code): the separately authorized real-credential/live-origin flow, a latency budget measured under real load, and moving vendor I/O fully outside the worker's row lock — the last one is a structural worker change that must be agreed with A/C. `docs/en/implementation-status.md` records the verification evidence for this batch.

## Pre-activation batch 2 — cost boundary, startup validation, injection regression — 2026-10-16

Three of the remaining activation follow-ups are implemented in this batch, again
**without** flipping the seam: `LLMProvider._SKELETON_SEAM` stays `True` and
`gigmate.media.processor._ENABLED` stays `False`, so no real vendor request,
credential or customer message is involved and the new code paths are exercised
through the same gate-open test subclass used for the five gates. Coverage lives
in `apps/backend/tests/test_extraction_batch2.py`.

- **Cost boundary.** Every call is priced against a built-in per-1K table keyed
  by `(vendor, model)`, overridable with `GIGMATE_LLM_COST_INPUT_USD_PER_1K` /
  `GIGMATE_LLM_COST_OUTPUT_USD_PER_1K`.   The budget lives in
  `GIGMATE_LLM_COST_BUDGET_USD` (default `0.10` USD per call). The P2-2 review
  fix makes this a ceiling that holds *before* money is spent: `_cost_plan`
  divides the budget across the `_MAX_RETRIES + 1` attempts and prices the
  bounded worst case of one attempt (estimated prompt tokens + the configured
  output ceiling) — a call whose worst case does not fit its share is refused
  with `llm:cost-budget-exceeded` without being issued, and a prompt larger
  than `GIGMATE_LLM_MAX_INPUT_TOKENS` is refused with `llm:cost-input-too-large`
  rather than truncated. The request carries the output ceiling as
  `max_tokens` (`GIGMATE_LLM_MAX_OUTPUT_TOKENS`), and non-positive ceilings are
  reported at startup as `llm:cost-tokens-invalid`. The post-call check is kept
  as the second line of defence: a response whose computed cost exceeds the
  budget is still refused with `llm:cost-budget-exceeded`. A call that cannot be
  priced at all is
  refused *before* it is issued with `llm:cost-pricing-missing` (unknown model and
  no override), `llm:cost-pricing-partial` (only one of the two overrides set) or
  `llm:cost-pricing-invalid`. A vendor that omits its `usage` block is not
  silently treated as free: the trace records `llm:cost-usage-missing` (or
  `llm:cost-usage-invalid` for a malformed block) and leaves `cost_usd` null.
  `model_call_traces` gained `input_tokens`, `output_tokens` and `cost_usd`
  (migration `0018_model_call_cost`), so an operator can reconstruct spend
  without re-deriving it. The post-call check still runs after the HTTP and
  parse gates because a `4xx` response produces no usage data and a parse
  failure cannot be charged to a budget; what it is left to catch is a vendor
  that ignored the `max_tokens` it was given.
- **Provider configuration startup validation.**
  `gigmate.extraction.llm.validate_provider_config()` is a pure audit that takes
  no session and opens no socket, so the worker can call it at boot via
  `gigmate.worker.audit_provider_config()`. It reports
  `llm:vendor-unknown`, `llm:endpoint-invalid`, `llm:vendor-endpoint-mismatch`,
  `llm:endpoint-required`, `llm:prompt-path-invalid`,
  `workspace-timezone-invalid`, the four cost codes above and
  `llm:api-key-missing` (only when `GIGMATE_LLM_LIVE=1`). Policy: with
  `GIGMATE_LLM_LIVE=1` any issue makes the worker refuse to start, because a
  process that is about to issue real vendor calls must not run against a
  configuration it already knows is broken; with the live gate off the same
  issues are logged as warnings, since the closed seam refuses every call anyway.
  Passing an `env` mapping lets tests drive the audit without mutating the real
  environment.
- **Prompt-injection regression suite.** `contracts/evaluation/injection.json`
  ships nine synthetic cases, each pairing a customer message that carries an
  instruction-injection attempt with a `compromised_response` that a fooled model
  would emit. The suite is driven by
  `test_extraction_batch2.py::test_injection_regression_suite`, which asserts that
  no case ever produces a `matched` proposal and that each one surfaces the
  expected stable code: `llm:response-provenance-failed` (foreign
  `work_order_id` / `conversation_id` / stale `base_work_order_version` /
  fabricated source message), `llm:response-schema-failed` (AI marks a field
  `confirmed`, smuggled extra keys) and `llm:time-basis-missing` (date invented
  from the model's own "now"). This is the text-only suite; the media attachment
  (OCR / ASR / PDF) equivalent remains a separately authorized batch.

Still pending for activation: the real-credential / live-origin flow with its own
review, the latency budget under real load, the media-attachment injection suite,
and moving vendor I/O outside the worker lock.

## Pre-activation batch 4 — media-attachment injection regression — 2026-10-16

Attachment content is attacker-controlled, so the media seam gets the same
treatment the text seam already has. A new pure classifier
`gigmate.media.injection` scans every untrusted surface of one media result —
the merchant/attacker caption, the OCR text or locally parsed page text, the
ASR transcript, and the vendor's own `summary` / `suggestions` /
`unresolved_questions` — against a narrow bilingual pattern set
(ignore-previous-instructions, role override, authority claim, review bypass,
prompt exfiltration, instruction verbs). Matches are recorded as stable
`media:instruction-text-detected:<field>` markers on a new optional
`WahaMediaResult.injection_markers` field (default empty; the result rides an
existing JSON column, so no migration) and logged as `MEDIA_INJECTION_DETECTED`
with pattern ids and field names only, never the payload.

Detection is a flag, not a verdict. It never blocks, rewrites or trusts
content, and never grants or removes authority:
`WahaMediaEvidence.business_confirmation_required` stays `Literal[True]`, and
the test asserts that flipping it to `False` is rejected even for a flagged
result. The trade-off is stated deliberately: a marker costs a human a second
look, a missed instruction costs a wrong work order, so the bias is to flag —
and because that bias can annoy, `contracts/evaluation/media_injection.json`
pairs every attack with clean control cases that fail the suite if ordinary
merchant content is flagged. Nine synthetic cases cover an image caption and
its OCR text, a spoken instruction in an ASR transcript, a PDF hidden text
layer, a PDF model that both tries to retype page text and smuggles an
instruction into the business layer, and an instruction hidden in
`unresolved_questions`. The PDF path re-pins that page text stays local.

Still pending for activation: real media content. Nothing here has seen a real
image, audio clip, PDF or vendor response — the bytes are synthetic
placeholders and the payloads are scripted — so the false-positive rate of the
pattern set against real merchant content is unknown and operators should read
the markers before acting. The PDF end-to-end variant skips rather than passes
on native macOS, where the local parser refuses with
`MEDIA_PDF_LIMIT_UNAVAILABLE`; the suite therefore drives the PDF business layer
through `coerce_pdf_extraction` with the parser's output shape.

## Pre-activation batch 3 — new-work-order recognition, unknown outcomes, evaluation classification — 2026-10-16

Three more B-side follow-ups from issue #29, again **without** flipping the seam
(`_SKELETON_SEAM = True`, media `_ENABLED = False`). Coverage lives in
`apps/backend/tests/test_extraction_batch3.py`.

- **`new_work_order` recognition contract.** `ChangeProposal` gained an optional
  `new_work_order` block (`NewWorkOrderSuggestion`): a *summary*, recognised
  critical `fields` (each with its value, `sources` bound to the message
  revision the server actually issued and a `reason`), `missing_fields`,
  `unresolved_questions` and `confidence`. It is recognition output only — it
  never creates a work order, never marks anything confirmed and grants no
  execution authority; the merchant still creates the order manually, and
  customer proposal, customer confirmation and merchant approval stay separate
  facts. The contract forbids the block next to a `matched` assignment or a
  non-null `work_order_id`, so a model cannot smuggle a second job alongside a
  reschedule. Unknown values stay missing: a field the customer never supplied
  is omitted from `fields` (or kept null) and listed in `missing_fields`.
  The suggestion rides the existing proposal JSON, so no migration was needed
  and no `RequirementChange` row is ever produced for it.
  **Pending `llm.py`:** extending provenance re-binding (gate 1) to suggested
  fields — a suggestion citing a message the merchant never saw is refused with
  `llm:response-provenance-failed:suggested-source-message-id` — and extending
  the time-basis gate (gate 4) so a relative-date suggestion is refused the
  same way a relative-date change is. Both guards are written and pass locally,
  and are pinned by `test_extraction_batch3_provider.py` plus the `inj-010`
  injection fixture, but `llm.py` is being edited concurrently (review fix
  P2-1), so this commit ships the contract, prompt, evaluation and docs only;
  the provider-side half lands with `llm.py` in the next commit.
  This is the contract C's #26 manual-creation flow can consume; `case-001` and
  `case-004` now pin that the current deterministic provider emits **no**
  spurious suggestion.
- **Unknown vendor outcome for text extraction.** A timed-out or otherwise
  unanswered call is unknown, not silently failed. The policy is now written
  down and pinned by tests: one bounded retry (`_MAX_RETRIES = 1`, inside the
  `_TOTAL_DEADLINE_S` budget), both attempts carrying the *same* persistent
  request id, then a `needs_review` proposal with the stable refusal
  `llm:http-failed:timeout` and the request id persisted on the trace row for
  vendor-log reconciliation. There is no further resubmission, and because
  extraction never writes customer-visible state a duplicate vendor-side
  completion cannot create a business fact; the job stays for explicit review.
  The media path keeps its own documented stance (`reconcile()` returns `None`),
  so nothing is ever resolved by blind resend.
- **Evaluation classification surface.** `EvaluationCase` gained
  `expected_new_work_order`, `evaluate_case` reports `actual_new_work_order`,
  `refused_reason` and `notes` per case, and `scripts/run_evaluation.py` now
  emits a `classification` block: pass/fail per expected assignment, how many
  cases suggested a new order, the refusal codes seen and the failing case ids.
  This is the structure E can fill with real-target data later; the runs today
  remain synthetic and claim no production accuracy.

The prompt (`role_b_extraction_v1.txt`) is now **1.2.0**: it documents the
`new_work_order` output block, its "no candidates only" rule, its source
binding and the "unknown stays missing" rule.

Still pending for activation: the real-credential / live-origin flow with its own
review, the latency budget under real load, the joint revision/version
verification with C, the media-attachment injection suite, and moving vendor I/O
outside the worker lock.

## PDF resource isolation

The vendor preflight now calls a private child process, not pypdf in the business worker. Defaults: 20 seconds wall time, 512 MiB, one parser per worker process, 20 MiB input and 1 MiB serialized output. Trusted server settings `GIGMATE_PDF_TIMEOUT_SECONDS` (1–60) and `GIGMATE_PDF_MEMORY_MIB` (128–1024) are propagated to API/worker by the media Compose overlay; they are not request parameters. Existing page/segment/text bounds and partial coverage checks remain.

Windows starts the real base interpreter suspended, attaches a private Job Object with committed-memory/CPU/active-process limits and kill-on-close, then resumes it. A venv redirector must not receive the limit instead of the parser. Linux sets hard RLIMIT_AS/RLIMIT_CPU, disables core dumps, bounds descriptors and binds child lifetime to its parent. Only after a bounded startup response proves the expected PID is PDF data released. Native macOS fails closed with MEDIA_PDF_LIMIT_UNAVAILABLE; run the backend in the project's Linux Docker image. No unreliable native-memory fallback is advertised.

The child receives bytes through pipes without staging files, uses UTF-8, receives no model/WAHA/database environment or worker PYTHONPATH, and loads only the locked pypdf location. Output shape/count/page/text bounds are revalidated in the parent. Timeout/output failure terminates and reaps the private process and closes pipes; crashes are not success. Known pre-vendor PDF refusal codes are persisted on the media job rather than disguised as a missing processor. The worker has an independent heartbeat thread during parsing/model I/O; no new DB migration is needed.

Local preparation may take time. A now supplies a private `MediaInput.before_submit` callback which the shipped B processor invokes after parsing and immediately before client construction. It rechecks active account/connection/consent, original lease, source/context/control and attachment version/expiry in a short transaction. Cancellation during preparation therefore prevents a later model submission. This callable is not part of any prompt, HTTP or stored evidence shape; third-party processors must honor this handoff. A change after that final check cannot retroactively retract external I/O. The wall-time deadline includes startup and IPC; bounded process teardown may add a few seconds.

This is resource isolation, not a complete filesystem/network sandbox or malware scanner. Limits are per worker, not a global host quota; deployments must size worker count/host resources accordingly. Scanned PDF OCR, real models and shared AI deployment remain separate. No original deployment or session is changed by this batch. Resource checks run in Linux/Windows/macOS CI; macOS verifies explicit native refusal, not native parsing. Native Apple Silicon/Docker codec and real-file acceptance still require a teammate's own-account run.

Mechanisms: [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects), [extended memory limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information), [Python resource](https://docs.python.org/3/library/resource.html).

## PDF integration and in-flight model interruption — 2026-10-12

PR #21 includes the PDF branch at `0d91ad1`. Text-layer PDFs are parsed locally before client construction; the model cannot replace locally bound page text. Missing page text forces complete coverage down to partial. Crossing the text bound stops before extracting another page. Scanned PDFs remain unsupported. Output bounds are not a hard CPU/memory sandbox; parser resource isolation remains a real-activation gate.

Cancellation, pause/revocation and derivative expiry retain the attachment/request identity for in-flight processing or unresolved reconciliation. Late model content and reviews are suppressed, including after regrant. The original lease can record a definite return or an explicit pre-submission processing refusal, releasing the gate without restoring content; an uncertain outcome retains result_unknown and blocks another request. Reconciliation cannot start while the original lease is live and performs only read-only lookup. Stopping pending reconciliation retains the original uncertainty. Restoring consent alone never authorizes resubmission; changed/expired sources may prevent automatic lookup and require operator handling. No forced-clear or blind-resend endpoint was added.

The model remains `_ENABLED=False`. Shared DeepSeek deployment, real vision/audio credentials and capability, timestamp grounding, prompt-injection and vendor acceptance are separate work. This does not implement scanned-PDF OCR or WhatsApp sending.

## Real PDF parser and two-layer extraction — 2026-10-12

`gigmate.media.pdfparse` replaces the `MEDIA_PDF_PARSER_PENDING` stub with a real local parser (`pypdf==6.20.0`, added to `pyproject.toml` and `requirements.lock`). PDF processing is now two layers:

1. **Local parse (deterministic, before any vendor call).** Pages are extracted verbatim with bounded I/O: at most 200 pages (the `WahaMediaSegment.page` bound), per-page text split into chunks of at most 4000 characters that keep the page number, total text at most 100000 characters (the contract bound). Oversized input refuses with `MEDIA_PDF_PAGE_LIMIT` / `MEDIA_PDF_TEXT_LIMIT` — never silently truncated. Unreadable bytes refuse with `MEDIA_PDF_NOT_PARSEABLE`; a scanned PDF with no text layer refuses with `MEDIA_PDF_NO_TEXT_LAYER` rather than shipping pixels to a text model. All of these happen before the vendor request, so the processor maps them to `ProcessingUnavailable` (nothing was charged). Pages that carry no extractable text inside an otherwise readable PDF are surfaced as an unresolved question ("N of M pages carried no extractable text") instead of claiming full coverage.
2. **Business extraction (vendor).** The extracted pages are shipped to the chat model with the dedicated prompt `prompts/role_b_media_pdf_v1.txt` (version header `1.0.0`, overridable via `GIGMATE_MEDIA_PDF_PROMPT_PATH`). The model only contributes coverage, summary, suggestions and unresolved questions; any `segments` key in its output is ignored because the final `WahaMediaResult` segments are bound locally from the parser. A model can never retype, merge or invent page text, and suggestion `source_indices` are validated against the local segments by the contract.

Validation: 9 new PDF cases in `test_media_processor.py` (real two-page parse with an injected model `segments` key proving local binding, no-text-layer, garbage bytes, 201-page bound, text bound, long-page splitting, blank-page unresolved question, vendor 5xx after a successful parse, bad `source_indices`) — 50 passed in the file, full backend suite re-run green. Ruff check/format clean; contract export and baseline checks unchanged.

This closes the "real PDF parser" item of the 2026-10-11 correction list. Still open from that list: explicit model capability and per-route credential verification, timestamp/timezone grounding, prompt-injection tests, and actual vendor/codec acceptance — the implementation still ships inactive (`_ENABLED=False`) and no real model request was made.

## PR #21 media integration safety correction — 2026-10-11

The media implementation ships **inactive** (`_ENABLED=False`) and has not been validated against a real vendor. The factory contract fixes in `a5aa0a1` are retained. PDF routing is recognized but processing now refuses with `MEDIA_PDF_PARSER_PENDING`; decoding PDF binary as text is not parsing. The default DeepSeek image route refuses with `MEDIA_VISION_VENDOR_UNVERIFIED`; explicit OpenAI/custom fake-client shapes are not proof of model vision capability. Custom vendors require an explicit endpoint. TXT must be UTF-8 and at most 90,000 characters; longer files require future chunking, without silent truncation.

Response validation retains every segment and source index: invalid/oversized results are uncertain, not silently shortened or reindexed. Full ASR text is split into bounded segments when vendor segments do not exactly reproduce it; coverage remains unknown and unsupported timing is not invented. Clients are closed after success and failure, and uncertain logs do not contain raw provider exception/response text. Malformed UTF-8 prompts refuse before submission. Smoke refusal/unknown outcomes exit nonzero.

Before enabling real media, B still needs a real PDF parser, explicit model capability and per-route credential verification, timestamp/timezone grounding, prompt-injection tests, bounded I/O and actual vendor/codec acceptance. A's request identity and source/version bindings remain server-owned; vendor request-id reconciliation is not implemented and `reconcile()` stays read-only/None. Unknown outcomes are not automatically or blindly resubmitted. Merchant evidence review and C business approval remain separate. No real model, account, media or deployment was accessed by this correction.


2026-10-10 media batch 2: A now supplies frozen provider sending time/merchant-selected timezone and reviewed read-only evidence. B must implement real MediaProcessor.process/reconcile separately from text extraction; C must agree attachment provenance and revalidate before business promotion. Missing time stays unresolved, and this does not enable external sending. See [media protocol](role-a-media-ingestion.md).

2026-10-10 media handoff: [A's media agreement](role-a-media-ingestion.md) supplies scoped bytes, immutable request/source/hash identifiers, source/context-bound result storage and review. B owns the real OCR/ASR/parser/GenAI factory and read-only reconciliation. No real adapter has been added by A; retain the existing deterministic live-input guard. Media snapshot evidence must not be cast into an existing canonical message revision or directly materialized as a confirmed work-order change. Review also binds expected_result_job_id so a new result cannot inherit an old review.

2026-10-09 integration update: [WAHA/extraction acceptance](role-a-integration-acceptance.md) records the merged control/worker handoff. Current Alembic head is `0007_merge_waha_extraction`, joining the unchanged B evidence migration and A's controls/provider-sample branch. Windows tests use pytest-owned temporary files; the default provider still refuses live extraction and no real-model/network integration was added.

Updated: 2026-10-10 (merge of the #18 gate-off/prompt-malformed fixes with
the #20 inactive HTTP implementation and always-closed skeleton gate).
[Chinese](../zh/role-b-extraction.md). Builds on
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
This batch ships the `llm` provider with the **inactive call implementation**:
registry selection, configuration, prompt versioning and the
OpenAI-compatible HTTP/parse call shape are wired in place behind the
always-closed `LLMProvider._SKELETON_SEAM` flag, so activating the real
model only has to clear the pre-activation acceptance gates below and flip
that flag (plus the operator gate) — no worker, contract or registry
changes.

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
| `GIGMATE_EXTRACTION_PROVIDER=llm` | Real-model seam with the inactive call implementation; returns `needs_review` with `llm:seam-pending` while `_SKELETON_SEAM=True`. |
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

This batch ships the provider with an **inactive call implementation** on
purpose: `_invoke_model` performs the real OpenAI-compatible
chat-completions POST (30 s timeout, one retry) and `_parse_response`
validates the JSON against `ChangeProposal`, but the always-closed class
flag `LLMProvider._SKELETON_SEAM` keeps every request away from the
network until the pre-activation acceptance gates below are cleared on
their own authorized batch. Until then the module performs no real
network calls regardless of which environment variables are exported, and
only `GIGMATE_LLM_API_KEY` is read; `OPENAI_API_KEY` /
`ANTHROPIC_API_KEY` are deliberately not consulted so model credentials
stay under the operator's explicit control.

Configuration (environment variables, all optional until the seam is filled):

| Variable | Purpose |
| --- | --- |
| `GIGMATE_LLM_PROVIDER` | Vendor name (`deepseek`, `openai`, `custom`). Used in `model_version` and as a sanity check that the operator picked a vendor this build supports. |
| `GIGMATE_LLM_MODEL` | Model identifier (e.g. `deepseek-chat`, `gpt-4o-mini`). Default marker `skeleton:pending` until configured. |
| `GIGMATE_LLM_API_KEY` | Server-side only. The provider reads this on every call; it is never stored on the instance or logged. |
| `GIGMATE_LLM_ENDPOINT` | Optional base URL override (defaults to `https://api.deepseek.com`). |
| `GIGMATE_LLM_PROMPT_PATH` | Optional override of the bundled prompt file. |
| `GIGMATE_LLM_LIVE=1` | The explicit operator gate. Required to actually invoke the model once `_SKELETON_SEAM` is flipped. Until then the skeleton gate refuses first; after the flip, a closed operator gate still refuses every call at the provider layer with `llm:live-gate-off`, even when the vendor and model are configured. Either way a misconfiguration surfaces immediately in the trace rather than silently falling back to a real model call. |
| `GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1` | Opt-in switch that lets `request.origin == "live"` traffic reach the model once the skeleton flag is open. Defaults to off. |

#### Two-gate safety net

Two gates must be open before `_invoke_model` runs:

1. **Class flag `LLMProvider._SKELETON_SEAM`** — `True` in this batch.
   While `True` the provider refuses every call with `llm:seam-pending` no
   matter which environment variables are exported, and no HTTP client is
   even constructed. This is the safety net that prevents a future
   implementation of `_invoke_model` from silently flipping into "real
   call" mode if the next batch only fills in the seam method.
2. **`GIGMATE_LLM_LIVE=1`** — operator switch. Even after the class flag
   is flipped to `False`, the provider still refuses every call with
   `llm:live-gate-off` unless `GIGMATE_LLM_LIVE=1` is exported.

The checks run in order: malformed-prompt check → skeleton flag →
configuration (missing vendor/model or API key → `llm:not-configured`) →
live gate (`llm:live-gate-off`) → wire check (vendor known, key set) →
live-origin guard (`llm:origin-live-refused` unless
`GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`) → `_invoke_model`. With the skeleton
flag `True` every call — operator gate on or off, configured or not — is
refused with `llm:seam-pending` before any client is constructed, so a
misconfigured deployment cannot accidentally emit a real network request.
The post-flip behaviour (`llm:live-gate-off`, `llm:origin-live-refused`
and the fake-client request shape) is pinned by isolated tests that flip
`_SKELETON_SEAM=False` on a test-only subclass; the production flag stays
closed.

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
`PROCESSING_FAILED` retry storm. (The empty-version and non-UTF-8 cases
used to raise `ValidationError` / `UnicodeDecodeError` straight out of
`propose`.) The bundled file encodes the hard rules — never emit
`confirmed`, never grant execution authority, respect the origin trust
boundary — and is the single seam the next batch edits together with the
gate flip.

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
| `GIGMATE_MEDIA_PDF_PROMPT_PATH` | Optional override of the bundled PDF extraction prompt file. |

MIME routing (in `gigmate.media.routing`):

| MIME | Dispatch | Vendor adapter |
| --- | --- | --- |
| `image/png`, `image/jpeg`, `image/webp` | `ocr` | chat-completions with vision input |
| `audio/ogg`, `audio/mpeg`, `audio/wav`, `audio/mp4`, `audio/x-m4a` | `asr` | `/v1/audio/transcriptions` |
| `application/pdf` | `pdf` | local page extraction (`gigmate.media.pdfparse`) then chat-completions business pass |
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
.venv/bin/python -m pytest apps/backend/tests/test_extraction_gates.py apps/backend/tests/test_extraction_batch2.py -q
.venv/bin/python scripts/check_baseline.py
```

The last `pytest` invocation is the pre-activation suite: the five gates plus
batch 2 (cost boundary, startup validation, injection regression). Neither file
opens the seam, so both run offline with no credential.

PostgreSQL tests are the meaningful run; SQLite does not prove row-locking
and only confirms conditional compatibility. Synthesize real WhatsApp
traffic is out of scope for this batch.

## Pre-activation acceptance gates

2026-10-16: the guards below are implemented and regression-tested; see
[the batch note above](#pre-activation-gates-implemented--2026-10-16). They are
recorded as written so reviewers can still see the original requirement and
confirm nothing silently opened the seam.

The current batch ships the **inactive call implementation**: the
HTTP / parse / schema paths are present, but `_SKELETON_SEAM = True`
and the live gate default-off keep every request from reaching the
network. The seam, prompt-versioning chain and live-origin guard are
in place as testable code; the following acceptance gates are
**not** in scope for this PR and must be cleared (each on its own
authorised batch, with their own review) before the seam is flipped
and live traffic is allowed through the real-model provider:

- **Trusted identity and provenance must not be decided by the
  model.** The current `_parse_response` only does structural
  validation; it accepts an LLM-supplied `work_order_id`,
  `base_work_order_version`, `conversation_id` and `sources` without
  re-binding them to the request the server actually issued. Before
  activation, `_parse_response` must re-bind (a) `work_order_id` to a
  member of `request.candidate_work_order_ids` (or `None` when the
  model picks none), (b) `base_work_order_version` to the value the
  worker resolved, (c) each `source.message_id` / `source.message_revision`
  to the request's `message_id` / `message_revision`, and (d)
  `conversation_id` to the request's `conversation_id`. Mismatches
  must surface as `llm:response-schema-failed` with a stable error
  code, never as `matched`. This gate does not require sending any
  more UUIDs to the model; it only needs stricter post-validation.
- **Vendor / endpoint semantics must be explicit.** Today's code
  treats `GIGMATE_LLM_PROVIDER=openai` (or any other vendor name) as
  "use the DeepSeek default endpoint unless the operator overrode
  `GIGMATE_LLM_ENDPOINT`". Once the seam is open, that is a footgun:
  a worker configured for one vendor can quietly call another
  vendor's service. Before activation, the provider must
  - reject an unknown `GIGMATE_LLM_PROVIDER` value, and
  - bundle each known vendor with its own documented default
    endpoint, and
  - require `GIGMATE_LLM_ENDPOINT` when the vendor is `custom`.
  If `openai` is meant to denote "any OpenAI-compatible protocol"
  rather than "OpenAI the vendor", the configuration surface and
  docs need to say so explicitly so reviewers do not infer the
  narrower meaning.
- **Retry must be designed with the worker lock and lease.** The
  current `_call_chat_completion` retries once on every
  `httpx.HTTPError` plus every `KeyError` / `IndexError` /
  `ValueError` from the response shape. With a 30 s timeout and
  one retry, a single extraction can hold the per-account / per-job
  lock for the full backoff window; if the lease expires while the
  request is in flight, the worker may complete and discard the
  result, then re-run, doubling the cost and the chance of a
  duplicate trace row. Before activation the retry policy must
  - bound the **total** wall time and reported cost per call,
  - restrict retries to clearly transient classes (network reset,
    5xx with `Retry-After`, etc.) and **not** retry on parse /
    schema / 4xx errors,
  - issue a **persistent request id** so the operator can correlate
    the trace with the upstream vendor's logs,
  - perform I/O **outside** the row lock, and
  - revalidate the candidate work order / context version after the
    call returns so a stale retry does not promote old data.
  None of this is in scope for this PR; the tests assert the
  current shape (one retry on any failure) so the behaviour cannot
  drift without an explicit test change.
- **Date interpretation needs a real time basis; the output must
  match the contract.** The current prompt tells the model to
  resolve relative dates (今天 / 明天 / 下星期X / "next Thursday")
  against an unspecified "now" and to emit
  `Asia/Hong_Kong`-anchored ISO-8601 strings. The
  `ExtractionRequest` does not carry the original message timestamp
  or a workspace timezone, and the contract's `TimedSchedule` value
  requires `start_at` / `end_at` in UTC `Z` form. Before activation,
  the request must carry a server-attached `message_received_at`
  (or equivalent) and `workspace_timezone`; the prompt must be
  told to resolve relative dates against that timestamp; the
  output must be UTC `Z`; and the provider must reject (with a
  typed note) any response whose `start_at` / `end_at` cannot be
  losslessly interpreted as UTC. The media-processor (OCR / ASR /
  PDF) batch lands the missing timestamp source; this PR is the
  text-only extraction seam, so that work is out of scope here.
- **Stable, sanitised error codes for diagnostics.** Today the
  `refused_reason` field embeds Python exception class names and
  the raw exception message. Useful for development, but private
  endpoint paths / vendor names / key fragments can leak through a
  downstream logger. Before activation, error codes must be
  stable strings (e.g. `llm:http-failed:timeout`) and any free-form
  portion must be redacted of the endpoint, the vendor and the
  API key prefix.

These gates are recorded here so reviewers can confirm that the
current PR does not silently open the seam. Each one is a separate
piece of work with its own batch and review.

## Open follow-ups

- Real-model provider activation: the gates above are implemented as of
  2026-10-16; the cost boundary, startup validation and text injection
  regression suite landed in pre-activation batch 2 on the same day and the
  `new_work_order` recognition contract, the unknown-outcome policy and the
  evaluation classification block landed in batch 3, so the next
  authorized batch must
  (a) supply real authorization + live-origin flow with their own dedicated
  review and measure the latency budget under real load, and (b) flip
  `LLMProvider._SKELETON_SEAM` to `False`
  (the live-origin guard currently lives in this provider but is
  unreachable while the seam flag is `True`; its
  `GIGMATE_LLM_ALLOW_LIVE_ORIGIN` opt-in is pinned by isolated
  test-only-subclass tests). The seam, prompt-versioning fallback chain,
  `llm:prompt-malformed` and `llm:seam-pending` trace notes, the
  `case-008-llm-skeleton-needs-review` evaluation case and the
  `_prompt_load_error` audit attribute are all in place.
- C-side manual creation (C #26) can now consume the `new_work_order`
  suggestion contract delivered in batch 3: the block is persisted with the
  proposal JSON, is refused next to a `matched` assignment, and never creates a
  work order by itself. B's part is done; wiring it into the merchant's
  "create from conversation" flow, and the joint verification of the
  model-returned revision/version re-binding, still need C.
- D frontend review surface for `pending_change_ids` produced by real
  providers; current Replay cards already accept them but a real provider
  round-trip is required before frontend changes ship. A `new_work_order`
  suggestion needs its own card (" recognised new job, still missing X ") for
  the same reason.
- Tighten `unresolved_questions` rendering for merchant review once a real
  provider exists.
- Vendor-side `reconcile()` for media: chat-completions vendors do not expose
  a stable request-id lookup, so the current implementation returns `None`
  and the worker must retain the unknown result for explicit review; it must not blindly resubmit. A future batch can add a
  vendor-specific lookup once the seam flag is open and operators need it.
- ~~B-side prompt-injection regression suite for media attachments (image OCR
  + audio ASR + PDF parsing)~~ **landed in pre-activation batch 4**
  (`contracts/evaluation/media_injection.json`, nine cases with control cases,
  driven by `gigmate.media.injection` and
  `apps/backend/tests/test_media_injection.py`). Still open on this surface:
  real media content. No case has yet seen a real image, audio clip, PDF or
  vendor response, so the false-positive rate of the pattern set against real
  merchant content is unknown, and the PDF end-to-end variant skips on native
  macOS where the local parser refuses with `MEDIA_PDF_LIMIT_UNAVAILABLE`.
  A follow-up batch should re-run it against real attachments once the media
  seam is authorized, and tune the patterns with that evidence.
