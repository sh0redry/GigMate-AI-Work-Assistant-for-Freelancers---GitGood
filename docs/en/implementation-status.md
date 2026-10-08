# Implementation status and validation

## Apple Silicon compatibility audit — 2026-10-07

Teammate reported Apple Silicon, without failing command/log. Confirmed root contributors: Windows-only command examples and the pinned WAHA 2026.9.1 index containing linux/amd64 plus an attestation, not arm64. Registry inspection confirmed same-version native arm-2026.9.1 index b4216daddb7d5c1eb3ab99e608b76a005ec7523e766f923939d229718df4aafb with linux/arm64; Python 3.12.10-slim includes arm64. Added explicit ARM Compose override, daemon-architecture selection in team up/stop (including Rosetta/remote-daemon distinctions), UTF-8 private file reads, and bilingual Mac commands. No engine/version change or session migration. Seventeen team tests passed, including amd64/x86_64/arm64/aarch64 selection and unknown architecture rejection; actual x86/ARM Compose rendering checked image/platform/WEBJS without outputting private values. Native Mac pairing/runtime has not been run here; exact teammate failure still requires their command/error. This fixes known portability gaps, not proof of every Mac setup. No commit/push.

## Local WAHA product setup backend batch — 2026-10-07

Delivered [setup API agreement and unified acceptance](role-a-setup-api-acceptance.md): owner/CSRF/version-checked setup, async connect/recover/inspect/discover, private QR, opaque expiring choices, explicit selection consent, pause/resume and GET-only unknown-result reconciliation. Migration 0005_waha_controls adds independent durable intents/candidates/control_version; generated models/OpenAPI/frontend types refreshed. Worker persists leases before provider calls, never automatically retries uncertain mutations, rejects superseded lease owners, expires pending intents and cleans expired contact metadata. Read-only auth avoids account mutation locks; mutations retain ownership serialization. CLI authorization changes advance setup/context versions. Compose supplies private control config to API and worker. B/C/D/E framework and bilingual entry points updated; no frontend screens, AI/send/history import, production/multi-merchant provisioning or Cloud API.

Verification: isolated PostgreSQL 17.9 full **268 passed** via check_waha_setup --run --suite; SQLite **262 passed, 6 skipped** (`local-data/pytest-setup-final-sqlite`), skips require PostgreSQL locking; existing Starlette/httpx warning. New control API tests cover account/CSRF, idempotency/conflicts, opaque/expired choices, strict consent, unknown results/no retry, expired/pending/stale leases and concurrent queue uniqueness. Migration upgrade/downgrade/re-upgrade preserves existing Replay rows. Real HTTP API and worker with a synthetic provider passed six workflow checkpoints plus scoped cleanup; separate worker restart preserved pending intent. Alembic check passed in the disposable database. Ruff/format, contract drift, baseline/diff and frontend generate/check:api/format/build pass (Vite build needed the permitted process environment after sandbox EPERM).

Environment boundary: Docker was stopped; after startup Windows reserved ports 54261–54360, preventing the existing PostgreSQL 54329 binding. No system reservation edits or deletion of real database/session volumes. Disposable check used unreserved 16432 and only its own resources. Current real-account/provider probe was unavailable, so this batch's new browser QR/discovery workflow has NOT been independently verified on a real WhatsApp account. No existing live database upgrade/deployment or promise of production readiness is claimed. Prior live text evidence remains historical; the new synthetic-provider runtime check is not a real WhatsApp test. E/manual steps remain explicit. No commit/push/main merge.

## Main protection applied — 2026-10-06

User-authorized GitHub main protection applied and API-readback verified: one PR approval, dismiss stale reviews, strict current-branch checks documentation-and-contracts/backend/frontend bound to GitHub Actions app 15368, conversation resolution, administrators enforced, force push/deletion disabled, no named merger/CODEOWNERS/bypass gate. No existing protection/rulesets were present before this change. PR #3 remains unmerged with passing checks and zero independent approvals; GitHub reports blocked. Independent review of the administrative change remains pending. No destructive bypass test performed. Bilingual governance/status records updated locally; no commit/push authorized by this settings-only request.

## PR backend CI import-path correction — 2026-10-06

PR #3 backend run 37432110763 failed during test collection with `ModuleNotFoundError: No module named 'scripts'` in test_waha_team.py. CI used the `pytest` console entry point with only backend src in PYTHONPATH; earlier local runs used `python -m pytest`, which additionally exposed the repository root. Reproduced locally using the console entry point. Backend pytest configuration now explicitly includes `src` and repository root (`../..` relative to apps/backend), making both launchers consistent without bypassing any tests. This is a test-environment correction, not a WAHA/database runtime failure. Related bilingual documentation updated; actual retest and online CI results follow when completed.

Local retest with PYTHONPATH unset: console `pytest` full PostgreSQL suite **253 passed** (`local-data/pytest-ci-console-fixed-pg`); both console/module launchers' team subset **12 passed** each. Ruff/format, generated-contract check, baseline/diff passed. Existing Starlette/httpx warning is not the failure cause. Online CI will rerun on the fix commit; its actual conclusion must be checked independently of local results.

## Team own-account local development batch — 2026-10-06

Final handoff checks also validated the rendered Compose override for API/worker/monitor, confirmed doctor Docker/database/binding/API healthy in the permitted Docker environment, and scanned all 14 changed/new files against local credentials/chat identifiers with no matches. Doctor distinguishes unavailable or access-denied Docker rather than assuming the engine is stopped.

Delivered [team local WAHA framework](role-a-team-local-development.md): `scripts/waha_team.py` init/up/doctor/run/stop/checkpoint/verify; dedicated PostgreSQL Compose on 54349; profile-controlled container DATABASE_URL override with legacy defaults retained. Fresh startup creates only a development application account and empty authorized connection, not Replay orders; repeated startup preserves pause/allowlists. Workspace/resource/port guards refuse implicit adoption, binding-path guard protects private writes, safe evidence checks current real message identity/revisions without text/provider IDs and exits 2 for incomplete acceptance. B/C/D/E now have concrete integration surfaces, dependencies and test expectations. No new domain shape/migration/frontend behavior or Cloud API/send/general-AI implementation.

Self-check: PostgreSQL full **253 passed** (`local-data/pytest-team-final-pg`); SQLite **248 passed, 5 skipped** (`local-data/pytest-team-final-sqlite`), existing Starlette/httpx warning. Twelve team tests cover initialization, identity/unfinished/revoked/missing/range checks, workspace/env/resource isolation, private error output and pause preservation. Final guard subset passed again. An initial test alias-isolation omission overwrote the host private binding; restored it from the retained original after validating config/database ownership, fixed test path injection and added a runtime path guard. Containers/provider session and database business content were unaffected; doctor and seven HTTP checks passed after restoration.

Actual isolated PostgreSQL 17.9 clean migration reached 0004_waha_recovery; one account, zero conversations/work orders/jobs; Alembic check passed. Only resources created for this check were removed after confirming no previous team project/volume existed. New evidence tool verified the existing October 6 07:07 live creation/edit/revocation, identity matching and completed jobs. A fresh empty checkpoint correctly reported no verified sequence. Ruff/format, contract drift, baseline/diff pass. Frontend was unchanged; its preceding successful build remains evidence. New teammate end-to-end init/up/QR on a different real account has NOT been executed: bootstrap orchestration uses isolated test doubles, clean database migration is real, existing-account evidence is real. Independent own-account onboarding must be run before claiming new-member acceptance. No automatic incident acknowledgement, commit/push/main merge.

## WAHA handoff audit and commit preparation — 2026-10-06

Added [current WAHA implementation/team handoff](role-a-waha-handoff.md) with capability limits, operator/API entry points, B/C/D/E responsibilities and remaining WAHA dependencies. Corrected obsolete live-pending claims in both indexes, responsibilities, roadmap and connection flow. Official Cloud API is deferred and excluded from the current plan per user instruction. Root `start.txt` is a preserved, ignored personal memo. Precommit PostgreSQL full suite again **241 passed** (`local-data/pytest-waha-precommit-pg`), existing Starlette/httpx warning; Ruff check/format, generated contracts, baseline/diff, seven HTTP checks and frontend check:api/format:check/build pass. Build needed the permitted process environment after sandbox spawn EPERM. Previous SQLite/fault results remain dated evidence; no new runtime edits in this documentation audit. Scanned 44 changed/new files against local private values: no matches, memo excluded. User authorized committing/pushing the remaining batch to Andy_WAHA; main is not a push target.

## Post-recovery live mutation acceptance — 2026-10-06

Repeated user test at 07:07 UTC verified in scoped read-only PostgreSQL: accepted 34 to 35 was an earlier ACK with no job, then 35 to 38 was one new message's creation/edit/revocation, revisions 1/2/3, matching internal/provider identity and final revoked state. Three jobs completed with attempts=1; seven HTTP smoke checks passed again, pipeline healthy/no backlog/failures. Last rejection 06:48:08 UTC preceded the sequence; no new rejection during it. Eleven review records retained. Documentation baseline/diff checks passed; no runtime edits, commit or push.

Read-only account/connection-scoped PostgreSQL metadata confirms an independent creation plus a second message's creation/edit/revocation (revisions 1/2/3) on October 6. Internal/canonical provider identity matches throughout, latest revision revoked. Accepted 30 to 34, four measured jobs completed, no backlog/failures in status samples. Processing 8–12 ms and completion latency 75–539 ms across four local samples only. Terminal LIVE_EXTRACTION_PENDING/SOURCE_SUPERSEDED codes reflect the current no-model/no-send scope. Fresh mutation verification after the private configuration-volume repair passes; earlier pending notes are historical. Eleven gap/source incidents remain unacknowledged, not evidence of restored missing messages. No runtime code change, commit or push. [Detailed evidence](role-a-recovery-acceptance.md#successful-post-recovery-live-mutation-check--2026-10-06).

## Local restart diagnosis — 2026-10-06

`waha_ingress.py status` returned `LOCAL_INGRESS_OPERATION_FAILED`. Docker Desktop was stopped, ports 54329/18700/18702 were unreachable, and the new terminal had no DATABASE_URL, so the CLI selected the default SQLite database instead of the provisioned PostgreSQL database. Private host configuration and binding JSON were readable. Started Docker Desktop and restored the existing database/WAHA/ingress/worker/monitor services, preserving all volumes and session data. With DATABASE_URL set to the existing local `gigmate_waha_a03` database, status and diagnose succeeded; all four components healthy, pipeline_ready=true, zero pending/processing/failed jobs, seven safe HTTP smoke checks passed. Receipts advanced 28 to 30 during connection recovery; content sync remained October 2, so this is not new message acceptance evidence. Eleven review records remain unacknowledged. No runtime code change, migration, commit or push; full suites were not rerun for service restart/documentation only.

Every new host PowerShell terminal must set `$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:54329/gigmate_waha_a03'` before operator commands. Activating `.venv` does not restore environment variables. Start Docker Desktop and the documented Compose services before checking status; do not reprovision or delete session volumes to fix an unavailable database.

## A-03 operational recovery batch — 2026-10-02

Manual acceptance follow-up: 13:24–13:25 UTC provider connecting was reported; direct check/diagnosis at 13:27 found WORKING and all components healthy without an agent restart/rescan. Accepted 28 contains 22 state notifications and six earlier content/ACK receipts; latest content sync remains 09:18, so fresh manual content acceptance has not passed. One selected/allowed chat is synchronized. Earlier unresolved-source error is an ACK; an earlier creation was rejected by the allowlist. The temporary connecting cause is not established. Six unacknowledged review records are preserved. Detailed safe evidence is in the recovery document; subsequent diagnosis and repair are described below; no commit/push.

Confirmed follow-up: unreadable Windows Docker bind mount (`ENODEV`) blocked reception despite the old healthy API signal. Runtime private configuration now uses Docker named volumes; health validates the binding and ownership, and operator sync/migration commands preserve private configuration and session state. Rebuilt services: four healthy components, pipeline_ready=true, nine review records retained. Seven HTTP checks and eight disposable fault checkpoints pass after this fix. Fresh real text acceptance remains pending.

Authorized follow-up to `83aa75e`: versioned `0004_waha_recovery`, separate component health and worker heartbeat, safe signed-rejection metrics, persisted outage/source review, operator diagnose/issues/review, terminal timing/lease metrics and bounded crash recovery. Generated domain/OpenAPI/frontend types refreshed. [Full scope, E matrix, commands and limitations](role-a-recovery-acceptance.md).

- PostgreSQL 17.9 final full suite: **241 passed**, no skips (`local-data/pytest-recovery-volumes-final-pg`). SQLite final full suite: **236 passed, 5 skipped** (`local-data/pytest-recovery-volumes-final-sqlite`); skipped cases require PostgreSQL locks. One existing Starlette/httpx deprecation warning. Versioned migration preservation/downgrade/re-upgrade covers legacy Inbox and Job rows; both local databases upgraded to head and Alembic check passed. Added response-start evidence that development login commits before sending its cookie; login/logout now use function-scoped transactions.
- Disposable Docker fault runner: **8 checkpoints passed**, real isolated PostgreSQL/API/worker stop/start, concurrent actual HTTP reception, database failure 503, committed retry dedup, backlog processing, process crash heartbeat staleness, explicit synthetic expired-lease fixture and review without import. Only `gigmate-waha-recovery` test resources were cleaned; no external sends. Safe result in ignored local-data/waha-recovery/result.json.
- First live provider interruption exposed a shared network namespace flaw: the monitor lost API/database connectivity along with WAHA. Fixed its network isolation and fixed internal provider target. Repeated live stop/start: provider unavailable while API/worker/monitor stayed healthy, pipeline_ready false; after recovery all healthy, pipeline_ready true without rescanning. Accepted receipts advanced from 10 to 12 through state notifications. Real business gap restoration is not claimed; MONITOR_GAP/PROVIDER_UNAVAILABLE review evidence remains visible for the user.
- Ruff/backend and changed-script format checks, source-generated contract checks and baseline/diff checks pass. Frontend generate:api/check:api/format:check/build pass; Vite required the permitted process environment after sandbox spawn EPERM. The final signature-check failure was traced to the unreadable private binding; earlier unrelated failure causes are not inferred. Final smoke includes the recovery list (**7 HTTP checks**) and passed twice consecutively after final deployment. Current pipeline_ready=true, all four components healthy, zero backlog/failures, nine issues still awaiting human review. No secrets or content in diagnostic output.
- Current live data/IDs/credentials remain private. This is developer verification, not E's independent signoff. Router/Internet outages, logout/QR recovery, complete historical restoration, frontend health UI, production auth/alerts and external execution remain pending. This batch has not been committed or pushed.

## A-03 live text mutation verification — 2026-10-02

User-operated fresh creation/edit/revoke at 09:18 UTC advanced accepted receipts **6 → 7 → 8**. Safe metadata verifies the same internal/canonical provider identity across creation, revision-2 edit and revision-3 revocation, with latest revision revoked. Queues are empty, failed jobs zero, database lock waiters zero, and six HTTP smoke checks pass. Added bilingual evidence; baseline and diff checks pass. This closes the previously pending local text mutation check, without claiming E review, production readiness or network outage recovery. No commit/push. [Detailed evidence](role-a-stage3-acceptance.md#successful-live-createeditrevoke-verification).

## A-03 webhook event-loop correction — 2026-10-02

After the user confirmed all three live actions, diagnosis found the API unhealthy with blocking synchronous reception on its async event loop and PostgreSQL lock waiters. Moved reception to the thread pool, retaining commit-before-success. New same-event-loop health responsiveness regression passes. PostgreSQL full suite **204 passed** (`local-data/pytest-loop-full-pg`); SQLite ingress subset **33 passed, 1 skipped** (`local-data/pytest-ingress-loop-sqlite`); existing Starlette/httpx warning remains. Ruff check/format and export check pass. Rebuilt services are healthy; six HTTP smoke checks pass; lock waiters are zero and monitor freshness resumes. Live accepted count remains five; fresh edit/revoke verification is pending. No commit/push. [Details](role-a-stage3-acceptance.md#follow-up-api-stall-correction).

## A-03 short target correction — 2026-10-02

Live creation persisted; edit/revoke failed because WAHA uses short mutation targets while creation stores serialized IDs. Added scoped, direction-checked short-ID resolution and ambiguity rejection, plus versioned `0003_waha_stanza_identity` with existing mapping backfill. Both local PostgreSQL databases upgraded to head; migration check passes. Rebuilt API/worker/monitor and six HTTP smoke checks pass. Latest full suites: PostgreSQL **203 passed** (`local-data/pytest-stanza-full-pg`), SQLite **201 passed, 2 skipped** (`local-data/pytest-stanza-full-sqlite`), with the existing Starlette/httpx warning. Ruff check/format passes for backend and changed scripts; export check passes. A broader scripts scan found pre-existing unused-import/format issues in unchanged `scripts/check_baseline.py`, which was preserved. Live edit/revoke still needs a fresh user test; three accepted receipts and empty job backlog only prove current ingestion/processing status. No commit/push. [Details](role-a-stage3-acceptance.md#live-target-format-correction).

Baseline: **v0.2 replay skeleton**; latest authorized extension: **A-03 durable WAHA ingress/monitoring**, recorded **2026-10-02**. Earlier evidence below remains historical. This is a completed-work record; future updates must add actual commands/results and revise remaining work.

## Completed

| Area | Implemented result | Source |
| --- | --- | --- |
| Environment | Fixed Python/Node/PostgreSQL, backend and npm locks, loopback-only Compose | infra, .env.example, runtime version files |
| Backend | FastAPI API, strict Pydantic contracts, health, structured errors and request IDs | apps/backend/src/gigmate |
| Persistence | 13 initial tables, explicit migration, idempotent synthetic seed | migrations/versions/0001_replay_foundation.py |
| Identity | Two isolated development accounts, scrypt passwords, hashed sessions, HttpOnly/SameSite cookies, CSRF/origin checks | identity.py, api.py |
| Messaging | Allowlisted text/edit/revoke replay, identity deduplication, revision checks, context advancement before extraction | messaging.py |
| Worker | Durable jobs, PostgreSQL SKIP LOCKED, leases, three-attempt failures, recovery from database outages | worker.py |
| Domain | Proposals only, provenance checks, stale-version rejection, overlap rejection, atomic order/calendar/generated-task/audit updates | workorders.py, planning.py |
| Frontend | Login, order list, source timeline, conflict/stale states, explicit confirmation, calendar and tasks | apps/web |
| Contracts | Generated domain schema, implemented OpenAPI, generated frontend types and drift checks | scripts/export_contracts.py, scripts/check_web_contracts.mjs |
| Verification | API/domain tests, HTTP smoke, lint/format/build and CI definitions | tests, scripts, .github/workflows |

Only generated pending tasks are cancelled by rescheduling; unrelated manual and completed tasks remain. Confirmed state is not written by the fixed extractor. Its scope is two exact synthetic examples, not general language understanding.

## Evidence

- Windows native tooling: Python 3.12.10, Node 24.15.0, npm 11.12.1. Linux containers were built and run with PostgreSQL 17.9.
- docker compose up --build -d --wait: completed; database/API healthy, worker running, migration exited successfully, web available on 18080.
- Alembic upgrade head and check: successful; no model/migration drift.
- PostgreSQL suite: 26 tests passed: 18 behavior tests plus 8 original domain-fixture compatibility checks against canonical runtime models. Includes concurrent claim, bounded retries and database-outage recovery. SQLite is a test fallback and skips the PostgreSQL-specific claim test.
- Ruff check/format, generated-schema drift, original positive/negative fixtures, frontend generated-type drift, TypeScript/production build: passed.
- Browser workflow: conflicting 15:00 proposal disabled confirmation; 16:30 proposal was explicitly confirmed; work-order version advanced from 3 to 4, calendar changed, old generated task cancelled, new task persisted; missing address remained missing.
- HTTP smoke against web proxy: login, replay/worker, confirmation or existing confirmed state, calendar/tasks, duplicate handling and logout passed.
- Restart verification: database/API/worker restarted; the same confirmed schedule and dependent records remained and repeat smoke passed.
- Resume verification: Docker Desktop was initially stopped; after starting it and running Compose up --wait, services recovered and the persisted-state HTTP smoke passed again. Baseline and generated-contract checks also passed again.

The test suite emits one upstream Starlette/httpx deprecation warning; it does not fail checks. No independently timed new-contributor onboarding study was performed.

## Shared baseline freeze — 2026-10-01

- Collaboration task COLLAB-01: the published engineering skeleton is commit [3231810](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/commit/3231810b7e17f7f3dd052eb8084fdd7b87d3c827). The local checkout and origin/main matched before preparing this record.
- [Engineering baseline CI](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/runs/36853663964) passed for that commit.
- [Replay skeleton CI](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/runs/36853664016) passed: backend PostgreSQL tests/migrations and contract/lint checks, plus frontend dependency installation, generated types, formatting and production build.
- Local Ruff, formatting, contract generation/drift, documentation/fixtures and frontend checks were repeated successfully during baseline preparation.
- Additional local PostgreSQL/migration and HTTP reruns were not completed: Docker became unavailable after Compose startup. The waiting native migration check was interrupted. Use the successful cloud backend run above as this freeze's fresh PostgreSQL evidence; earlier local results remain historical evidence.
- Solo self-review: this follow-up changes documentation only; runtime contracts and shared migrations are untouched, related English/Chinese records agree, documentation checks pass, and no private data was added.
- Baseline label: v0.2.0. The annotation identifies the tested implementation commit; later documentation-only freeze records do not change its runtime scope. Tags are immutable team references; fixes receive new commits and subsequent version labels.
- Next collaboration gates: independently verify a teammate's fresh checkout, configure host branch protection/required checks, agree rotating module contacts and prepare scoped starter issues. These are not completed by passing CI or creating a tag.

This freeze covers synthetic replay only. It is not a production release, live connector validation or proof of general AI extraction quality.

## Role A documentation and batch policy — 2026-10-02

- Added bilingual Role A responsibility and technical evolution documents: current boundaries, event mappings, security, durable jobs, monitoring, handoffs, four development batches and eight planned failure-test groups.
- Persisted the user's current/future policy in AGENTS.md and bilingual contribution rules: complete as many related tasks as practical within the authorized milestone, self-check/fix during development, then unified batch acceptance. Independent review, scope limits and honest blocked verification remain required.
- Added navigation in both documentation indexes. No runtime code, schemas, generated files, migrations or root README changed; no live integration was implemented, and no commit/push was performed.
- Verification: `.venv/Scripts/python.exe scripts/check_baseline.py` passed: 30 Markdown files, 91 local links, 3 schemas, 11 valid fixtures, 6 rejected fixtures and 12 synthetic acceptance scenarios; jsonschema 4.26.0. `git diff --check` passed. These checks cover documentation/contracts, not application behavior or live capability. Ruff, pytest, migrations and frontend checks were not rerun for this documentation-only batch.
- Self-review checked local navigation, bilingual policy/phase alignment, current-versus-planned claims and absence of private data. Other role assignments and live acceptance remain pending.

## Onboarding and equal-collaboration preparation — 2026-10-01

COLLAB-02 materials are prepared: internal step-by-step onboarding/report, [matching public policy and acceptance](team-governance.md), ADR 0004 and an Onboarding verification issue template. Contribution/PR rules now use equal peer review and rotating coordination contacts; the baseline checker requires the new materials.

ONB-01 through ONB-08 cover clone/start/login, conflict rejection, proposal-only behavior, explicit confirmation, deduplication, restart persistence, account isolation and a real first peer-reviewed PR. Setup instructions reflect the actual fixed Compose project/volume behavior, scripts/docs absent from the API image and idempotent seed passwords.

This change affects documents, templates and the documentation check's required-file list only. Documentation/link/positive-negative fixture checks passed; solo self-review checked English/internal consistency, configuration facts and explicit pending status. No runtime/migration changes or new full application retest are claimed. No independent teammate report or peer-approved starter PR exists yet.

COLLAB-03 protection settings are specified but not applied. Equal repository Admin access requires an agreed organization because the current owner is a personal account. Actual member usernames, target organization and permission scope are pending; no transfer, invitations or authorization changes were made. Organization Owner is a separate decision. All members follow the same review/check targets; no creator-only approval or bypass is intended.

Materials are published on docs/equal-team-onboarding (initial commit 6f84983), with unassigned [teammate verification issue #1](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/issues/1) and [documentation draft PR #2](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/2), not merged into main. This materials PR is not the teammate's first acceptance PR. An authenticated GitHub API read confirmed main protected=false and current repository admin access; no permission or protection settings were changed.

## Local documentation conflict resolution — 2026-10-02

- Resolved overlapping insertions between local main c71cc6a and incoming main 50c989f: kept both Role A and equal-collaboration navigation, and both completion records. Automatically merged contribution rules retain unified batch acceptance and equal peer review.
- Verification: `.venv/Scripts/python.exe scripts/check_baseline.py` passed: 36 Markdown files, 122 local links, 3 schemas, 11 valid fixtures, 6 rejected fixtures and 12 synthetic acceptance scenarios. Working-tree and staged `git diff --check` passed; a repository content scan found no remaining conflict markers.
- Documentation only; no application/live tests rerun. Resolution does not itself complete the merge commit or push, and no commit/push was performed in this task.

## WhatsApp connection documentation — 2026-10-02

- Added bilingual product/technical flow for GigMate login, owned WAHA sessions, QR pairing, allowlists, authenticated live events and bounded available history. Linked both indexes and Role A responsibility/roadmap documents; cited official provider documentation.
- Clarified that pairing is separate from per-conversation processing consent, historical snapshots require live-event reconciliation, and QR/history/live ingress remain pending. No runtime or contract changes; no commit/push.
- Verification: `.venv/Scripts/python.exe scripts/check_baseline.py` passed (38 Markdown files, 134 local links, 3 schemas, 11 valid/6 rejected fixtures, 12 synthetic scenarios); `git diff --check` passed. Self-review checked bilingual alignment and implementation boundaries. No application, frontend or live tests rerun; external links were consulted, not validated by baseline.

## Outstanding capabilities

Complete durable live text/edit/revoke/ACK and outage acceptance; provider gaps/history recovery; general model extraction and evaluation; multi-order classification/live-status UI; other requirement fields and rejection/edit commands; action approval/outbox/sending/reconciliation; full calendar buffers/work hours; production authentication/secrets management; full account/backup deletion; media and external calendars. Pinning, local pairing and WAHA content-retention maintenance are implemented.

The original 12 acceptance scenarios remain targets. Some internal cases now have service tests; external unknown-send/API-echo/send-race cases do not. Real use is limited to the explicitly authorized local test account/conversations, not production or full P0 completion.

## A-03 durable ingress/monitoring — 2026-10-02

The user authorized shared changes after commits `908855f` (offline adapter) and `016a679` (local capability tools). Added private-bound signed transactional reception, three mapping/state tables and Inbox connection FK via versioned `0002_waha_ingress`, local accepted revision ordering, persistent dedup/ACK/state, scoped status/queue metrics, operator provision/pause/reconcile/purge, 30-second monitoring, hourly 30-day content cleanup, and worker lease/authorization checks. Real content never runs through fictional extraction. No model, external send, approval/outbox or history import was added. Generated domain/OpenAPI/frontend types were refreshed from source. [Full scope, commands and limits](role-a-stage3-acceptance.md).

- PostgreSQL 17.9: migration upgrade/check passed on the Replay development database and dedicated `gigmate_waha_a03`; `0001` was preserved. Disposable SQLite upgrade/downgrade/re-upgrade test preserves existing Replay Inbox rows.
- `.venv/Scripts/python.exe -m pytest apps/backend/tests -q --basetemp=local-data/pytest-ingress-delivery-pg` with documented TEST_DATABASE_URL: **200 passed**, no skips, one existing Starlette/httpx warning. Includes concurrent reception/claim, commit-failure/rollback/lost-response, source ordering/direction, authorization, leases, poll races, retention and provisioning checks.
- SQLite full suite: **198 passed, 2 skipped** (PostgreSQL reception and worker concurrency); it is compatibility evidence, not locking proof.
- Ruff check/format, export_contracts.py --check, baseline, frontend generate:api/check:api/format:check/build passed. Native Vite first encountered sandbox spawn EPERM; the authorized build outside that process restriction succeeded.
- Independent local ingress/API, worker and monitor built and ran. Provider callback configuration changed, session recovered WORKING without rescan, and two real HMAC-authenticated status callbacks committed without jobs. `scripts/smoke_waha_ingress.py`: **six HTTP checks passed**, no real message content read. API/worker/monitor restart retained connection/mapping/receipt state and repeated smoke passed; monitor refreshed freshness.
- Private ingress configuration, secrets, QR and session profiles remain ignored/untracked. Current callbacks use durable ingress rather than the volatile probe. Actual durable fresh text/edit/revoke/ACK and broader network recovery still require the user's consenting test chat and E's independent unified review. No commit/push this batch.

## Role B extraction subsystem — 2026-10-08

Branch `william/role-b-extraction-prompts-eval` (local, not pushed). Delivers the deterministic extraction provider plus an evaluation harness, durable proposal evidence and the WAHA-side hook replacing the prior `LIVE_EXTRACTION_PENDING` placeholder. Scope, contracts and evaluation format are documented in [docs/en/role-b-extraction.md](role-b-extraction.md) and the Chinese counterpart.

- New Pydantic `ChangeProposal`, `ProposalChange`, `ProposalCandidate`, `AssignmentResult`, `EvaluationCase` and `EvaluationRun`; regenerated `contracts/domain/models.schema.json` with `python scripts/export_contracts.py --check` passing. OpenAPI and frontend types unchanged.
- Migration `0005_extraction_evidence` adds `proposals`, `model_call_traces`, `evaluation_runs` and `evaluation_cases`. `0001..0004` untouched. `alembic upgrade head && alembic check` passes.
- `gigmate.extraction` module ships `DeterministicProvider` (default) and `DisabledProvider`; selection via `GIGMATE_EXTRACTION_PROVIDER={deterministic,disabled}`; unknown names raise at startup. The Replay branch still calls `gigmate.understanding.extract` so `test_workflow` monkey-patching continues to work.
- Worker WAHA branch now persists `proposals` + `model_call_traces` rows in the same transaction as the Job outcome. Unknown live content ends with `EXTRACTION_NEEDS_REVIEW` instead of `LIVE_EXTRACTION_PENDING`; nothing is written to `requirement_changes`. `test_waha_ingress::test_real_content_worker_never_calls_fictional_extractor` updated to assert the new error code.
- `scripts/run_evaluation.py` plus `contracts/evaluation/manifest.json` (7 synthetic cases: known reschedule, known available, unknown live text, no-order linkage, multi-order ambiguity, prompt-injection, live-origin with fixture-equal text). Local run with disposable SQLite: 7/7 cases pass; non-empty manifest requirement enforced.

Verification on a disposable SQLite database after the Branch A-03 migrations were already upgraded to head:

- `python -m ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py`: 0 errors.
- `python -m ruff format --check apps/backend scripts/export_contracts.py scripts/smoke_replay.py scripts/run_evaluation.py`: 50 files already formatted.
- `python scripts/export_contracts.py --check`: synchronized.
- `python -m alembic -c apps/backend/alembic.ini check`: no new upgrade operations detected.
- `python -m pytest apps/backend/tests -q --basetemp=/tmp/extraction_full`: 262 passed, 5 skipped (PostgreSQL row-locking tests require a real PG instance; SQLite does not prove those).
- `python scripts/check_baseline.py`: 52 Markdown files, 253 local links, 3 schemas, 11 valid / 6 rejected fixtures, 12 synthetic scenarios.

Not proved: production-grade model integration, prompt-injection regression for real providers, latency budget under load, real WhatsApp traffic through the new provider, E's independent signoff. The deterministic provider refuses unknown live content by design; lifting that guard is the next authorized batch.

## Role B review fixes — 2026-10-08

Applied on PR head `7de6042` (branch `WillW27-patch` on GitHub) in response to the reviewer's four findings; all fixes verified with synthetic inputs only.

- P1 persistence: `persist_changes_for` no longer reads `.value` off Literal strings and no longer round-trips Pydantic values through `json.dumps`; it constructs `RequirementChange` directly and serializes with `model_dump(mode="json")`. Regression test `test_matched_waha_proposal_persists_evidence_then_merchant_confirms` covers matched input → proposal/trace/change rows → merchant confirmation.
- P1 retention: `waha_ingress.purge_expired` now deletes `model_call_traces`, then `proposals`, then inbox receipts, so the `proposals.event_id` foreign key no longer rolls back the 30-day purge. The result gains `deleted_proposals` / `deleted_traces` counts. Evidence shares the receipt retention window; confirmed business changes on work orders are retained. Regression test `test_waha_ingress::test_retention_removes_extraction_evidence_with_receipts` runs the full receive → worker → purge chain (foreign keys enforced under PostgreSQL; SQLite runs confirm the deletion logic).
- P1 source trust: `ExtractionRequest.origin` (`synthetic` | `live`, default `live`) is the server-side trust boundary. The worker's WAHA branch always marks `origin="live"`; the deterministic provider refuses live-origin input even when the text equals a fixture, so fixed-date templates can only apply to trusted Replay/evaluation input. New manifest case `case-007-live-origin-with-fixture-text` plus unit/worker regression tests pin this.
- P2 provider switch: the legacy Replay path (`gigmate.understanding.extract`) now resolves its provider through `gigmate.extraction.provider()` instead of hardcoding `deterministic`, so `GIGMATE_EXTRACTION_PROVIDER=disabled` suppresses proposals on both paths (Replay → `STUB_UNSUPPORTED_INPUT`, live → `EXTRACTION_NEEDS_REVIEW`); unknown names raise. Documented in both languages.
- Minor: `scripts/run_evaluation.py` imports carry `# noqa: E402` and the script joined `ruff check`/`ruff format --check` scope in `.github/workflows/skeleton.yml`.

Verification: `ruff check`/`ruff format --check` (ruff 0.15.6, CI scope incl. `run_evaluation.py`) clean; `pytest apps/backend/tests -q`: 268 passed, 5 skipped (PostgreSQL suite requires a real PG instance; the two new FK-sensitive tests execute the same code path on SQLite); `export_contracts.py --check` synchronized; `check_baseline.py` PASS; evaluation run 7/7 pass. No migration changes in this round (`0005` already shipped in the PR).
