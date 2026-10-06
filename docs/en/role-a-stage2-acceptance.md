# A-02 local connection tools and acceptance

Date: 2026-10-02. Branch: Andy_WAHA. A-01 was committed as `908855f` at the user's request. This batch implements the independent local capability portion of [A-02](role-a-development-roadmap.md); authorized account pairing and basic live event/history checks have now succeeded. See the [Chinese record](../zh/role-a-stage2-acceptance.md).

The user authorized an account test and scanned personally. Changes are limited to new files and Role A documents created in this conversation. Shared API, ingestion, database, worker, contracts, migrations, dependencies, frontend and global progress records were not edited. This record substitutes for the shared status files under that restriction. The user requested a stage-two commit; no push is authorized.

## Delivered behavior

| File | Responsibility |
| --- | --- |
| [waha_client.py](../../apps/backend/src/gigmate/waha_client.py) | Local server-side API client: create session, read sanitized status, obtain PNG QR, count bounded allowlisted history |
| [waha_probe.py](../../apps/backend/src/gigmate/waha_probe.py) | Independent raw-body HMAC verification, consent/session/chat checks, bounded volatile metadata and duplicate/conflict observations |
| [waha_local.py](../../scripts/waha_local.py) | Private initialization and local operational commands; no credentials or QR bytes printed |
| [smoke_waha_local.py](../../scripts/smoke_waha_local.py) | Nine real HTTP checks with synthetic inputs |
| [test_waha_local.py](../../apps/backend/tests/test_waha_local.py) | 45 tests for authentication, shape, isolation, limits, QR/status/history and uncertain request results |
| [waha.compose.yaml](../../infra/waha.compose.yaml) / [Dockerfile](../../infra/waha-probe.Dockerfile) | Separate local deployment, loopback ports and private Docker session volume |

WAHA is pinned to Core `2026.9.1`, WEBJS, image digest `sha256:41283bd89922ec3f722e5a772b844c451634d4aa72e9c34043c3480184f970fe`. The probe uses the existing backend dependency lock. It does not expose the product API or alter generated OpenAPI.

## Architecture and boundaries

The local CLI reads ignored secrets and calls WAHA on `127.0.0.1:18700`. WAHA signs callbacks and sends them to the separate probe over the Compose network. Probe port `18701` is also published only on loopback. QR is written privately for the user to open; linking the device changes the user's WhatsApp device authorization.

The probe authenticates the raw bytes before decoding JSON, resolves the configured single session, then checks the chat allowlist before retaining observations. It stores no chat bodies, message identifiers or normalized business events. The last 100 identities are represented by keyed hashes; counters and field-presence flags are memory only. Restart loses them. HTTP 200 explicitly returns `durable_acceptance: false` and `X-GigMate-Probe-Only: true`; it acknowledges an observation, not durable business ingestion. Callback timestamps are not included in WAHA's documented body HMAC, so timestamp headers are not used as authenticated freshness proof. Volatile dedup is not durable replay protection.

The default allowlist is empty. Session notifications are observable; every business chat notification is rejected. History requires an explicitly allowlisted chat and WORKING state, disables media download, and returns a count only. Available records are not a promise of full historical recovery. The local account UUID is a test binding, not production login or multi-user ownership resolution.

No sending, AI, approvals, business writes, persistent job queue or database connection state is implemented here. A-01 remains a synthetic adapter; observing one live status does not prove compatibility of edit/revoke/ACK identities or all event payloads. Live business integration and A-03 persistence require separately authorized changes to shared modules.

## Start and scan on Windows

Run from the repository root with Docker Desktop's Linux engine running:

```powershell
# Only on a fresh setup; refuses to overwrite existing secrets:
.venv\Scripts\python.exe scripts/waha_local.py init
.venv\Scripts\python.exe scripts/waha_local.py sync-container-config
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml up --build -d --wait
# Only when no default session exists; inspect status before retrying:
.venv\Scripts\python.exe scripts/waha_local.py create
.venv\Scripts\python.exe scripts/waha_local.py status
# When status is SCAN_QR_CODE:
.venv\Scripts\python.exe scripts/waha_local.py qr
```

On this machine initialization and creation are already complete. Open `local-data/waha-a02/qr.png`, then use WhatsApp > Linked devices > Link a device. Refresh the QR command and reopen the file if it expires. Do not send the QR, credentials, session profile or conversations into chat or commit them. No dashboard is exposed. The user may need to complete additional phone-side authentication. Scan completion is verified by:

```powershell
.venv\Scripts\python.exe scripts/waha_local.py status
.venv\Scripts\python.exe scripts/waha_local.py observations
.venv\Scripts\python.exe scripts/smoke_waha_local.py
```

Expected status is `WORKING` and `connected: true`; API/container health alone does not prove connection. Status output omits profile, configuration and credentials. Callback observations show only safe counts and field-presence flags.

For a deliberately authorized test conversation, prefer the local selector below. Alternatively edit only ignored `local-data/waha-a02/config.json`: add its known provider chat identifier to `allowlisted_chats`. Do not collect unrelated message history. Restart the probe to load that setting:

```powershell
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml restart probe
.venv\Scripts\python.exe scripts/waha_local.py history --chat '<authorized-provider-chat-id>' --limit 10 --offset 0
```

Use only a consenting test conversation. Send/edit/revoke a synthetic text from the phone, and inspect safe observations. Never paste live payloads into tracked fixtures. The probe only reports structural flags; exact identity/revision mapping still needs a future private validation workflow. Removing the chat and restarting the probe revokes its local observation access.

## Operation and recovery

### Select actual chat IDs locally

At the user's request, metadata discovery is now authorized separately from business-content ingestion. Run:

```powershell
.venv\Scripts\python.exe scripts/waha_local.py select-chats --limit 20
```

The local terminal displays numbered names and canonical IDs for recent direct/group chats. Enter `1,3` to add those rows; Enter cancels. It merges into the existing allowlist, preserves credentials/settings, writes atomically and rejects a detected intervening config edit. It does not restart the probe automatically. Run the printed Compose restart command after saving. For the next page use `--limit 20 --offset 20`; these are separate live queries, not a frozen complete snapshot. Select only conversations authorized for this test. Keep this private terminal output out of model contexts and tracked files.

The [WAHA chat list API](https://waha.devlike.pro/docs/how-to/chats/) may return additional message fields; the client immediately discards them and exposes only ID/name, without storage or logging. No message history endpoint is called by discovery. The pinned version accepts `conversationTimestamp` rather than the current documentation's `messageTimestamp`; its WEBJS IDs are objects with canonical `_serialized` strings. Both were confirmed against the running server. No phone-number guessing or conversion is performed; @lid IDs are retained. Broadcast/status entries are omitted.

Follow-up evidence: the account is now WORKING and actual bounded discovery produced **20 selectable rows**; only the count was printed during agent verification. No allowlist entry was chosen by the agent. **55 focused tests passed**, including metadata filtering, WEBJS ID extraction, malformed/duplicate IDs, invalid/cancelled selections, atomic merging and concurrent-edit detection. Ruff/format and baseline passed. Full chat-event and history acceptance remains pending the user's selection.

`local-data/waha-a02/config.json`, `.env` and `qr.png` are Git-ignored; config contains the local API/HMAC secrets. Docker volume `gigmate-waha-a02_waha_sessions` contains linked-device credentials and must remain private. Dashboard, Swagger, console QR, apps and media downloads are disabled. Ports bind only to localhost. Local secret files are intended for the current developer machine, not a multi-user deployment.

An initial Windows bind-mounted Chromium profile failed with a browser/profile-lock error. Changing the session directory to a Docker Linux named volume resolved it and reached SCAN_QR_CODE. The old ignored directory was left intact; no user profile was deleted. Named volumes avoid that host filesystem lock issue.

`docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml down` stops the tools while preserving the session volume. Do not add `-v` casually. To unlink an authorized test device, remove it in WhatsApp's Linked devices settings. A saved QR becomes stale and should be refreshed only when status requests a QR. A create timeout yields `WAHA_RESULT_UNKNOWN`: inspect status before any retry; the client never automatically retries a mutation. A 409 may indicate an existing session. Restarts preserve provider session files, but connected restart recovery has not yet been tested after scanning.

## Actual verification and remaining acceptance

Recovery follow-up (2026-10-02): the session subsequently became FAILED, with WAHA reporting that the WhatsApp Web page had closed. The underlying reason for closure is not established. A new `restart` command calls the [documented session restart API](https://waha.devlike.pro/docs/how-to/sessions/) only after observing FAILED or STOPPED, preserving the profile and never logging out/deleting/recreating the session. It rejects recovery on an active connection; uncertain results are not retried. The focused suite now has **48 passing tests**, including recovery, active-connection protection and timeout/no-retry behavior. Use the following sequence if QR retrieval returns WAHA_NOT_WAITING_FOR_QR:

```powershell
.venv\Scripts\python.exe scripts/waha_local.py status
# Only for FAILED / STOPPED:
.venv\Scripts\python.exe scripts/waha_local.py restart
# Wait until STARTING becomes SCAN_QR_CODE, then:
.venv\Scripts\python.exe scripts/waha_local.py status
.venv\Scripts\python.exe scripts/waha_local.py qr
```

If status is WORKING, pairing has completed and a QR is unnecessary. If recovery returns WAHA_RESULT_UNKNOWN, inspect status before another request. Do not repeatedly create the existing session or delete its volume. The original batch evidence below remains historical.

- Docker Engine 28.3.3: pinned image pulled, both services healthy; create succeeded, status reached SCAN_QR_CODE, PNG QR retrieval succeeded. Actual signed WAHA session callbacks reached the probe.
- Nine actual HTTP checks passed: WAHA rejects missing API key; probe health identifies non-durable mode; stats require authorization; wrong HMAC is rejected; signed synthetic observation succeeds; duplicate is recognized; changed content under one identity is rejected; wrong session is rejected; unallowlisted chat is rejected.
- Backend suite: **157 passed, 1 skipped** on SQLite. The PostgreSQL concurrent-claim test was skipped; no PostgreSQL locking claim is made. One existing Starlette/httpx deprecation warning remains.
- Ruff check and format check, generated-contract drift check and repository baseline passed. The new module tests account for 45 of the 157 passing tests.
- Git ignore confirmed for configuration, environment secrets and QR. No shared migration/schema/API/frontend changes; migration and frontend checks are not applicable to this isolated batch.

## Final authorized live evidence and next batch

The user supplied sanitized command outputs confirming WORKING/connected on WEBJS, one allowlisted history query returning four records with complete_history false, message.created, message.revoked with a target field, and message.edited with a target field. The final observation count was six, with zero duplicates and identity conflicts in that volatile window. These are capability observations, not proof of durable ingestion, exact original-message identity mapping or revision correctness. The actual chat ID, names and message contents are intentionally absent from this record. An ACK field on a message is not evidence of a separate message.ack event.

Final commit verification: backend **167 passed, 1 skipped** on SQLite; Ruff check/format, generated-contract check, baseline and nine synthetic real-HTTP smoke checks passed. The PostgreSQL locking test remains skipped and the existing deprecation warning remains. No migration/frontend check applies to this independent batch.

Next milestone combines the remaining A-02 durable-ingress work with core A-03 monitoring: persist trusted account/session/chat/message mappings and message revisions; connect authenticated/allowlisted normalized events to transactional inbox/jobs; preserve duplicate/conflict and edit/revoke semantics across restarts; persist connection state with ordering/freshness and account-scoped status; verify database failures, lost responses, worker crashes and reconnects on PostgreSQL. Separate ACK, provider identity/revision compatibility, disconnect/reconnect and connected restart are still pending. Shared messaging/db/API/contracts/worker integration requires explicit permission under the user's file restriction; new migrations must be versioned. AI/sending is outside this milestone. Complete related implementation and checks as one batch, then conduct unified acceptance with E.
