# D-01: frontend connection and conversation selection

## PR #16 review follow-up — 2026-10-10

The user authorized shared progress updates and merging dependency PR #14. Its exact head `56e482e` passed independent code/test re-review and merged as `ab52d3e`; PR #16 now targets main and incorporates that merge without conflicts. Original Kyrie sources remain intact. Current shared evidence is in [implementation status](implementation-status.md); the October 10 initial-delivery entry below is the pre-merge publication history.

New `connection-workspace.test.mjs` mounts the actual workspace, child controls and live HTTP adapter in a local DOM with a stateful synthetic response fixture. Three regressions cover (1) cross-page/filter selection → complete version-bound PUT → reread/remount retaining both → global withdrawal, (2) pagination/filter/size causing no provider discovery and explicit load-more preserving next offset/hidden picks, and (3) real IDs behind missing-name fallbacks, withdrawal, clean dirty state and explicit phone-only hints. `jsdom` is a pinned development-only dependency. This is automated DOM/API-fixture integration, not a real browser/backend or disk-persistence test.

Review clarification: the row text is “个人聊天”; missing display names do not create fake or empty choice IDs. Existing authorization must remain withdrawable when unnamed. Supplied phone-only labels remain visible with “未提供昵称”; masking is not implemented and restoring missing nicknames still needs upstream mapping. Shared progress documents were previously excluded by the user's scope, and are now synchronized under the new authorization. Native Windows and real nickname acceptance remain pending. The earlier 24-choice browser-preview evidence remains supplementary.

Actual follow-up verification: **53 frontend tests passed**, API drift, source and all six test-file format checks, TypeScript/build, locked dependency audit, contract export/baseline and Git whitespace/scope passed. PR #14's separate pre-merge recheck completed 349 PostgreSQL-configured tests and 10 disposable HTTP/worker checkpoints with evaluation 7/7 and cleanup; some B fixtures use SQLite. Independent approval of PR #16 is still pending; neither a discussion comment nor passing CI is an approval.

## Conversation-list follow-up — 2026-10-10

This D-only batch uses `codex/d01-chat-list`, based on Andy's open [PR #14](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/14), commit `56e482e`. The screenshot's search/filter UI and canonical `WahaChoice.kind` originate there. The PR targets `Andy_WAHA_message_sync` so Andy's backend/contracts do not appear in this frontend diff. PR #15's earlier D-01 delivery has merged into main (`1336c60`); the October 9 entries below describe that earlier delivery. Original `Kyrie_Frontend` / `c702f0c` remains intact. No merge is performed in this follow-up.

- **D01-CHAT-TYPE:** rows and filtering use canonical `direct` / `group`. Missing/unrecognized metadata explicitly displays “类型未提供”; names and opaque IDs never determine type. Group avatars are distinct.
- **D01-CHAT-PAGE:** browse 8 (default), 16 or 24 loaded choices per page. Search/type/size changes start at page 1; smaller refreshed catalogs clamp the current page. Counts and empty results are explicit. The full loaded catalog and cross-page pending selection stay in the parent workspace: saving/revoking never uses only the visible page. Backend discovery remains explicit, with at most 100 choices per batch and the existing cursor; it is separate from display pagination. Existing selection cap, expiry, version and connection guards remain in force.
- **D01-CHAT-NAME:** provider labels render as text, with explicit unnamed/authorized fallbacks. Direct choices with number-only labels retain that number and display “未提供昵称”. Diagnosis with fictional input reproduced the upstream limitation: `LocalWahaClient.recent_chats()` reads only `name`; a number-valued `name` remains a number even if another provider nickname field is present. The canonical choice exposes only `label`, not a separate nickname. Selected choices can also fall back to `Authorized conversation` after candidate metadata expires. This frontend cannot restore absent nicknames; the integration maintainer must resolve canonical display names server-side. Backend/contact lookup and shared contracts are unchanged. Rediscovery can refresh labels supplied by the server, but cannot guarantee a missing nickname.

Verification for this follow-up: frontend **50 tests passed**, including five new type/label/pagination regressions; `check:api`, `format:check`, all five test-file formatting checks, TypeScript and production build passed. Contract export consistency, baseline and Git whitespace/scope checks passed. Browser preview with 24 fictional choices verified first/last pages, alternate size, direct/group filter, empty search, two choices selected across pages, save and reload of both, and no horizontal overflow at 375px/320px. Preview warning/error logs were empty. A synthetic unchanged-backend diagnostic confirmed the name limitation above. These are preview and synthetic checks, not live contact/nickname acceptance or native Windows evidence. No full backend suite was rerun for this frontend-only change. Independent review and upstream nickname resolution remain pending; no real contacts, QR or session material are tracked.

## Current D-01 delivery — 2026-10-09

Owner: Kyrie. Local main was fast-forwarded from `d6e70eb` to `5f9df37`, which includes [Andy's merged PR #11](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/pull/11). The original `Kyrie_Frontend` checkout and unpushed `c702f0c` remain intact. This batch is prepared in the attached `d01-pr11` worktree on `codex/d01-pr11`, based on updated main; it preserves the frontend replay corrections from `c702f0c`. The user subsequently authorized committing, pushing and opening a PR for this separate branch. Merge remains excluded pending acceptance and review.

Only `apps/web` and the D-specific English/Chinese acceptance and user-guide files change relative to that main. Backend, Andy/WAHA tools, B/C sources, migrations, shared documentation and contracts remain untouched. The main-generated client types are used unchanged. Current D progress/evidence is recorded here because the user limited edits to D documents.

**D-01 frontend implementation is complete against PR #11's implemented local APIs. Real phone pairing, native Windows runtime acceptance and independent teammate review remain external acceptance gates.** Automated synthetic tests do not establish them. The ongoing replay limitations below are preserved and this batch remains unmerged.

### Delivered and accepted scope

| D-01 task | Current behavior / evidence |
| --- | --- |
| Authenticated connection and QR | Owned setup, connect/recover and operation polling use `/api/v1`; QR stays in a short-lived memory blob and clears on pause, failure, expiry, logout or leaving the page. The retired Vite/Python bridge is absent. |
| Operation feedback and recovery | Pending/terminal outcomes have separate labels. Lost POST responses retain the exact action/version/key in browser session storage (opaque IDs only), across page reloads where storage is available. An explicit original-request check uses backend idempotency. `result_unknown` requires explicit read-only reconciliation. Neither is automatically retried. |
| Conversation discovery and consent | Loading persisted authorization is separate from explicit discovery of up to 100 recent chats. Choices use generated opaque IDs; labels render as plain text. Saving rereads persistent selected IDs. Expired new choices cannot be granted. |
| Save, discard and revoke | Status polling keeps unsaved choices. Dirty choices can be discarded and reloaded after a version conflict, expiry or unknown save. Failed reads/writes block further saving until a successful reread. Existing authorization can be reduced or emptied while disconnected, paused or private configuration is unavailable. |
| Pause/resume and health | Explicit controls retain selected authorization and show provider connectivity, freshness, receiving permission and processing readiness separately. A pause/version change requires rereading authorization before another save. |
| Recovered-issue review | Explicit no-history-import confirmation binds the displayed recovered issue IDs; active incidents cannot be acknowledged. Historical audit is retained. |
| Preview and replay preservation | Synthetic preview remains memory-only. The `c702f0c` replay store/API/UI regressions and bilingual usage guide are retained; no sample data or live session is reset. |

### Actual verification

- Pinned Node **24.15.0**, npm **11.12.1**, project Python **3.12.10** and existing locked dependencies were used. Frontend `npm test`: **40 passed**; `check:api`, `format:check`, TypeScript and production build passed. The additional formatting check covers all four test files.
- Unmodified `scripts/check_waha_setup.py --run --suite --frontend` uses its disposable PostgreSQL database and synthetic provider: **316 backend tests passed**, with one existing Starlette/httpx deprecation warning. Some extraction unit fixtures use SQLite; the PostgreSQL-configured suite is not a claim that every test exercises PostgreSQL locking. Eight HTTP/worker/evaluation checkpoints passed. The runner finished with exit 0 after Alembic check and cleanup of only its disposable resources.
- Applicable backend Ruff check/format, `scripts/export_contracts.py --check`, `scripts/check_baseline.py` and Git whitespace/scope checks passed. Generated frontend types match main's implemented OpenAPI.
- Browser acceptance against that actual API/worker with fictional contact metadata covers discovery/save, durable reload, pause/resume, paused revocation, version-change reread, discard, recovered-issue review, private synthetic QR transport and logout/account isolation. The initial-entry state, explicit FAILED recovery, memory blob transport (a synthetic 1×1 PNG), pause/resume image cleanup, status-refresh preservation of dirty choices, save/reload persistence, discard, paused and missing-config withdrawal, recovered-only issue review with retained audit, and another account's empty connection list passed. An injected persisted `result_unknown` fixture was resolved using the explicit reconciliation button, without creating another connect/recover operation. Network/partial-response and version-zero original-request cases are Node regressions, not evidence of a real interrupted provider send. Browser warning/error logs were empty at the final preview checkpoint. Screenshots show fictional preview data and remain ignored; no real contacts, QR or credentials enter tracked files.

### Existing local runtime update — 2026-10-09

At the user's explicit request, the existing local ingress API, worker and monitor were rebuilt from `5f9df37` and recreated. A private Git-ignored database backup and the previous images were retained first. Alembic upgrade from `0004_waha_recovery` to `0007_merge_waha_extraction` and Alembic check passed. Comparison before and after confirmed the existing connection ownership, receiving switch and conversation authorization were preserved; the allowlist remains empty. There was no legacy unresolved restart journal to import. The provider/probe containers and WhatsApp session volume were not recreated or reset; their existing amd64 runtime was retained.

The API at `http://127.0.0.1:18702` returned health 200 and exposes PR #11's setup, QR, operations, chats, pause and resume routes. The visible frontend at `http://127.0.0.1:5173` successfully logged in, loaded the authenticated setup/status and decoded the real QR into a private memory blob; browser warning/error logs were empty. The user can now scan locally. This confirms QR display, not successful phone pairing or reception. Historical incidents remain unreviewed, and no conversation permission, provider control operation or message send was submitted during verification. No real QR was saved in the evidence. The runtime images use the attached updated-main worktree; rebuilding from the original older `Kyrie_Frontend` sources would restore an older backend.

During the user's subsequent retry, the provider became `FAILED` and recovery reported `WAHA_REMOTE_CONFIGURATION_UNCONFIRMED`. Read-only inspection confirmed the old callback still targeted the local probe, rather than the canonical ingress required by PR #11. The initial runtime update had verified QR display but missed this prerequisite. The existing operator configuration method migrated that callback, preserving the session and empty allowlist; the provider progressed through `STARTING` to `SCAN_QR_CODE`. Clicking **核对未知操作（不重发）** then completed the pending recovery through read-only provider verification, and the page decoded a fresh QR. No extra recovery POST was sent to the provider. Normal failed/stopped recovery uses **重新连接并获取二维码**; while waiting for scan, **刷新二维码** retrieves the current image without restarting the session. Phone pairing itself remains unverified.

Use the [current frontend guide](role-d-frontend-user-guide.md). Product routes are governed by [Andy's setup API agreement](role-a-setup-api-acceptance.md); current service preparation is in [his local-development guide](role-a-team-local-development.md). The old proposed routes, bridge commands and dated evidence below describe earlier revisions and must not be used for current startup.

## Historical record (through 2026-10-08)

Owner: Kyrie. Prepared on 2026-10-06 on `Kyrie_Frontend`, based on `main` merge commit `0cd7e3f`. The user requested a local commit with message `还没测试`; no push. Real WhatsApp pairing was attempted on 2026-10-07 but has not succeeded; user acceptance remains pending. Verification evidence is recorded below. [Chinese counterpart](../zh/role-d-stage1-acceptance.md).

## Scope and current result

This batch changes only frontend files in `apps/web` and this pair of D-specific acceptance documents. Backend, WAHA tools, migrations, infrastructure, dependencies, shared documentation, contracts and generated types are identical to main. Earlier uncommitted D-01 backend/shared changes were backed up privately under ignored `local-data` and removed from the active changes.

The desktop workspace provides a pairing area, connection/processing health, conversation checkboxes, explicit save, revoke and discard controls, and a clearly marked synthetic preview. Read authorization does not enable automatic replies. Automatic replies and message sending remain separate milestones.

Live mode uses main's existing authenticated connection and recovery-issue queries. It shows connection state, sampled readiness, freshness, receiving permission and unresolved issues separately. Product pairing and conversation-selection APIs remain pending. An explicitly enabled local development bridge displays real pairing status and QR images using Andy's unchanged server-side adapter; default development and production builds leave pairing disabled. The 2026-10-08 local update adds failed-session restart and explicit review of recovered issues through the same opt-in bridge. Initial session creation and live conversation selection remain pending. The browser never calls WAHA administration endpoints.

The preview is browser memory only: simulated scan, connect/disconnect, stale status, selection, saving and offline revocation. Leaving the preview or reloading resets it. The QR area is a placeholder, not a scannable QR. Preview success does not prove database writes, real authorization, pairing or delivery.

**End-to-end D-01 acceptance is pending Andy's authenticated product APIs and real-account testing.** This frontend batch does not implement those APIs.

## Interfaces to agree with Andy

Already implemented in main and used by live mode:

| Query | Frontend use |
| --- | --- |
| `GET /api/v1/connectors` | Account-scoped, paginated `ConnectorStatus`; use generated main types |
| `GET /api/v1/connectors/{id}/recovery-issues` | Account-scoped, paginated `RecoveryIssue`; use generated main types |

The following product routes and shapes are **frontend proposals only**. Andy should confirm or replace them before implementation. They are not additions to the shared contract or evidence of implemented product routes. The local development bridge below does not replace these APIs.

| Proposed route | Needed behavior |
| --- | --- |
| `GET /api/v1/connectors/{id}/pairing` | Current pairing state, `connected`, `qr_available`; authenticated owner only |
| `POST /api/v1/connectors/{id}/pairing/start` | Start/reconnect an owned session; report unknown outcomes without blind retries |
| `GET /api/v1/connectors/{id}/qr` | Private, non-cacheable PNG while waiting for scan; no credentials/provider session files |
| `GET /api/v1/connectors/{id}/chats` | Paginated discovery metadata for visual selection; no message bodies |
| `GET /api/v1/connectors/{id}/selection` | Authoritative version and selected choices, readable while disconnected |
| `POST /api/v1/connectors/{id}/selection` | Atomic replace using expected version and server-issued choices; empty selection revokes all |

Preview-local `Pairing`, `Choice`, `Selection` and `Discovery` in `src/connection-api.ts` are provisional frontend shapes, not canonical domain models. Suggested selection response: `{version, selected}`; choice: `{choice_id, token, name, kind, selected, conversation_id}`; discovery: `{items, next_offset}`. IDs/tokens must be scoped and validated server-side. After agreement, Andy owns backend models, migrations, API and generated contracts; D will adopt the generated types and enable the live adapter in a follow-up.

Agree response envelopes, pagination, expiration/error codes, same-origin session authentication, CSRF and idempotency before enabling writes. Save/revoke must survive reload, check versions and update the authoritative allowlist; business content must not be stored or sent to models before authorization. Unknown write outcomes must be reconciled. Frontend never receives WAHA keys, webhook secrets or provider session files. This is read/processing permission, not automatic-reply permission.

## Windows/macOS preview and existing API

From `apps/web`, with the repository's pinned Node/npm dependencies installed:

```bash
npm run dev
```

Open http://127.0.0.1:5173 and select **D-01 演示预览**. No Docker or login is needed for preview. For live status, start main's backend using its existing setup, sign in, then use **WhatsApp 连接**. An account without a provisioned connection shows an empty state. Backend setup remains owned by its maintainers; see [existing getting started](getting-started.md) and [Andy's local-development guide](role-a-team-local-development.md).

The Vite default proxy remains `http://127.0.0.1:18000`. To inspect your already configured ingress backend instead, set only the frontend process environment:

```bash
GIGMATE_API_URL=http://127.0.0.1:18702 npm run dev
```

The proxy accepts local HTTP origins only. This selects an existing backend; it does not provision WhatsApp or add missing product APIs. Existing backend origin/authentication requirements still apply.

To display a real QR in the page using your already initialized, workspace-bound Andy team setup, keep its services/session running, then start the frontend from `apps/web`:

```bash
GIGMATE_API_URL=http://127.0.0.1:18702 GIGMATE_LOCAL_PAIRING=1 npm run dev
```

Windows PowerShell equivalent, also from `apps/web`:

```powershell
$env:GIGMATE_API_URL = "http://127.0.0.1:18702"
$env:GIGMATE_LOCAL_PAIRING = "1"
npm run dev
```

The web UI uses standard browser APIs. The local bridge selects `.venv/Scripts/python.exe` on Windows and `.venv/bin/python` on macOS, resolves paths without shell commands, and hides the Windows child-process console. Each machine must initialize its own existing Andy team environment with the repository's pinned Node/npm/Python dependencies and running Docker services. macOS was verified; Windows compatibility has been inspected in code but a native Windows run remains for peer acceptance. Apple Silicon still needs a compatible WAHA image/platform configuration as recorded below; this frontend does not change Andy's Compose files.

Sign in to the local workspace and use **WhatsApp 连接**. While the provider is in `SCAN_QR_CODE`, the page automatically loads a fresh PNG into browser memory, refreshes it every 20 seconds while visible, and offers manual refresh. A displayed image is hidden 30 seconds after retrieval unless replaced; provider rotation can still invalidate it earlier. No PNG file needs to be opened in Preview. The existing ignored `qr.png` is neither read nor rewritten by this bridge. Logout, failed status/QR reads, non-QR provider state and leaving the workspace clear the image and revoke its object URL. A successful image display does not establish phone pairing.

`apps/web/local-pairing.mjs` is a Vite development middleware, disabled unless explicitly opted in and absent from the production server/build. Its read-only routes are `GET /__gigmate_local_pairing/{connection_id}/status` and `/qr`. Requests require a loopback socket/Host, same-origin checks, a custom request header and an authenticated app session. Ownership and enabled receiving permission are resolved through main's existing connectors API before and after retrieval; the Python process also checks the workspace profile and private connection binding. Only safe status fields or private, non-cacheable PNG bytes reach the browser. Credentials remain in the existing Python server-side adapter. The additional opt-in local mutations are described below. There are no chat reads, allowlist writes or sends. This local tool is not a deployable onboarding API; Andy still owns the future authenticated product APIs and shared contracts.

## Acceptance evidence

Verification on 2026-10-06 is recorded here, without changing shared progress documents:

- Scope audit: exactly five frontend files (`main.tsx`, `vite.config.ts`, `ConnectionWorkspace.tsx`, `connection-api.ts`, `connection.css`) and these two D documents differ from main. Before committing, no changes were staged and branch HEAD equaled `0cd7e3f`. Backend/WAHA, shared contracts/generated types, dependency locks and shared documentation match main byte-for-byte.
- Frontend `check:api`, `format:check`, TypeScript and production build passed. Pinned Node 24.15.0 / npm CLI 11.12.1 were used.
- Unmodified main: contract export check, baseline (52 Markdown files / 253 local links), Ruff check/format and pytest passed: **248 passed, 5 skipped**. PostgreSQL-specific cases were skipped; no PostgreSQL locking claim.
- A fresh, ignored SQLite development database was migrated using main's existing migrations, seeded with fictional accounts, and passed Alembic check. The backend was restarted from main source, replacing the earlier D-01 backend runtime. Real local API login, empty connection and existing replay reads passed.
- Browser-only preview: no business API requests; selection/save/discard, unsaved selections surviving a status refresh, offline revoke, stale state and reset on leaving preview passed.
- Intercepted synthetic fixtures matching main's status/recovery API: connection pagination, multiple connections, removal of the currently selected connection, independent connected/readiness/review display, network failure/recovery and 401 data clearing passed. Pairing/chat/save/revoke controls stayed disabled. No unimplemented connector routes or HTTP writes were requested.
- Desktop and 320/375px preview/live-fixture layouts passed with no horizontal overflow or page errors. Desktop/mobile screenshots were visually inspected. Synthetic screenshots and the browser test driver remain ignored local artifacts.

Required frontend commands: `npm run check:api`, `npm run format:check`, `npm run build`. Contract and baseline checks must use unchanged main sources. Browser acceptance must distinguish real main API responses from intercepted synthetic status fixtures.

Pending external verification: real WAHA phone pairing, live chat discovery, persistent save/revoke and independent teammate review. The later PostgreSQL evidence is recorded below; neither synthetic preview nor a SQLite development login proves live integration.

## Computer-controlled verification: 2026-10-07

At the user's request, the committed D-01 frontend (`d0859f0`) was operated through the visible local browser. Simulated scan, loading choices, explicit save, preserving unsaved choices during status refresh, discarding changes, revoking while disconnected, stale/review indicators and reset on leaving the preview passed. Real local development login, existing replay reads, logout and API shutdown/recovery states passed. These preview writes are browser memory, not live conversation authorization. A synthetic acceptance screenshot remains under ignored `local-data`.

Docker Engine/Compose are available. Andy's unchanged team tools initialized a new developer-owned private setup with an empty allowlist and a separate PostgreSQL 17.9 database. The full unmodified backend suite using isolated PostgreSQL test schemas passed: **253 passed, no skips** (one existing Starlette/httpx warning). No main/shared source or generated contract changes were made; this follow-up only records evidence in D's two documents. No additional commit or push.

Mac compatibility: the pinned WAHA image has no `linux/arm64/v8` manifest, so the stock team startup failed on this Apple Silicon Mac. A temporary Compose override supplied through stdin sets only the WAHA service to `linux/amd64`; tracked Compose files remain unchanged. Andy should decide how to document/support Apple Silicon in the team startup. The compatible image subsequently downloaded successfully and all six local services started. Doctor reported Docker/database/binding/API healthy. An initially absent provider session was created once, then reported `SCAN_QR_CODE`. A private PNG was generated using the existing CLI, confirmed Git-ignored with mode 0600, and opened in macOS Preview for the user to scan. No QR bytes were included in tracked evidence. The frontend was restarted with process-only `GIGMATE_API_URL=http://127.0.0.1:18702`; main's existing APIs authenticated the local developer and displayed the real connecting state, freshness and recovery review while absent product APIs remained disabled. The receiving allowlist remains empty. The user reported the phone message `Can't link new devices right now`; the provider still reported `SCAN_QR_CODE`, not `WORKING`. The displayed PNG was refreshed once using the existing CLI, confirmed to have changed, and reopened for a prompt retry. This does not establish the cause of the phone error. Real pairing remains unverified.

The retry produced the same phone message. The user elected to end the real-pairing test; an account issue is suspected by the user but not established by this verification. No further scan, session reset or account troubleshooting was performed. The final live page shows an unconnected session and a processing pipeline that is not ready. Its QR-free screenshot is an ignored local artifact. Local services remain available for a later test; this is not successful live D-01 acceptance.

## In-page QR correction: 2026-10-07

The user requested that the QR be displayed in the browser instead of a separate local image viewer, and authorized a local commit after display verification. Changes are confined to D's frontend development middleware/configuration, frontend adapter/workspace, tests and these two documents. Andy/B/C sources, infrastructure, migrations, dependencies, shared documentation, generated types and contracts remain unchanged. The later cross-platform review request authorizes publishing `Kyrie_Frontend` and opening a PR against `main` for teammate review and merge.

Browser control confirmed the real in-page image decoded successfully at **276×276**, used an in-memory blob URL, loaded again on manual refresh and automatically refreshed while visible. It disappeared on logout and appeared again after login. When the provider entered `FAILED`, the page hid the QR as expected; after confirming the failed state, one existing Andy CLI restart restored `SCAN_QR_CODE` and the page resumed image loading. The synthetic preview still uses fictional connection/selection data and contains no real QR. This verification does not retry the phone scan or claim `WORKING`. A screenshot of the controls below the QR is retained only under ignored `local-data` and excludes QR pixels.

Run `node --test local-pairing.test.mjs` from `apps/web` for the eight focused bridge tests: authenticated image/status, denied login/origin/Host/connection access, paused permission, expiry during retrieval, paginated ownership, invalid PNG/provider errors, connected-state QR rejection, backend outage and a missing project Python environment. Also run the existing frontend API/format/build checks and `prettier --check local-pairing.mjs local-pairing.test.mjs`. Keep QR/credentials out of tracked evidence.

Actual checks: **8 bridge tests passed**; frontend `check:api`, formatting, TypeScript and production build passed. A build with the local opt-in environment set still excluded the local pairing route from its client bundle. Unauthenticated local QR access returned 401. Direct Vite file requests for the private config/QR returned the SPA HTML fallback, not private JSON/PNG; private `local-data` is explicitly denied by the frontend filesystem configuration. Contract export and baseline checks passed. The documented Ruff scope (`apps/backend`, `scripts/export_contracts.py`, `scripts/smoke_replay.py`) passed. An additional broader Ruff run over all `scripts` found an existing unused `sys` import and formatting issue in unchanged main's `scripts/check_baseline.py`; it was preserved under the user's ownership boundary. The unchanged backend PostgreSQL suite had already passed 253 tests earlier that day and was not repeated for this frontend-only correction. Browser warning/error logs were empty after final display verification.

## Local review follow-up: 2026-10-08

This batch addresses Lena's PR #4 state-guidance review and the user's reconnect/clear-issue requests. The user explicitly requested local acceptance first: no commit, push, GitHub reply or review-thread resolution. Only `apps/web` and these two D acceptance documents change; Andy/B/C backend, tools, infrastructure, migrations, contracts, generated types, dependencies and shared progress documents are preserved.

Connected, disconnected, scanning and uncertain states have distinct prominent headings and contextual primary actions. Stale/failed status reads override any older connected result, hide QR content and offer **Refresh status** first. A fresh failed session offers **Reconnect and get QR**; connected sessions hide QR/restart controls. The synthetic preview supports these states and explicit review of a recovered gap while retaining a separate unrecovered issue.

The opt-in local bridge adds `POST /__gigmate_local_pairing/{id}/restart` with a UUID `key`, and `/review-issues` with an explicit `confirmed: true` and 1–100 unique `issue_ids`. They require same-origin POST, bounded strict JSON, the custom header, app session and CSRF. D's `local-operations.py` reuses unchanged identity, failed-session restart and recovery acknowledgement functions. It rechecks the private workspace binding, ownership, enabled receiving permission and CSRF in a transaction. Account/connection row locks serialize local commands. Credentials travel to Python through stdin, never command arguments or responses. This is development tooling, not a product API or shared contract.

Reconnect never interrupts a working/scanning/starting session. A private atomic dispatch record under ignored `local-data/d01-operations` deduplicates the latest attempt, applies a 30-second cooldown and preserves uncertain outcomes across process restarts. An uncertain attempt cannot be blindly resent; refresh/reconciliation is required. Successful dispatch is not proof that QR generation or phone pairing completed. Docker/service outages, first-time setup and provider configuration errors still require the integration owner.

**Clear recovered issues** requires the operator to review the shown intervals and confirm that no history import is needed. The server revalidates exactly those IDs and recovery state; a bad/missing/unrecovered row rejects the whole batch. It uses the existing `reviewed_no_import` acknowledgement, retains audit rows and messages, and performs no history import. Active outages remain visible. The control is disabled when no recovered items exist, the query fails, or confirmation/local capability is absent.

Actual evidence:

- **14 Node tests passed**: bridge access/method/origin/CSRF/input guards, ownership, paused receiving, redaction, uncertain outcomes and UI state precedence. **15 Python tests passed on PostgreSQL**, using disposable random schemas: explicit atomic scoped acknowledgement, audit retention, login/CSRF/expiry/owner/mapping/permission denial, cooldown, persisted unknown outcome and concurrent duplicate restart dispatching once. SQLite fallback separately passed 14 tests with the PostgreSQL locking case skipped; it is not locking evidence.
- Real Vite-to-Python requests rejected incorrect CSRF (403), restart of the currently scanning session (409 `WAHA_RECOVERY_NOT_REQUIRED`) and clearing an active provider outage (409 `COMPONENT_STILL_UNAVAILABLE`). Real QR decoded in the page at **276×276**, using a memory blob URL. No phone scan was retried. A real failed-session button dispatch remains pending a compatible `FAILED` occurrence; synthetic/provider-double and PostgreSQL concurrency tests do not establish successful phone pairing.
- Controlled runtime testing stopped only the unpaired, empty-allowlist local session. This exposed an unchanged Andy adapter limit: `LocalWahaClient.status()` rejects the stopped provider's missing engine information with `WAHA_ENGINE_MISMATCH`, blocking the existing restart helper. The session was restored with a guarded operator start and again reported `SCAN_QR_CODE`; the frontend reports this limitation rather than bypassing the adapter. Andy needs to support stopped-session status/recovery. No Andy source/configuration file changed.
- Browser synthetic acceptance verified distinct connected/disconnected/stale guidance, reconnect preview, explicit clearing of only recovered items, retained active outage and disabled clear when none remain. Desktop and 320px layouts were inspected with no horizontal overflow. Screenshots contain synthetic data only and remain ignored local artifacts.
- Frontend API generation check, formatting, TypeScript/production build, local helper Ruff check/format, generated-contract check and baseline passed. The full unchanged backend suite was not repeated; the preceding 253-test PostgreSQL result remains historical evidence.

Mac clarification: this Apple Silicon machine already displays real QR with the earlier temporary `linux/amd64` runtime override. Stock team startup still needs Andy's Apple Silicon support. The stopped-session adapter issue is separate from OS compatibility. The earlier phone error `Can't link new devices right now` does not establish a Mac or account cause, and successful real phone linking remains unverified. Native Windows runtime acceptance is still pending.

## Replay corrections and frontend user guide: 2026-10-08

At the user's request, fetched upstream first and fast-forwarded local main and `Kyrie_Frontend` to `d31aa7d`, including merged PR #4 and Lena's task-title PR #5. Local D changes were preserved. This batch changes only eight frontend files and four D-specific English/Chinese documents. Andy/B/C backend, WAHA, infrastructure, migrations, shared contracts/generated types, dependency locks and shared progress documents have no local modifications. The user authorized a local commit with the supplied message, with no push or merge.

Replay now separates login/logout from data refresh, clears account data on expiry, discards superseded/unmounted reads, loads every cursor page and prevents writes against stale data or while another write is unresolved. Network/HTML error responses have readable guidance; recovery clears old errors. Rejected versions require fresh review, and uncertain writes are never automatically retried. The fixed replay inputs are enabled only for merchant's fictional fixture; duplicates have a distinct notice. Confirmed, conflicted and invalidated proposals have appropriate text and disabled controls. Source links, revision/time labels, task deadlines, calendar ownership labels and empty-state guidance make the displayed scope explicit. The [frontend user guide](role-d-frontend-user-guide.md) documents modes, startup, exact controls, expected replay outcomes and remaining limits in both languages.

Actual evidence on updated main:

- **32 frontend Node tests passed** (14 existing bridge/state tests and 18 new replay/API regressions). Coverage includes delayed reads, logout/expiry, stale snapshots, pagination, fixed-target/duplicate input, concurrent clicks, version rejection and unknown write outcomes. Production build runs these regressions before TypeScript and Vite.
- Frontend generated-API check, formatting, TypeScript and production build passed. Generated-contract export check, repository baseline and the documented backend Ruff check/format passed without editing shared sources.
- **18 backend workflow tests passed against PostgreSQL** using disposable isolated schemas on the separate review database. One existing Starlette/httpx deprecation warning remains. This is a focused workflow run, not a new full-suite or live WAHA verification.
- Browser operation against the separate review stack passed: target selection, 15:00 conflict blocking, duplicate input, 16:30 proposal, source link, confirmation to version 4, calendar/task synchronization, correct confirmed text, login/logout and wrong-password guidance. The new task title was `10/08 15:30 准备 16:30 的虚构业务预约`, with a 15:30 deadline; existing seeded task titles were preserved. The other account retained only its own version 3 data and could not replay merchant's fixture.
- Stopping only the review API produced a readable stale-data warning and disabled replay controls; restart/read cleared the warning. Expiring only review login sessions removed cached orders and returned to login. No original replay data was reset and no WhatsApp session was altered. Screenshots contain fictional data only and remain Git-ignored.

Replay still needs independent review: a multi-conversation order displays only its first linked conversation; several read APIs do not form one atomic database snapshot; worker failure/queue diagnosis, sample reset, message editing/revocation and general AI input have no complete UI. Backend checks remain authoritative for versions, authorization, sources and conflicts. These limitations are documented, not bypassed through shared backend changes. Real phone linking, product chat/authorization APIs, automatic replies/sending and native Windows verification remain pending. Do not merge this batch yet.
