# WAHA local product setup API: delivery and unified acceptance

2026-10-09 review fixes: PUT /chats checks login, ownership, CSRF, choices and control_version. Keeping or reducing the current allowlist works when private WAHA configuration is missing or mismatched; adding or reauthorizing a conversation still requires valid configuration. Successful withdrawal may return available=false. Discovery preserves unexpired choice IDs and original expiry, updates labels, and keeps valid options from other pages/windows. Expired choices receive new IDs; actual authorization changes still reject stale versions. Refresh setup/chats after saving to obtain persistent selected IDs. No API shape or migration changed.

2026-10-08 extension: [merged integration](role-a-integration-acceptance.md) adds the implemented D screens, recovered-issue review, migration 0006 provider samples and legacy journal adoption. `inspect`/`discover` do not advance control_version. The dated initial scope/evidence below is retained; frontend screens are no longer pending.

Date: 2026-10-07; branch Andy_WAHA_upgrade, based on main 0cd7e3f. [Chinese](../zh/role-a-setup-api-acceptance.md). Scope: backend setup for one privately configured local Core/WEBJS session. No frontend screens, production identity, arbitrary multi-merchant/session provisioning, AI, history import, sending or Cloud API.

## Delivered architecture

The operator still bootstraps a developer-owned installation with team init/up (or the legacy runbook). Browser login identifies a local application account; private config and database ownership identify its one connection. The browser cannot provide server credentials, provider URLs, session names or account ownership. All control mutations require session/CSRF, origin validation, expected control_version and owner checks; HTTP success follows transaction commit. Read-only authentication no longer takes the account mutation lock, allowing private QR reads without blocking inbound content for the whole provider request.

Migration 0005_waha_controls preserves old data and adds control_version, durable WahaControl intent/leases and expiring WahaCandidate metadata. Control operations run in the separate worker, alongside the existing content queue, but never as AI/business jobs. API queues intent and returns 202 without performing a provider write. Request keys are unique within the owned connection; replaying the same key/body returns the same operation, not another remote call. Each connection allows one active control intent. Pending intents expire after two minutes; running leases expire after two minutes into result_unknown, never automatic write retry. Lease tokens prevent a superseded worker from finalizing reconciliation. PostgreSQL control locks/statements have 3/5-second limits.

## Implemented endpoints for D

Prefix: `/api/v1/connectors/{connection_id}`. Obtain the application UUID from authenticated GET /api/v1/connectors. Use the generated types in api.d.ts; never expose provider credentials or call WAHA directly from the frontend.

| Method/path | Input/result |
| --- | --- |
| GET /setup | WahaSetup: control_version, enabled, config availability, sampled provider state/time/staleness, active/last operation UUID |
| POST /operations | WahaControlCommand + Idempotency-Key; action connect/recover/inspect/discover; returns 202 WahaControlResult |
| GET /operations/{operation_id} | Owner-scoped operation status; only safe code/state metadata |
| POST /operations/{operation_id}/reconcile | WahaVersionCommand; explicit read-only provider check for result_unknown, not a resend |
| GET /qr | Owner-only PNG while enabled and waiting for QR; no-store, nosniff, no file/log persistence; pairing material is transient |
| GET /chats | Selected opaque chat UUIDs and unexpired discovery UUIDs/labels; no provider chat IDs |
| PUT /chats | WahaSelectionCommand: expected_version, selected_ids, consent=true; replaces authorized set without resuming paused reception |
| POST /pause, /resume | WahaVersionCommand; pause is local durable denial, resume explicit; neither deletes sessions nor clears gap review |
| POST /recovery-issues/review | WahaIssueReviewCommand; explicit no-import acknowledgement of recovered owned issues, atomic and audit-preserving |

Example mutation bodies:

```json
{"action":"connect","expected_version":1}
```

```json
{"expected_version":2,"selected_ids":[],"consent":true}
```

These versions are examples, not constants. Always GET setup before a new user intention. Keep one stable request key for retries of the SAME POST /operations body; do not generate another key after a lost response. A changed intention needs a new key and current version. A succeeded operation returns its accepted snapshot version; GET setup gives current version. Local resume/selection use compare-and-set: stale retries return WAHA_SETUP_VERSION_CONFLICT, prompting a read rather than blindly applying old choices.

### UI sequence

Login → GET connectors/setup → resume explicitly if paused → POST connect → poll operation. A new session is created with the signed business webhook directly. An existing correctly configured session is inspected without overwriting its callback; a mismatched probe/other callback requires the operator to verify/configure it. Connect success means the control operation completed, not WhatsApp is ready. If sampled provider state is SCAN_QR_CODE, fetch/display the PNG transiently; revoke any object URL after use. Do not include pairing material in analytics, screenshots or shared fixtures. If STARTING, poll an inspect intent/status; if FAILED/STOPPED, explicit recover can restart the trusted session. A stale sample must not be displayed as current connectivity; use ConnectorStatus pipeline_ready for sampled end-to-end readiness.

After WORKING: POST discover → poll → GET chats → explicit consent/selection → PUT chats. Discovery reads at most 100 recent chats; this is not an exhaustive catalog. Choices expire in ten minutes and are owner/connection scoped. Expired/foreign/duplicate IDs fail without changing authorization. Newly discovered names/IDs are limited private contact metadata, not message content. Candidate data is purged by hourly maintenance after expiry. Selected entries use persistent application UUIDs and generic labels; provider IDs remain server-side.

After PUT, refresh setup and chats to obtain persistent selected UUIDs rather than retaining expiring discovery IDs. Selected entries use a matching unexpired discovery label when available, otherwise a generic label; rediscover to refresh names. Render labels as untrusted plain text, not HTML. QR performs a post-fetch authorization/version recheck; a pause/config change during provider fetching suppresses the image. WAHA_NOT_WAITING_FOR_QR returns 409 so the UI refreshes state instead of treating a non-QR session as a failed image.

Removing authorization advances conversation context so old proposals remain stale even if the chat is reauthorized. Queued content jobs still check current consent/version. CLI provision/pause also advance control_version; provision additionally advances changed conversation context. Browser selection is authoritative in the database and does not rewrite host config: later CLI provision intentionally replaces it from host allowlisted_chats. Do not mix browser and CLI authorization changes casually. Up/restart preserves current database authorization and pause state.

## Unknown results and operational limits

result_unknown blocks another active provider command. Explicit reconcile schedules GET-only verification: connect/recover requires the expected signed business callback; recovery still FAILED/STOPPED remains unresolved. Uncertain discover can finish failed with WAHA_DISCOVERY_REISSUE_REQUIRED, allowing a new explicit read request. This is conservative: ambiguous provider errors can require operator review even when no write occurred. There is no arbitrary abandon/resend endpoint. Existing mismatched remote callbacks are never silently adopted. An interrupted final database write leaves the running lease to become unknown. Pause does not promise to undo an already initiated remote operation; business reception remains denied. Review of setup outcomes is separate from historical recovery-issues; no issue is auto-acknowledged.

Errors include WAHA_CONTROL_DISABLED/CONFIG_INVALID (operator setup), CONNECTOR_PAUSED, WAHA_SETUP_VERSION_CONFLICT, INVALID_IDEMPOTENCY_KEY/IDEMPOTENCY_CONFLICT, CHAT_CHOICE_EXPIRED_OR_UNAVAILABLE, WAHA_OPERATION_NEEDS_RECONCILIATION and safe provider codes. Controllers are development-only; production rate limiting, secret rotation and multi-instance scheduling remain future work. One unknown intent may hold up the local session's queue; other business jobs continue.

## Deployment and verification

Upgrade database to head before rebuilding API/worker. The ingress Compose supplies WAHA_CONTROL_CONFIG and WAHA_CONNECTOR_CONFIG through read-only private volumes to both services; internal provider target remains fixed. Existing host development can set the private file paths and leave WAHA_CONTROL_INTERNAL unset; no credentials are passed to the browser. Team up migrates/rebuilds automatically; no new account or QR is required for an already paired session.

```powershell
.venv\Scripts\python.exe scripts/check_waha_setup.py --run --suite
```

This refuses existing gigmate-waha-setup-check resources, runs disposable PostgreSQL 17.9 on 16432, actual API/worker on 18802 and a synthetic provider on 18800. It creates no real WhatsApp connection, QR or message; safe fake pairing bytes only test HTTP handling. It tests durable connect/idempotence, QR ownership/cache, discovery/selection/versioning, pause/resume, worker restart and cross-account denial, then optionally all PostgreSQL tests. Finally it stops only its child processes and removes only its disposable Compose resources. Do not confuse this with an independent real-account acceptance.

Independent manual gate: on a consenting test account, verify setup/inspect, scan if required, discover/select the correct chat, new/edit/revoke text, remove authorization, pause/resume and restart. Record IDs as opaque application IDs only; no real chats/keys/QR in tracked files. E reviews transaction/concurrency/unknown-result cases, D builds screens using these routes, B/C retain their existing live-processing/approval boundaries. Current environment evidence and blocked real-account checks are in implementation-status.md.

### This operator's prepared manual environment — 2026-10-07

Committed snapshot cf14815 (not pushed). The original database/session volumes were preserved; ignored `local-data/waha-a02/database-port-override.yaml` maps the existing database to 16433 because Windows reserved 54329. Migration to 0005 and Alembic check completed, API/worker/monitor rebuilt on 18702 with the internal database address on 16433. Existing provider recovered WORKING with matching business webhook. Set host DATABASE_URL to the original gigmate_waha_a03 database on 16433; future Compose recreation must keep the ignored database override and WAHA_DATABASE_URL internal port 16433. Team-new-install defaults are unchanged.

I ran 273 PostgreSQL tests and the six disposable HTTP/worker workflow checks plus cleanup. On the real local account: seven HTTP checks, setup/config availability, inspect, discover (87 private choices), duplicate-key consistency, CSRF denial and cross-account denial passed. Existing-session connect inspected successfully without replacing its callback. No message sent, QR fetched, allowlist changed, pause applied or incident acknowledged by the automatic real-account checks.

For this machine only, an ignored local client `local-data/waha-a02/manual_setup_cf14815.py` is prepared for the remaining steps; it calls the committed HTTP protocol as a development user, not WAHA administration. It is not part of the repository/teammate installation. Commands use `.venv/Scripts/python.exe` on Windows. First set DATABASE_URL to localhost:16433/gigmate_waha_a03 as above for database tools.

1. `manual_setup_cf14815.py discover`: view private names/opaque IDs locally. If the test chat is already selected, keep it. Otherwise run `select --choice <opaque UUID>`, confirm YES; other selected chats are preserved. Never share the contacts list.
2. `waha_team.py checkpoint`, then on the phone send a NEW text, edit it once and delete it for everyone. Run `waha_ingress.py status` after each; then `waha_team.py verify` must report mutation_sequence_verified=true. This is the phone work automation cannot do.
3. `manual_setup_cf14815.py pause`, send another test text and check enabled=false/pipeline_ready=false; last content sync must not advance from this text and rejection should be CONSENT_REVOKED. Keep paused long enough for the configured bounded callback retries to finish, then `resume`; send a NEW text and confirm fresh reception. Resume does not guarantee importing paused messages.
4. For removal testing, refresh `status`, use the current selected persistent opaque UUID with `remove --choice ...`, confirm YES, send a test and expect CONVERSATION_NOT_ALLOWED without a new content sync. Rediscover/reselect to restore authorization; discovered handles change after expiry. Do not run CLI provision during this API test, as host allowlists are a separate source.
5. Do not force logout to test QR on the paired WORKING account. Only if the account naturally waits for SCAN_QR_CODE: `connect`, then `qr`; open the private path printed locally and scan, then `inspect`. No QR/credentials/screenshots need to be pasted into chat. A timed-out POST has a saved request key/body; use `retry`, not a new key. result_unknown stops the test for explicit reconciliation.
