# Kyrie's file map: start small, look up the rest later

Current delivery files (2026-10-16): [OrderCreation](../../apps/web/src/OrderCreation.tsx) collects customer-backed order details; [OrderLifecycle](../../apps/web/src/OrderLifecycle.tsx) explains state changes; [CalendarWorkspace](../../apps/web/src/CalendarWorkspace.tsx) draws month/tasks and downloads; [ReviewWorkspace](../../apps/web/src/ReviewWorkspace.tsx) surfaces manual review; [order-command-api](../../apps/web/src/order-command-api.ts) keeps original numbered requests; [features](../../apps/web/src/features.ts) explains blocked dependencies. [workspace_api.py](../../apps/backend/src/gigmate/workspace_api.py) supplies owned read helpers; [calendar_export.py](../../apps/backend/src/gigmate/calendar_export.py) writes the calendar file. main includes #25; the current candidate is `codex/d-final-workspace`. Older exhaustive tables below retain dated path/history observations.

D-03 files: [ApprovalsWorkspace.tsx](../../apps/web/src/ApprovalsWorkspace.tsx) draws review/history; [approvals-api.ts](../../apps/web/src/approvals-api.ts) reads canonical APIs and preserves the original uncertain request; [approval-view.ts](../../apps/web/src/approval-view.ts) explains states and approval blockers. These files are in the pending D-03 branch, not main.

Updated 2026-10-12. [中文地图](../zh/kyrie-file-atlas.md) · [Beginner guide](kyrie-learning-guide.md).

Start with App.tsx (login/navigation), chat-choices.ts (page calculation), ChatChoices.tsx (checkbox rows), WorkOrderWorkspace.tsx (business review), and workspace-api.ts (requests). Read the long connection screen/backend later.

Ordinary checkout is main `bbb0074`; new D is a separate `codex/d02-workspace` directory, locatable with `git worktree list`. Original exhaustive reference/history is preserved; version labels describe path existence against old D `c702f0c`, not identical current content. New-D source links use pushed `4665692` for location, not later unpublished cleanup. App/new entry tests are listed by repository path; inspect them on the complete D branch or its PR. The complete D-02 branch is now prepared for PR review; main integration remains pending.

Roles coordinate work, not character authorship: A messaging, B proposals, C business rules, D UI, E independent checks. Tests do not establish phone pairing. Do not edit generated outputs manually. Dependencies/cache/private keys/sessions are excluded.

## New D entry points

| File | Plain purpose |
| --- | --- |
| `apps/web/src/App.tsx` | Sign-in/out and business/connection navigation; local D worktree |
| `apps/web/app.test.mjs` | Checks no demo bypass, blank credentials, truthful emptiness, owned routes and logout |
| [apps/web/src/WorkOrderWorkspace.tsx](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/4665692/apps/web/src/WorkOrderWorkspace.tsx) | Business page: exact sources, review, schedule confirmation, calendar/tasks |
| [apps/web/src/work-order-view.ts](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/4665692/apps/web/src/work-order-view.ts) | Formats status/time and resolves source/conflicting order |
| [apps/web/work-order-view.test.mjs](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/4665692/apps/web/work-order-view.test.mjs) | Checks multi-chat source context, midnight dates, filtering, versions and conflict names |
| [apps/web/work-order-workspace.test.mjs](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/4665692/apps/web/work-order-workspace.test.mjs) | Exercises real business component: review/consent/stale data/conflicts |

The remaining reference is for lookup, not first-day memorization. Vocabulary is in guide section 9. Database migrations upgrade saved data structures, not ordinary page edits.

## Root configuration / 根配置

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [.dockerignore](../../.dockerignore) | Excludes private/dependency/unneeded files from Docker builds | A | Both |
| [.env.example](../../.env.example) | Environment placeholder example; never commit real credentials | A/B/C/D | Both |
| [.gitattributes](../../.gitattributes) | Git file attributes and line-ending rules | A/B/C/D | Both |
| [.gitignore](../../.gitignore) | Ignores local secrets/sessions/data/generated artifacts | A/B/C/D | Both |
| [.node-version](../../.node-version) | Required Node.js runtime version | D | Both |
| [.python-version](../../.python-version) | Required Python runtime version | A/B/C | Both |
| [AGENTS.md](../../AGENTS.md) | Repository engineering/authorization/contract/test/bilingual rules | A/B/C/D/E | Both |
| [README.md](../../README.md) | Root English scope/start entry; reconcile with dated evidence | A/B/C/D/E | Both |
| [跟單_WhatsApp业务协作助手_新版方案v2.docx](../../%E8%B7%9F%E5%96%AE_WhatsApp%E4%B8%9A%E5%8A%A1%E5%8D%8F%E4%BD%9C%E5%8A%A9%E6%89%8B_%E6%96%B0%E7%89%88%E6%96%B9%E6%A1%88v2.docx) | Original v2 product-plan input; not re-reviewed page-by-page or delivery evidence | 产品/全队 / Product/team | Both |

## GitHub collaboration and CI / GitHub 协作与持续集成

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [.github/ISSUE_TEMPLATE/bug.md](../../.github/ISSUE_TEMPLATE/bug.md) | Issue template: bug reproduction/expected versus actual | A/B/C/D/E | Both |
| [.github/ISSUE_TEMPLATE/onboarding.md](../../.github/ISSUE_TEMPLATE/onboarding.md) | Issue template: independent onboarding evidence | A/B/C/D/E | Both |
| [.github/ISSUE_TEMPLATE/task.md](../../.github/ISSUE_TEMPLATE/task.md) | Issue template: task and acceptance | A/B/C/D/E | Both |
| [.github/pull_request_template.md](../../.github/pull_request_template.md) | PR description/scope/evidence/limits template | A/B/C/D/E | Both |
| [.github/workflows/baseline.yml](../../.github/workflows/baseline.yml) | GitHub Actions documentation/schema/baseline workflow | A/E | Both |
| [.github/workflows/skeleton.yml](../../.github/workflows/skeleton.yml) | GitHub Actions backend/frontend tests/build; main also lints evaluation/model smoke scripts | A/B/D/E | Both |

## Backend configuration / 后端配置

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [apps/backend/alembic.ini](../../apps/backend/alembic.ini) | Alembic migration configuration entry | A/C | Both |
| [apps/backend/pyproject.toml](../../apps/backend/pyproject.toml) | Python package/dependency ranges and Ruff/pytest configuration | A/B/C | Both |
| [apps/backend/requirements.lock](../../apps/backend/requirements.lock) | Pinned backend dependencies for the project virtual environment | A/B/C | Both |

## Migrations / 数据库迁移

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [apps/backend/migrations/env.py](../../apps/backend/migrations/env.py) | Migration connection/metadata loading; not an env-secret file | A/C | Both |
| [apps/backend/migrations/versions/0001_replay_foundation.py](../../apps/backend/migrations/versions/0001_replay_foundation.py) | Versioned migration: Replay identity/message/order/planning/job foundation; preserve shared history | A/C | Both |
| [apps/backend/migrations/versions/0002_waha_ingress.py](../../apps/backend/migrations/versions/0002_waha_ingress.py) | Versioned migration: Durable WAHA ingress/provider identity/review state; preserve shared history | A/C | Both |
| [apps/backend/migrations/versions/0003_waha_stanza_identity.py](../../apps/backend/migrations/versions/0003_waha_stanza_identity.py) | Versioned migration: Canonical provider stanza identity and old-data handling; preserve shared history | A/C | Both |
| [apps/backend/migrations/versions/0004_waha_recovery.py](../../apps/backend/migrations/versions/0004_waha_recovery.py) | Versioned migration: Health/incident/recovery-review state; preserve shared history | A/C | Both |
| [apps/backend/migrations/versions/0005_extraction_evidence.py](../../apps/backend/migrations/versions/0005_extraction_evidence.py) | Versioned migration: B provider extraction request/result/evidence tables; preserve shared history | B | Added in main |
| [apps/backend/migrations/versions/0005_waha_controls.py](../../apps/backend/migrations/versions/0005_waha_controls.py) | Versioned migration: A connection control/discovery/idempotency; parallel to B branch; preserve shared history | A/C | Added in main |
| [apps/backend/migrations/versions/0006_waha_provider_sample.py](../../apps/backend/migrations/versions/0006_waha_provider_sample.py) | Versioned migration: Provider samples/bounded observation fields; preserve shared history | A/C | Added in main |
| [apps/backend/migrations/versions/0007_merge_waha_extraction.py](../../apps/backend/migrations/versions/0007_merge_waha_extraction.py) | Versioned migration: Merges A/B migration heads, rather than deleting a duplicate number; preserve shared history | A/C | Added in main |
| [apps/backend/migrations/versions/0008_waha_message_sync.py](../../apps/backend/migrations/versions/0008_waha_message_sync.py) | Versioned migration: Bounded history sync/media metadata incremental schema; preserve shared history | A/C | Added in main |

## Backend modules / 后端模块

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [apps/backend/src/gigmate/__init__.py](../../apps/backend/src/gigmate/__init__.py) | Python package marker/exports; little business logic | A/B | Both |
| [apps/backend/src/gigmate/api.py](../../apps/backend/src/gigmate/api.py) | Backend entry: receive page requests and invoke business methods | A/C | Both |
| [apps/backend/src/gigmate/config.py](../../apps/backend/src/gigmate/config.py) | Environment/startup configuration; not a store for real keys | A/B | Both |
| [apps/backend/src/gigmate/contracts.py](../../apps/backend/src/gigmate/contracts.py) | Authoritative business data shapes/validation; frontend descriptions are generated from it | A/B/C/D | Both |
| [apps/backend/src/gigmate/db.py](../../apps/backend/src/gigmate/db.py) | Defines saved database records, not page memory | A/B/C | Both |
| [apps/backend/src/gigmate/errors.py](../../apps/backend/src/gigmate/errors.py) | Shared business errors/codes mapped to API responses | A/C/D | Both |
| [apps/backend/src/gigmate/extraction/__init__.py](../../apps/backend/src/gigmate/extraction/__init__.py) | Python package marker/exports; little business logic | A/B | Added in main |
| [apps/backend/src/gigmate/extraction/deterministic.py](../../apps/backend/src/gigmate/extraction/deterministic.py) | Repeatable fixed-input extraction for replay/evaluation | B | Added in main |
| [apps/backend/src/gigmate/extraction/disabled.py](../../apps/backend/src/gigmate/extraction/disabled.py) | Explicit disabled provider; missing configuration cannot imply success | B | Added in main |
| [apps/backend/src/gigmate/extraction/evaluator.py](../../apps/backend/src/gigmate/extraction/evaluator.py) | Evaluates provider output/missing values/sources against scenarios | B | Added in main |
| [apps/backend/src/gigmate/extraction/legacy.py](../../apps/backend/src/gigmate/extraction/legacy.py) | Adapts legacy understanding into provider interface | B | Added in main |
| [apps/backend/src/gigmate/extraction/llm.py](../../apps/backend/src/gigmate/extraction/llm.py) | LLM/DeepSeek HTTP/parser seam; skeleton gate stays closed | B | Added in main |
| [apps/backend/src/gigmate/extraction/persistence.py](../../apps/backend/src/gigmate/extraction/persistence.py) | Persists extraction requests/results/evidence/state | B | Added in main |
| [apps/backend/src/gigmate/extraction/prompts/role_b_extraction_v1.txt](../../apps/backend/src/gigmate/extraction/prompts/role_b_extraction_v1.txt) | Versioned extraction prompt; never authority for automatic confirmation | B | Added in main |
| [apps/backend/src/gigmate/extraction/registry.py](../../apps/backend/src/gigmate/extraction/registry.py) | Provider registration/config selection; rejects unknown configuration | B | Added in main |
| [apps/backend/src/gigmate/extraction/types.py](../../apps/backend/src/gigmate/extraction/types.py) | Provider input/output/evidence interface types | B | Added in main |
| [apps/backend/src/gigmate/identity.py](../../apps/backend/src/gigmate/identity.py) | Checks identity and owned data access | A | Both |
| [apps/backend/src/gigmate/messaging.py](../../apps/backend/src/gigmate/messaging.py) | Canonical message acceptance, identity/deduplication and revisions/context | A | Both |
| [apps/backend/src/gigmate/planning.py](../../apps/backend/src/gigmate/planning.py) | Calculates calendar conflicts and preparation tasks | C | Both |
| [apps/backend/src/gigmate/seed.py](../../apps/backend/src/gigmate/seed.py) | Synthetic demo account/order/calendar/task initialization | A/C | Both |
| [apps/backend/src/gigmate/understanding.py](../../apps/backend/src/gigmate/understanding.py) | Legacy fixed-fixture understanding; not general model extraction | B | Both |
| [apps/backend/src/gigmate/waha_adapter.py](../../apps/backend/src/gigmate/waha_adapter.py) | Normalizes WAHA provider events into message events | A | Both |
| [apps/backend/src/gigmate/waha_client.py](../../apps/backend/src/gigmate/waha_client.py) | Server-side WAHA HTTP client; credentials stay server-side | A | Both |
| [apps/backend/src/gigmate/waha_controls.py](../../apps/backend/src/gigmate/waha_controls.py) | Formal setup/QR/discovery/allowlist/pause/revoke/reconcile controls | A/D | Added in main |
| [apps/backend/src/gigmate/waha_ingress.py](../../apps/backend/src/gigmate/waha_ingress.py) | Signature/binding/allowlist validation and durable ingress HTTP service | A | Both |
| [apps/backend/src/gigmate/waha_probe.py](../../apps/backend/src/gigmate/waha_probe.py) | Provider/pipeline health observation and incident facts | A | Both |
| [apps/backend/src/gigmate/waha_recovery.py](../../apps/backend/src/gigmate/waha_recovery.py) | Recovery, manual incident review and guarded transitions | A | Both |
| [apps/backend/src/gigmate/waha_replay.py](../../apps/backend/src/gigmate/waha_replay.py) | Offline replay of synthetic WAHA create/edit/revoke events | A/E | Both |
| [apps/backend/src/gigmate/waha_sync.py](../../apps/backend/src/gigmate/waha_sync.py) | Bounded history observations, live-event merge, revisions/media metadata | A/D | Added in main |
| [apps/backend/src/gigmate/worker.py](../../apps/backend/src/gigmate/worker.py) | Processes persisted queued work separately | A/B | Both |
| [apps/backend/src/gigmate/workorders.py](../../apps/backend/src/gigmate/workorders.py) | Checks order sources/versions/conflicts and performs internal confirmation | C | Both |

## Backend tests / 后端测试

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [apps/backend/tests/conftest.py](../../apps/backend/tests/conftest.py) | Shared pytest database/account/isolation fixtures | A/B/C/E | Both |
| [apps/backend/tests/fixtures/waha_a01.json](../../apps/backend/tests/fixtures/waha_a01.json) | Synthetic raw provider events for adapter/replay | A/E | Both |
| [apps/backend/tests/test_contracts.py](../../apps/backend/tests/test_contracts.py) | Domain-shape/state-constraint/contract regression | A/B/C/E | Both |
| [apps/backend/tests/test_extraction.py](../../apps/backend/tests/test_extraction.py) | Controlled provider/evidence/evaluation/LLM seam tests | B/E | Added in main |
| [apps/backend/tests/test_waha_adapter.py](../../apps/backend/tests/test_waha_adapter.py) | Provider event identity/normalization and invalid input tests | A/E | Both |
| [apps/backend/tests/test_waha_controls.py](../../apps/backend/tests/test_waha_controls.py) | Setup/consent/idempotency/ownership/unknown-result control tests | A/D/E | Added in main |
| [apps/backend/tests/test_waha_ingress.py](../../apps/backend/tests/test_waha_ingress.py) | Signature/allowlist/duplicate/revision/durable ingress tests | A/E | Both |
| [apps/backend/tests/test_waha_local.py](../../apps/backend/tests/test_waha_local.py) | Local helper boundaries/configuration/safe-output tests | A/E | Both |
| [apps/backend/tests/test_waha_migration.py](../../apps/backend/tests/test_waha_migration.py) | WAHA migration/data compatibility/table-constraint tests | A/E | Both |
| [apps/backend/tests/test_waha_recovery.py](../../apps/backend/tests/test_waha_recovery.py) | Health/recovery/manual-review/failure tests | A/E | Both |
| [apps/backend/tests/test_waha_sync.py](../../apps/backend/tests/test_waha_sync.py) | Bounded sync/ownership/dedup/groups/edit/revoke history conflict tests | A/E | Added in main |
| [apps/backend/tests/test_waha_team.py](../../apps/backend/tests/test_waha_team.py) | Team workspace/resource/private-binding guards and helper tests | A/E | Both |
| [apps/backend/tests/test_workflow.py](../../apps/backend/tests/test_workflow.py) | Synthetic replay/ownership/version/conflict/confirm transaction tests | A/B/C/E | Both |

## Frontend / 前端

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [apps/web/chat-choices.test.mjs](../../apps/web/chat-choices.test.mjs) | Individual/group/unknown, filter and paging edge regression | D/E | Added in main |
| [apps/web/connection-state.test.mjs](../../apps/web/connection-state.test.mjs) | Fresh/stale/incident guidance priority regression | D/E | Both |
| [apps/web/connection-workspace.test.mjs](../../apps/web/connection-workspace.test.mjs) | Mounted jsdom React tests: cross-page PUT/readback/revoke | D/E | Added in main |
| [apps/web/index.html](../../apps/web/index.html) | HTML shell and React root; not the business logic | D | Both |
| [apps/web/local-operations.py](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/c702f0c/apps/web/local-operations.py) | Old bridge Python operations helper; retired in main | D | Retired |
| [apps/web/local-pairing.mjs](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/c702f0c/apps/web/local-pairing.mjs) | Old Vite pairing development bridge; retired in main | D | Retired |
| [apps/web/local-pairing.test.mjs](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/c702f0c/apps/web/local-pairing.test.mjs) | Legacy bridge routes/QR/failure regressions; not phone pairing | D/E | Retired |
| [apps/web/package-lock.json](../../apps/web/package-lock.json) | Exact installed dependency versions, maintained by npm | D | Both |
| [apps/web/package.json](../../apps/web/package.json) | Frontend tool list and commands available through npm run | D | Both |
| [apps/web/business-store.test.mjs](../../apps/web/business-store.test.mjs) | Replay subscriptions/races/login/proposal/confirm state regression | D/E | Both |
| [apps/web/src/ChatChoices.tsx](../../apps/web/src/ChatChoices.tsx) | Draws loaded checkbox rows without losing hidden selections | D | Added in main |
| [apps/web/src/ConnectionWorkspace.tsx](../../apps/web/src/ConnectionWorkspace.tsx) | Connection screen: state, real QR and saved/withdrawn chat consent | D | Both |
| [apps/web/src/ReplayWorkspace.tsx](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/bbb0074/apps/web/src/ReplayWorkspace.tsx) | Old workspace; D-02 replaces it with WorkOrderWorkspace; linked main history | D | main history |
| [apps/web/src/WahaMessages.tsx](../../apps/web/src/WahaMessages.tsx) | Shows allowed timeline, sync progress and media metadata | A/D | Added in main |
| [apps/web/src/chat-choices.ts](../../apps/web/src/chat-choices.ts) | Calculates search/type/pages without network calls | D | Added in main |
| [apps/web/src/connection-api.ts](../../apps/web/src/connection-api.ts) | Agrees connection data/methods; simulator removed | D | Both |
| [apps/web/src/connection-state.ts](../../apps/web/src/connection-state.ts) | Chooses guidance; old observations cannot establish current connection | D | Both |
| [apps/web/src/connection.css](../../apps/web/src/connection.css) | Connection/chat layout; obsolete demo styles removed | D | Both |
| [apps/web/src/generated/api.d.ts](../../apps/web/src/generated/api.d.ts) | Tool-generated API data descriptions; do not edit manually | A/B/C/D | Both |
| [apps/web/src/main.tsx](../../apps/web/src/main.tsx) | Starts the page; App.tsx now handles login/navigation | D | Both |
| [apps/web/src/business-store.ts](../../apps/web/src/business-store.ts) | Tracks reads/writes and prevents late responses replacing newer selections; renamed BusinessStore; no fictional input action | D | Both |
| [apps/web/src/style.css](../../apps/web/src/style.css) | Global colors/layout/wrapping and narrow-screen adjustments | D | Both |
| [apps/web/src/waha-live-api.ts](../../apps/web/src/waha-live-api.ts) | Sends connection/consent requests and checks the original request after lost responses | D | Added in main |
| [apps/web/src/waha-sync-api.ts](../../apps/web/src/waha-sync-api.ts) | Queries messages and bounded history-import progress | A/D | Added in main |
| [apps/web/src/workspace-api.ts](../../apps/web/src/workspace-api.ts) | Reads orders/calendar/tasks and sends version-bound confirmation | D | Both |
| [apps/web/test_local_operations.py](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/blob/c702f0c/apps/web/test_local_operations.py) | Legacy Python helper failure/operations regression | D/E | Retired |
| [apps/web/tsconfig.json](../../apps/web/tsconfig.json) | Configures TypeScript code checks | D | Both |
| [apps/web/vite.config.ts](../../apps/web/vite.config.ts) | Configures development page and backend request forwarding | D | Both |
| [apps/web/waha-live-api.test.mjs](../../apps/web/waha-live-api.test.mjs) | Formal adapter request/key/error/reconcile regression | D/E | Added in main |
| [apps/web/workspace-api.test.mjs](../../apps/web/workspace-api.test.mjs) | Replay HTTP request/error/authentication regression | D/E | Both |

## Contracts and synthetic examples / 契约与虚构样例

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [contracts/README.md](../../contracts/README.md) | Contract authority/generation/independent schemas/fixture guide | A/B/C/D | Both |
| [contracts/ai/change-proposal.schema.json](../../contracts/ai/change-proposal.schema.json) | Independently versioned AI proposal-only JSON Schema | B/C | Both |
| [contracts/api-v1.md](../../contracts/api-v1.md) | Implemented API versus target/proposed endpoints; C #13 is planning | A/B/C/D | Both |
| [contracts/domain/models.schema.json](../../contracts/domain/models.schema.json) | Generated Pydantic domain schema; never manual edit | A/B/C/D | Both |
| [contracts/evaluation/manifest.json](../../contracts/evaluation/manifest.json) | Offline provider evaluation scenarios/inputs/expectations, not real chats | B/E | Added in main |
| [contracts/events/message-event.schema.json](../../contracts/events/message-event.schema.json) | Independently versioned message-event JSON Schema | A/B | Both |
| [contracts/examples/action-pending.json](../../contracts/examples/action-pending.json) | Pending action contract example, not implemented sending | A/B/C/D/E | Both |
| [contracts/examples/action-unknown.json](../../contracts/examples/action-unknown.json) | Unknown external outcome example: reconciliation required | A/B/C/D/E | Both |
| [contracts/examples/approve-command.json](../../contracts/examples/approve-command.json) | Merchant approval command version/binding example | A/B/C/D/E | Both |
| [contracts/examples/date-only.json](../../contracts/examples/date-only.json) | Date-only example; do not invent a time | A/B/C/D/E | Both |
| [contracts/examples/invalid-ai-confirmed-field.json](../../contracts/examples/invalid-ai-confirmed-field.json) | Negative: reject AI writing confirmed fields | A/B/C/D/E | Both |
| [contracts/examples/invalid-ai-execution.json](../../contracts/examples/invalid-ai-execution.json) | Negative: reject AI asking for direct execution | A/B/C/D/E | Both |
| [contracts/examples/invalid-approval-no-merchant.json](../../contracts/examples/invalid-approval-no-merchant.json) | Negative: reject approval without merchant authority | A/B/C/D/E | Both |
| [contracts/examples/invalid-date.json](../../contracts/examples/invalid-date.json) | Negative: reject invalid date | A/B/C/D/E | Both |
| [contracts/examples/invalid-event-no-account.json](../../contracts/examples/invalid-event-no-account.json) | Negative: reject event lacking account ownership | A/B/C/D/E | Both |
| [contracts/examples/invalid-missing-value.json](../../contracts/examples/invalid-missing-value.json) | Negative: reject values in missing/unknown fields | A/B/C/D/E | Both |
| [contracts/examples/manifest.json](../../contracts/examples/manifest.json) | Positive/negative fixture list, schemas and expected results | A/B/C/D/E | Both |
| [contracts/examples/message-edited.json](../../contracts/examples/message-edited.json) | Synthetic message edit/revision example | A/B/C/D/E | Both |
| [contracts/examples/message-original.json](../../contracts/examples/message-original.json) | Synthetic original appointment message event | A/B/C/D/E | Both |
| [contracts/examples/message-reschedule.json](../../contracts/examples/message-reschedule.json) | Synthetic customer reschedule proposal event | A/B/C/D/E | Both |
| [contracts/examples/message-revoked.json](../../contracts/examples/message-revoked.json) | Synthetic revoke event invalidating old source | A/B/C/D/E | Both |
| [contracts/examples/proposal-reschedule.json](../../contracts/examples/proposal-reschedule.json) | AI reschedule proposal/source; not confirmed mutation | A/B/C/D/E | Both |
| [contracts/examples/scenarios.json](../../contracts/examples/scenarios.json) | Business/reliability scenarios and acceptance expectations | A/B/C/D/E | Both |
| [contracts/examples/session-disconnected.json](../../contracts/examples/session-disconnected.json) | Disconnected connector event example | A/B/C/D/E | Both |
| [contracts/examples/work-order.json](../../contracts/examples/work-order.json) | Order fields/state/version/source example | A/B/C/D/E | Both |
| [contracts/openapi.json](../../contracts/openapi.json) | Generated implemented FastAPI OpenAPI; never manual edit | A/B/C/D | Both |

## Design, operations and acceptance documents / 设计、操作与验收文档

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [docs/en/README.md](../../docs/en/README.md) | Documentation index; headings retain historical dates | A/B/C/D/E | Both |
| [docs/en/adr/0001-foundation.md](../../docs/en/adr/0001-foundation.md) | Stack/monorepo/modular foundation decision | A/B/C/D/E | Both |
| [docs/en/adr/0002-contract-authority.md](../../docs/en/adr/0002-contract-authority.md) | Generated Pydantic authority and independent event/AI versions | A/B/C/D/E | Both |
| [docs/en/adr/0003-approval-and-execution.md](../../docs/en/adr/0003-approval-and-execution.md) | Approval binding/invalidation/unknown outcomes/external reliability | A/B/C/D/E | Both |
| [docs/en/adr/0004-equal-collaboration.md](../../docs/en/adr/0004-equal-collaboration.md) | Equal collaboration permissions and independent review | A/B/C/D/E | Both |
| [docs/en/adr/0005-bounded-waha-observations.md](../../docs/en/adr/0005-bounded-waha-observations.md) | Bounded history/group/media metadata observation limits | A/B/C/D/E | Added in main |
| [docs/en/adr/README.md](../../docs/en/adr/README.md) | ADR index; design rationale differs from delivery progress | A/B/C/D/E | Both |
| [docs/en/architecture.md](../../docs/en/architecture.md) | Module boundaries/state flow/ownership/reliability architecture | A/B/C/D/E | Both |
| [docs/en/contributing.md](../../docs/en/contributing.md) | Issue/branch/review/completion rules | A/B/C/D/E | Both |
| [docs/en/getting-started.md](../../docs/en/getting-started.md) | Verified install/run/migration/test commands and PostgreSQL setup | A/B/C/D/E | Both |
| [docs/en/implementation-status.md](../../docs/en/implementation-status.md) | Dated English implementation and actual verification evidence | A/B/C/D/E | Both |
| [docs/en/overview.md](../../docs/en/overview.md) | Product purpose/current scope/exclusions | A/B/C/D/E | Both |
| [docs/en/role-a-development-roadmap.md](../../docs/en/role-a-development-roadmap.md) | A coherent batch plan/dependencies; not all implemented | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/en/role-a-integration-acceptance.md](../../docs/en/role-a-integration-acceptance.md) | A integration acceptance method and dated results | A（D/E 阅读） / A (D/E readers) | Added in main |
| [docs/en/role-a-message-sync-acceptance.md](../../docs/en/role-a-message-sync-acceptance.md) | A #14 bounded message-sync acceptance/limits | A（D/E 阅读） / A (D/E readers) | Added in main |
| [docs/en/role-a-recovery-acceptance.md](../../docs/en/role-a-recovery-acceptance.md) | Recovery/incident/manual-review acceptance and limits | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/en/role-a-responsibilities.md](../../docs/en/role-a-responsibilities.md) | A responsibility boundaries and role handoffs | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/en/role-a-setup-api-acceptance.md](../../docs/en/role-a-setup-api-acceptance.md) | A #11 formal control API/migration/idempotency acceptance | A（D/E 阅读） / A (D/E readers) | Added in main |
| [docs/en/role-a-stage1-acceptance.md](../../docs/en/role-a-stage1-acceptance.md) | Earlier WAHA adapter/synthetic event acceptance | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/en/role-a-stage2-acceptance.md](../../docs/en/role-a-stage2-acceptance.md) | Durable WAHA ingress stage acceptance | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/en/role-a-stage3-acceptance.md](../../docs/en/role-a-stage3-acceptance.md) | WAHA status/monitoring/integration stage acceptance | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/en/role-a-team-local-development.md](../../docs/en/role-a-team-local-development.md) | Own-account isolated team setup/doctor/evidence instructions | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/en/role-a-waha-handoff.md](../../docs/en/role-a-waha-handoff.md) | Current WAHA capability matrix/limits/role integration points | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/en/role-b-extraction.md](../../docs/en/role-b-extraction.md) | B provider/evidence/evaluation; main LLM gates and remaining work | B（D/E 阅读） / B (D/E readers) | Added in main |
| [docs/en/role-d-frontend-user-guide.md](../../docs/en/role-d-frontend-user-guide.md) | D user operation/run/mode distinctions; dated version matters | D（全队参考） / D (team reference) | Both |
| [docs/en/role-d-stage1-acceptance.md](../../docs/en/role-d-stage1-acceptance.md) | D connection/consent/paging stage acceptance/history | D（全队参考） / D (team reference) | Both |
| [docs/en/team-governance.md](../../docs/en/team-governance.md) | Equal permissions/main protection/independent review rules | A/B/C/D/E | Both |
| [docs/en/whatsapp-connection-flow.md](../../docs/en/whatsapp-connection-flow.md) | Pairing→consent→events→history and boundaries | A/B/C/D/E | Both |
| [docs/project-kickoff-plan.md](../../docs/project-kickoff-plan.md) | Historical kickoff proposal superseded by engineering baseline | A/B/C/D/E | Both |
| [docs/zh/README.md](../../docs/zh/README.md) | Documentation index; headings retain historical dates | A/B/C/D/E | Both |
| [docs/zh/acceptance.md](../../docs/zh/acceptance.md) | E/team acceptance criteria; criteria are not completed results | A/B/C/D/E | Both |
| [docs/zh/collaboration-checklist.md](../../docs/zh/collaboration-checklist.md) | Task/branch/commit/self-check/review checklist | A/B/C/D/E | Both |
| [docs/zh/domain-workflows.md](../../docs/zh/domain-workflows.md) | Business entities/state/approval/execution boundaries | A/B/C/D/E | Both |
| [docs/zh/engineering-standards.md](../../docs/zh/engineering-standards.md) | Engineering modules/naming/contracts/data/logging standards | A/B/C/D/E | Both |
| [docs/zh/onboarding-report-template.md](../../docs/zh/onboarding-report-template.md) | Independent teammate setup/replay/PR acceptance report template | A/B/C/D/E | Both |
| [docs/zh/onboarding.md](../../docs/zh/onboarding.md) | New teammate clone/environment/replay/first PR instructions | A/B/C/D/E | Both |
| [docs/zh/progress.md](../../docs/zh/progress.md) | Dated Chinese implementation and actual verification evidence | A/B/C/D/E | Both |
| [docs/zh/roadmap.md](../../docs/zh/roadmap.md) | Stage plan/dependencies; distinct from actual progress | A/B/C/D/E | Both |
| [docs/zh/role-a-development-roadmap.md](../../docs/zh/role-a-development-roadmap.md) | A coherent batch plan/dependencies; not all implemented | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/zh/role-a-integration-acceptance.md](../../docs/zh/role-a-integration-acceptance.md) | A integration acceptance method and dated results | A（D/E 阅读） / A (D/E readers) | Added in main |
| [docs/zh/role-a-message-sync-acceptance.md](../../docs/zh/role-a-message-sync-acceptance.md) | A #14 bounded message-sync acceptance/limits | A（D/E 阅读） / A (D/E readers) | Added in main |
| [docs/zh/role-a-recovery-acceptance.md](../../docs/zh/role-a-recovery-acceptance.md) | Recovery/incident/manual-review acceptance and limits | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/zh/role-a-responsibilities.md](../../docs/zh/role-a-responsibilities.md) | A responsibility boundaries and role handoffs | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/zh/role-a-setup-api-acceptance.md](../../docs/zh/role-a-setup-api-acceptance.md) | A #11 formal control API/migration/idempotency acceptance | A（D/E 阅读） / A (D/E readers) | Added in main |
| [docs/zh/role-a-stage1-acceptance.md](../../docs/zh/role-a-stage1-acceptance.md) | Earlier WAHA adapter/synthetic event acceptance | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/zh/role-a-stage2-acceptance.md](../../docs/zh/role-a-stage2-acceptance.md) | Durable WAHA ingress stage acceptance | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/zh/role-a-stage3-acceptance.md](../../docs/zh/role-a-stage3-acceptance.md) | WAHA status/monitoring/integration stage acceptance | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/zh/role-a-team-local-development.md](../../docs/zh/role-a-team-local-development.md) | Own-account isolated team setup/doctor/evidence instructions | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/zh/role-a-waha-handoff.md](../../docs/zh/role-a-waha-handoff.md) | Current WAHA capability matrix/limits/role integration points | A（D/E 阅读） / A (D/E readers) | Both |
| [docs/zh/role-b-extraction.md](../../docs/zh/role-b-extraction.md) | B provider/evidence/evaluation; main LLM gates and remaining work | B（D/E 阅读） / B (D/E readers) | Added in main |
| [docs/zh/role-d-frontend-user-guide.md](../../docs/zh/role-d-frontend-user-guide.md) | D user operation/run/mode distinctions; dated version matters | D（全队参考） / D (team reference) | Both |
| [docs/zh/role-d-stage1-acceptance.md](../../docs/zh/role-d-stage1-acceptance.md) | D connection/consent/paging stage acceptance/history | D（全队参考） / D (team reference) | Both |
| [docs/zh/scope.md](../../docs/zh/scope.md) | P0/P1 scope and exclusions; no implicit expansion | A/B/C/D/E | Both |
| [docs/zh/team-governance.md](../../docs/zh/team-governance.md) | Equal permissions/main protection/independent review rules | A/B/C/D/E | Both |
| [docs/zh/whatsapp-connection-flow.md](../../docs/zh/whatsapp-connection-flow.md) | Pairing→consent→events→history and boundaries | A/B/C/D/E | Both |

## Learning artifacts / 学习资料

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [docs/en/kyrie-file-atlas.md](../../docs/en/kyrie-file-atlas.md) | This file-by-file responsibility/version/reading atlas | D（全队参考） / D (team reference) | New |
| [docs/en/kyrie-learning-guide.md](../../docs/en/kyrie-learning-guide.md) | This learning path: GitHub/architecture/progress/D code/exercises | D（全队参考） / D (team reference) | New |
| [docs/learning-assets/README.md](../../docs/learning-assets/README.md) | Screenshot provenance/date/public scope/teaching purpose | D/E | New |
| [docs/learning-assets/github-actions.jpg](../../docs/learning-assets/github-actions.jpg) | Actual GitHub Actions screenshot; read with guide | D | New |
| [docs/learning-assets/github-code.jpg](../../docs/learning-assets/github-code.jpg) | Actual GitHub Code screenshot; read with guide | D | New |
| [docs/learning-assets/github-commit.jpg](../../docs/learning-assets/github-commit.jpg) | Actual GitHub Commit dcd7527 screenshot; read with guide | D | New |
| [docs/learning-assets/github-diff.jpg](../../docs/learning-assets/github-diff.jpg) | Actual GitHub Files changed screenshot; read with guide | D | New |
| [docs/learning-assets/github-issue19.jpg](../../docs/learning-assets/github-issue19.jpg) | Actual GitHub Issue #19 screenshot; read with guide | D | New |
| [docs/learning-assets/github-pr16.jpg](../../docs/learning-assets/github-pr16.jpg) | Actual GitHub Merged #16 screenshot; read with guide | D | New |
| [docs/learning-assets/github-pulls.jpg](../../docs/learning-assets/github-pulls.jpg) | Actual GitHub PR list screenshot; read with guide | D | New |
| [docs/zh/kyrie-file-atlas.md](../../docs/zh/kyrie-file-atlas.md) | This file-by-file responsibility/version/reading atlas | D（全队参考） / D (team reference) | New |
| [docs/zh/kyrie-learning-guide.md](../../docs/zh/kyrie-learning-guide.md) | This learning path: GitHub/architecture/progress/D code/exercises | D（全队参考） / D (team reference) | New |

## Runtime configuration / 运行配置

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [infra/backend.Dockerfile](../../infra/backend.Dockerfile) | Builds backend/worker container image | A | Both |
| [infra/compose.yaml](../../infra/compose.yaml) | Development API/worker/web/PostgreSQL services/ports/volumes | A | Both |
| [infra/nginx.conf](../../infra/nginx.conf) | Web reverse-proxy/static/API routing configuration | A/D | Both |
| [infra/waha-arm64.compose.yaml](../../infra/waha-arm64.compose.yaml) | Pinned ARM64 WAHA image/platform override | A | Added in main |
| [infra/waha-ingress.compose.yaml](../../infra/waha-ingress.compose.yaml) | Durable ingress service Compose override | A | Both |
| [infra/waha-probe.Dockerfile](../../infra/waha-probe.Dockerfile) | Builds connector probe/ingress support image | A | Both |
| [infra/waha-recovery.compose.yaml](../../infra/waha-recovery.compose.yaml) | Health monitoring/recovery development configuration | A | Both |
| [infra/waha-setup-check.compose.yaml](../../infra/waha-setup-check.compose.yaml) | Setup diagnostic/acceptance service configuration | A/E | Added in main |
| [infra/waha-team.compose.yaml](../../infra/waha-team.compose.yaml) | Isolated team PostgreSQL/runtime override | A | Both |
| [infra/waha.compose.yaml](../../infra/waha.compose.yaml) | Optional base WAHA service Compose | A | Both |
| [infra/web.Dockerfile](../../infra/web.Dockerfile) | Builds frontend/static nginx container | A/D | Both |

## Scripts / 脚本

| File | Responsibility / learning value | Coordination | Presence |
| --- | --- | --- | --- |
| [scripts/check_baseline.py](../../scripts/check_baseline.py) | Checks Markdown links, schemas/fixtures/baseline; not runtime acceptance | A/B/C/D/E | Both |
| [scripts/check_waha_recovery.py](../../scripts/check_waha_recovery.py) | Reproducible fault/recovery/manual-review acceptance runner | A/E | Both |
| [scripts/check_waha_setup.py](../../scripts/check_waha_setup.py) | Setup/connection diagnostic runner and failure evidence | A/E | Added in main |
| [scripts/check_web_contracts.mjs](../../scripts/check_web_contracts.mjs) | Regenerates frontend API types and checks OpenAPI drift | D | Both |
| [scripts/export_contracts.py](../../scripts/export_contracts.py) | Exports domain/OpenAPI from models/routes; --check detects drift | A/B/C/D | Both |
| [scripts/replay_waha.py](../../scripts/replay_waha.py) | Command-line synthetic WAHA JSON replay | A/E | Both |
| [scripts/requirements-baseline.txt](../../scripts/requirements-baseline.txt) | Pinned documentation/schema validator dependencies | A/E | Both |
| [scripts/run_evaluation.py](../../scripts/run_evaluation.py) | Offline extraction scenario evaluation; not live-model acceptance | B/E | Added in main |
| [scripts/smoke_deepseek.py](../../scripts/smoke_deepseek.py) | Controlled DeepSeek invocation smoke tool; main gates still apply | B/E | Added in main |
| [scripts/smoke_replay.py](../../scripts/smoke_replay.py) | HTTP synthetic replay smoke: input through confirmation/planning | A/C/D/E | Both |
| [scripts/smoke_waha_ingress.py](../../scripts/smoke_waha_ingress.py) | Controlled HTTP ingress smoke verification | A/E | Both |
| [scripts/smoke_waha_local.py](../../scripts/smoke_waha_local.py) | Local binding/API health smoke; not full real-message acceptance | A/E | Both |
| [scripts/waha_container_config.py](../../scripts/waha_container_config.py) | Builds guarded WAHA container configuration/architecture parameters | A | Both |
| [scripts/waha_ingress.py](../../scripts/waha_ingress.py) | CLI starts the durable ingress HTTP service | A | Both |
| [scripts/waha_local.py](../../scripts/waha_local.py) | Local connection/config/init/QR and private-output helper | A | Both |
| [scripts/waha_team.py](../../scripts/waha_team.py) | Team init/up/doctor/run/checkpoint/verify and isolation guards | A/E | Both |

## Use files to locate delivery progress

D: entry → connection workspace → adapters/state → chat helpers/view → tests. Replay: workspace → store/API → workorders/planning.

A #11: controls/0005_waha_controls/0006/setup acceptance; D #15: live adapter/workspace. A #14: sync/0008/WahaMessages/sync acceptance; D #16: chat choices/component tests. B #9/#18/#20: extraction/0005_extraction_evidence/evaluation. C #13 new-order work remains a target in api-v1.md, not an implemented endpoint. 0007 merges A/B migration heads.

See guide section 3 for remaining issues and acceptance. English/Chinese counterparts are one delivery, not separate achievements. File count is not a contribution score.


## Update after C integration (2026-10-16)

`InspectOrderAttempt.tsx` explains and reviews a saved command receipt; `order-command-api.ts` retains the exact key and clears only verified completed records. `workspace_api.py` only reads the existing command cache; C still owns all business writes. Generated API types now include C's create/status commands and the typed readonly inspection request.
