# A-03 durable ingress, monitoring and unified acceptance

Date: 2026-10-02. Baseline: stage-two commit `016a679`, branch Andy_WAHA. The user explicitly authorized shared-module edits. This batch completes durable WAHA reception and core monitoring, with independent worker processing. [Chinese record](../zh/role-a-stage3-acceptance.md).

## Delivered behavior

- New versioned migration `0002_waha_ingress`, preserving `0001`: three tables for account-owned sessions, allowlisted chat/conversation mappings and canonical message/revision mappings; Inbox gains an optional connection FK/index. No credentials are stored in these tables.
- [Ingress service](../../apps/backend/src/gigmate/waha_ingress.py) and `POST /api/v1/connectors/waha/{connection_id}/events`: raw-body SHA-512 HMAC, strict bounded JSON, private server binding, active account/connector and conversation allowlist checks before content storage. Inbox/message/revision/context/job/mapping changes commit together. Function-scoped transaction teardown completes before HTTP success. Database failures return safe 503, never durable success.
- Receipt identity includes instance/account/session/provider event ID. Receipt-time changes do not alter semantic digest. Repeated receipts and creation aliases create no extra content revisions/jobs; reusing identity with changed normalized meaning is rejected. Old receipts still deduplicate after a newer edit/revoke.
- Edit/revoke targets resolve through stored originals. Revision allocation is serialized and advances local accepted revisions; earlier/equal mutation timestamps, unknown originals, changes after revocation and conflicting identities require rejection/reconciliation. Missing remote revisions cannot be inferred; this is not complete historical reconstruction.
- ACK receipts persist independently, update a monotonic delivery rank, and do not advance content/context or create extraction jobs. Error/unsupported ACK requires reconciliation. ACK is not customer confirmation or evidence of an approved send.
- Session state persists and ignores older notifications; conflicting equal timestamps require reconciliation. [Status contract](../../apps/backend/src/gigmate/contracts.py) and authenticated `GET /api/v1/connectors` expose state/freshness, last accepted content sync, receipt/duplicate/stale counters and pending/processing/failed job counts, scoped to the signed-in account, without credentials or provider chat identifiers. Existing Replay status and Replay routes remain compatible.
- [Operator CLI](../../scripts/waha_ingress.py) synchronizes explicitly chosen chats, pauses ingress, polls trusted status, configures the business callback and purges expired content. Provisioning creates separate conversations without guessing work-order assignment. Removed selections revoke database allowlists on reprovisioning; it never resets existing messages.
- [Compose extension](../../infra/waha-ingress.compose.yaml) adds API on loopback `18702`, worker and a monitor that polls every 30 seconds. It uses dedicated database `gigmate_waha_a03` on the local PostgreSQL server. Provider sessions and the legacy Replay database are separate. Monitoring failure does not fabricate state; observations older than 120 seconds are marked stale and not live-connected. This is a conservative configured window, not an uptime guarantee.
- Worker rechecks connector/account/conversation authorization, recovers expired leases, and prevents an expired owner from finishing. Real content bypasses fictional extraction, completes with LIVE_EXTRACTION_PENDING, and creates no proposals or formal writes. No AI/sending/outbox was added.
- Worker startup/hourly maintenance and operator purge remove Inbox/jobs older than 30 days and scrub old revision text while retaining identity/revision/source metadata. Events beyond this window are rejected, preventing old content from being reintroduced by retries. Purge also covers paused connections. Full account deletion/backup removal remains outside this batch.

Generated domain/OpenAPI/frontend types were regenerated from source. The event wire remains 0.1.0; no event schema was manually edited. Existing API message timelines expose latest stored revisions; owned WAHA conversation details use their actual provider chat ID.

## Local operation

The current machine is provisioned and business callbacks are configured. No need to create/pair again. Future fresh setup requires the stage-two private config/selected chats, local PostgreSQL, a dedicated database, then:

```powershell
$env:PYTHONPATH = 'apps/backend/src'
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:54329/gigmate_waha_a03'
# Database must already exist. Development bootstrap is idempotent:
.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv\Scripts\python.exe -m gigmate.seed
.venv\Scripts\python.exe scripts/waha_ingress.py provision
.venv\Scripts\python.exe scripts/waha_ingress.py sync-container-config
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml -f infra/waha-ingress.compose.yaml up --build -d --wait ingress ingress-worker ingress-monitor
# Changes provider callback configuration and may restart its session:
.venv\Scripts\python.exe scripts/waha_ingress.py configure-live
.venv\Scripts\python.exe scripts/waha_ingress.py reconcile
.venv\Scripts\python.exe scripts/waha_ingress.py status
.venv\Scripts\python.exe scripts/smoke_waha_ingress.py
```

Current runtime configuration uses private Docker volumes; synchronize host changes before restarting services. See [recovery workflow](role-a-recovery-acceptance.md).

`local-data/waha-a02/bindings/ingress.json` is the ignored private server binding. API mounts it read-only through WAHA_CONNECTOR_CONFIG; ingress is disabled without that configuration. Credentials/QR/profiles remain local/private. Development accounts/password and PostgreSQL credentials are only for this loopback test environment, not production authentication. The CLI's instance/account/session mapping must match the actual connected provider. Never copy real profiles into fixtures or enable an unrelated account's connection.

Changing the selected chats now requires `select-chats`, then `waha_ingress.py provision` against this database. Restarting only the old probe does not update durable authorization. To stop reception immediately run `waha_ingress.py pause`; in-flight work is serialized and future requests/jobs are rejected/cancelled. Editing the private consent flag alone is not a substitute for pausing the authoritative database connection. Rotating/replacing the mounted binding requires restarting ingress/monitor and updating the provider HMAC configuration.

For live acceptance, send a **new synthetic text after callback configuration** in the chosen consenting conversation, then edit/revoke that same text. Check `waha_ingress.py status`; accepted and last_sync_at should advance, worker backlog should clear without proposals. Existing phone history was not imported, so mutating an old unreceived message returns SOURCE_MESSAGE_UNRESOLVED. Normal old `observations` output belongs to the volatile capability probe, which no longer receives the business subscriptions.

`configure-live` and all provider mutations are not automatically retried after an uncertain result. Inspect provider/database state first. Failed source/order cases require manual reconciliation, not fabricated originals or blind history import. Callback retries are bounded by the provider configuration; prolonged outages may lose notifications. Available-history counts do not guarantee backfill. Connected-session config restart recovered WORKING without rescanning; broader network outage/logout recovery is still pending independent live acceptance.

## Live target-format correction

The first live text persisted and its worker job completed without extraction. Subsequent edit/revoke callbacks returned SOURCE_MESSAGE_UNRESOLVED: the adapter compared the short target with the stored serialized message ID. [WAHA's event documentation](https://github.com/devlikeapro/waha-docs/blob/main/content/docs/how-to/events/index.md) specifies that editedMessageId/revokedMessageId omit the chat ID.

Versioned migration `0003_waha_stanza_identity` adds an indexed short-ID mapping and backfills recognized existing serialized IDs, preserving earlier migrations. Lookup remains scoped to the authorized chat, account, conversation and original direction; ambiguous targets return SOURCE_MESSAGE_AMBIGUOUS. Revisions retain the canonical full ID and original internal message UUID. The existing local original mapping was backfilled; no real identifiers or content are recorded here.

The rebuilt API/worker/monitor is running. PostgreSQL full suite: **203 passed**; SQLite: **201 passed, 2 skipped**. Added tests cover short edit/revoke targets, late duplicate receipts, direction mismatch and ambiguous group targets. Six HTTP smoke checks pass. Live status remains connected/fresh with three accepted receipts and no pending/processing/failed jobs. This does not prove live edit/revoke acceptance yet. Repeat with a new consenting test text, then edit and revoke it, checking status after each action. Previously rejected callbacks were not stored; automatic recovery is not promised.

## Follow-up live receipt evidence

The user's follow-up status reached five accepted receipts. A read-only metadata check confirmed two session-state receipts, two creations and one ACK; both stored messages remain at revision 1 and are not revoked. The additional creation and independent ACK persisted with no queue backlog or failure. These counts do not establish edit/revoke acceptance. Recent callback diagnostics contain no new edit/revoke failure; the earlier unresolved target was an ACK at 08:33 UTC. No message bodies, provider identifiers or credentials were read into diagnostic output.

## Follow-up API stall correction

The user confirmed that creation, editing and revocation had all been performed. Missing persisted mutations therefore cannot be attributed to missing user actions. Inspection found the ingress API unhealthy, health/HTTP smoke timing out, a transaction idle while holding locks, and two database lock waiters. The async webhook handler was running synchronous, potentially lock-blocked reception on its event loop; another request could prevent the earlier request's transaction teardown from being scheduled.

Reception now runs via `run_in_threadpool`, preserving function-scoped commit-before-success. A new regression test holds reception while requesting health on the same ASGI event loop and verifies responsiveness. PostgreSQL full suite: **204 passed**; SQLite ingress subset: **33 passed, 1 skipped**; Ruff check/format and export checks pass. After rebuild/restart, API health and six HTTP smoke checks pass, lock waiters are zero, and monitoring resumes with fresh observations. Five receipts remain durable, with no job backlog/failure. No schema or frontend behavior changed in this correction; their previous checks remain historical. Live edit/revoke acceptance still requires a fresh test because aborted/uncommitted callbacks cannot be treated as persisted or automatically recovered.

## Successful live create/edit/revoke verification

At 09:18 UTC on 2026-10-02, the user's three sequential actions advanced accepted receipts **6 → 7 → 8**, with last_sync_at updating each time and pending/processing/failed jobs all zero. Read-only metadata confirmed one new creation, one edit at revision 2 and one revocation at revision 3, all sharing the same internal message identity and canonical provider identity. Latest stored revision is revoked. Total receipts: two session-state events, three creations, one ACK, one edit and one revocation. Database lock waiters remain zero; six HTTP smoke checks pass. No real content or provider identifiers were output. This validates the local pinned WEBJS text mutation path; independent E review, network outage recovery and other previously listed limits remain pending. Earlier statements of pending text mutation verification above describe evidence before this successful run. No commit/push.

## Actual checks and remaining limits

Final automated results and restart evidence are recorded with the shared [implementation status](implementation-status.md). Tests cover signatures, ownership/allowlists, receipt conflicts/duplicates, normal/edit/revoke ordering, independent ACK, rollback/lost response, commit failure, expired leases, worker authorization, state freshness/poll races, retention, provision revocation, PostgreSQL concurrent reception and migration preservation/downgrade on disposable SQLite. Both PostgreSQL and SQLite suites are run; only PostgreSQL demonstrates row-lock behavior.

Runtime evidence: dedicated database migrated/seeded/provisioned; trusted provider poll reported WORKING; provider callback reconfiguration emitted STARTING then WORKING through HMAC-authenticated HTTP into persistent Inbox; two status receipts accepted without jobs. Local API health/auth/signature/status/logout smoke uses no real message content. API/worker/monitor restart preserves receipt/mapping/state. Frontend generated-type/format/build checks pass; its full live-connector UI remains D's follow-up.

This batch is ready for one unified review with E, not a claim that E independently accepted it. Remaining live checks: fresh text/edit/revoke through durable storage, separate ACK, complete provider-target compatibility and network disconnection recovery. Production auth/secrets management, general extraction, work-order assignment UI, approved external execution/outbox/reconciliation, full history recovery, media and full deletion remain pending. No automatic commit or push.
