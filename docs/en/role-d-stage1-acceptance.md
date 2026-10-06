# D-01: frontend connection and conversation selection

Owner: Kyrie. Prepared on 2026-10-06 on `Kyrie_Frontend`, based on latest `main` merge commit `0cd7e3f`. The user requested a local commit with message `还没测试`; no push. Real WhatsApp pairing and user acceptance have not been tested; the automated checks below have passed. [Chinese counterpart](../zh/role-d-stage1-acceptance.md).

## Scope and current result

This batch changes only frontend files in `apps/web` and this pair of D-specific acceptance documents. Backend, WAHA tools, migrations, infrastructure, dependencies, shared documentation, contracts and generated types are identical to main. Earlier uncommitted D-01 backend/shared changes were backed up privately under ignored `local-data` and removed from the active changes.

The desktop workspace provides a pairing area, connection/processing health, conversation checkboxes, explicit save, revoke and discard controls, and a clearly marked synthetic preview. Read authorization does not enable automatic replies. Automatic replies and message sending remain separate milestones.

Live mode uses main's existing authenticated connection and recovery-issue queries. It shows connection state, sampled readiness, freshness, receiving permission and unresolved issues separately. Missing pairing and conversation-selection capabilities are visibly pending; the corresponding controls are disabled. The live adapter makes no requests to unimplemented routes or WAHA administration endpoints.

The preview is browser memory only: simulated scan, connect/disconnect, stale status, selection, saving and offline revocation. Leaving the preview or reloading resets it. The QR area is a placeholder, not a scannable QR. Preview success does not prove database writes, real authorization, pairing or delivery.

**End-to-end D-01 acceptance is pending Andy's authenticated product APIs and real-account testing.** This frontend batch does not implement those APIs.

## Interfaces to agree with Andy

Already implemented in main and used by live mode:

| Query | Frontend use |
| --- | --- |
| `GET /api/v1/connectors` | Account-scoped, paginated `ConnectorStatus`; use generated main types |
| `GET /api/v1/connectors/{id}/recovery-issues` | Account-scoped, paginated `RecoveryIssue`; use generated main types |

The following routes and shapes are **frontend proposals only**. Andy should confirm or replace them before implementation. They are not additions to the shared contract or evidence of implemented routes.

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

## macOS preview and existing API

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

Pending external verification: Docker/WAHA phone pairing, live chat discovery, persistent save/revoke, PostgreSQL behavior and independent teammate review. Neither synthetic preview nor a SQLite development login proves these.
