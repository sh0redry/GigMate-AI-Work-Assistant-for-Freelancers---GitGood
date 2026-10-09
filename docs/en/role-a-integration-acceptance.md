# WAHA and extraction integration after PR #4, #5 and #9

2026-10-08 · Andy_WAHA_upgrade · main d31aa7d merged at 20611ce. [Chinese](../zh/role-a-integration-acceptance.md).

2026-10-09 update: main d6e70eb (PR #9) merged at f166084; prior integration checkpoint committed as **0e22486**. The following follow-up joins migrations and fixes Windows test compatibility. It does not introduce a real-model provider.

This batch connects D's workspace to A's durable backend and preserves C's task-title feature. It does not implement general AI extraction, sending, complete history import, production onboarding or Cloud API. Earlier acceptance documents retain their dated evidence; this document governs current integration.

## One control path

The browser now calls authenticated `/api/v1` routes for setup, queued connect/recover/inspect/discover, private QR, chat authorization, pause/resume and explicit unknown-result reconciliation. The Vite/Python local-pairing bridge and its separate restart journal are retired. Vite only proxies the backend; `GIGMATE_LOCAL_PAIRING` is unnecessary. Provider secrets and raw chat IDs remain server-side. Login/CSRF/ownership, version checks and explicit consent apply to every relevant mutation.

`inspect` and `discover` hold the current control-version snapshot without incrementing it. Connect/recover and authorization changes advance the version. Polling therefore cannot invalidate a chat selection merely by reading status. After discovery/save, reread setup/chats for current versions and persistent selected UUIDs. A lost operation response preserves the exact body/version/key; pending and unknown intents block another provider command. Reconciliation performs GET-only verification, never blind restart.

Migration `0006_waha_provider_sample` adds raw provider state/sample time alongside normalized connection health. Control reads and signed callbacks update it without allowing an older provider lookup to overwrite a newer callback. Provider connectivity, reception permission, sample freshness and pipeline readiness remain separate UI signals. Pause hides QR and denies reception; resume restores existing choices explicitly.

A STOPPED WEBJS session may omit runtime engine metadata. In that case only, the adapter verifies `/api/server/version` is exactly pinned Core 2026.9.1/WEBJS before accepting the sample. Wrong engines/versions and active sessions missing metadata still fail. This avoids both the former false incompatibility and blindly trusting an unknown installation.

`POST /api/v1/connectors/{id}/recovery-issues/review` takes unique `issue_ids` and `confirmed_no_import: true`. It atomically checks ownership and recovery, records `reviewed_no_import`, and retains history. Mixed active/recovered requests fail without partial acknowledgement. Reviewing is possible while reception is paused; it does not resume, import or delete messages.

## Upgrade existing installations

Current schema head is **0007_merge_waha_extraction**. WAHA `0005_waha_controls → 0006_waha_provider_sample` and B's `0005_extraction_evidence` both descend from 0004; the new merge revision requires both parents. No shared migration was renamed or rewritten. `upgrade head` works from either existing branch and installs the other branch before the single merge point. Do not fix this by stamping a database whose tables were not migrated. Downgrade checks use disposable test databases only.

1. Preserve private configuration, database and WAHA session volumes. Do not use `down -v` on a real installation. Run the existing team `up` workflow to migrate/rebuild. Legacy installations must migrate their own database to head and rebuild API/worker/monitor before using the updated frontend.
2. An old D bridge restart journal in `local-data/d01-operations/restart-{application_connection_uuid}.json` with `submitting` or `unknown` is imported by team startup into a blocking durable unknown operation. The journal is retained and marked migrated. Conflicting active intent or invalid evidence fails clearly. For a legacy installation, set its correct DATABASE_URL and run `python scripts/waha_team.py import-legacy` before opening the page. The command uses the private configured binding; no raw account IDs or secrets are entered in the browser.
3. In `apps/web`, set `GIGMATE_API_URL` to your local ingress API, then `npm run dev`. Typical API is `http://127.0.0.1:18702`; team ports can differ. Use the API origin configured by your installation. Old bridge environment flags and commands are obsolete.
4. Log in as the account bound to this installation. Inspect first; an already WORKING session needs no new scan. If scanning is needed, the user scans locally. Load chats, explicitly save the intended selection, and keep contact names/QR private. CLI provision can replace database authorization from host config; do not mix it with browser selection casually.

For C, task readiness is computed by subtracting one elapsed hour from the UTC schedule instant, then converting that same instant for local title display. New tests cover both New York DST transitions and Hong Kong midnight; the displayed preparation time and stored due instant agree.

For B, accepted live WAHA content now creates durable `proposals`/`model_call_traces` through the default deterministic provider. It still refuses live extraction: `Job.state=completed`, `Job.error_code=EXTRACTION_NEEDS_REVIEW`, no confirmed business change. This is an extraction-review outcome, not failed reception. Old completed jobs are not automatically reprocessed. Edits/revocations retain existing source/context invalidation. Review UI for B's evidence remains future work; connection/gap review does not approve a proposal.

Windows extraction tests now use pytest `tmp_path` files and dispose their engines in `finally`, replacing an open `NamedTemporaryFile` that SQLite could not reopen on Windows. Temporary manifests use the same ownership/cleanup mechanism. The tests remain meaningful on other platforms; their SQLite fixture is not PostgreSQL locking evidence.

## Unified acceptance

The automated runner `python scripts/check_waha_setup.py --run --suite` uses disposable PostgreSQL, actual HTTP API and worker, and a synthetic provider. It preserves durable intent across worker restart, checks ownership/CSRF, QR caching, discovery, version conflicts and pause/resume, then runs the PostgreSQL suite. `--frontend` adds a disposable 30-minute browser environment on 18803. Its one-pixel PNG is a transport fixture, not a scannable WhatsApp QR. Automated fixtures support developer verification; teammates still use their own accounts for live acceptance.

The updated runner also submits an HMAC-authenticated synthetic live-origin message over HTTP: reception and a completed worker job must persist a needs-review proposal/trace with no business change. A paused signed message must be rejected without additional evidence. The evaluation CLI runs all seven synthetic manifest cases and persists results in that disposable PostgreSQL database. Migration tests cover upgrade from 0004, B's existing branch and A's existing branch; they verify retained replay rows, paused connection/counters, A's sample/version and B's evaluation row. With TEST_DATABASE_URL these migration paths use isolated PostgreSQL schemas; otherwise they use disposable SQLite files.

Browser checks in that isolated environment covered discovery and authorization removal/save, pause/resume, STOPPED recovery through the worker, waiting-for-QR display, and explicit unknown-operation reconciliation. Database inspection confirmed one recovered issue reviewed, both audit rows retained, and the unrecovered issue untouched. Frontend tests cover exact request replay, opaque choices, conflicts, no automatic unknown-result retry and canonical backend routes.

Final command counts and limitations are recorded in [implementation status](implementation-status.md). Native Apple Silicon phone pairing, real phone mutations and independent E review are separate acceptance gates, not claims made by these automated checks.

## Team direction and manual gate

A maintains ingestion/control/monitoring; B consumes authorized message revisions for proposals; C confirms internal task/calendar updates with provenance; D builds on generated API types; E independently reviews ownership, concurrency, stale context and unknown outcomes. B/C must not call WAHA or introduce a second authorization source. Provider connection alone does not mean AI processing or sending is implemented.

On each consenting developer's own installation, validate the whole batch once: login and current status → scan only if needed → discover/save the intended test chat → checkpoint → send/edit/delete a new text on the phone → verify → remove chat authorization and confirm denial → restore it explicitly → pause and confirm denial → resume and send a new text. Check status freshness and pipeline health throughout. Review only recovered gaps actually checked; if missing messages need investigation, keep the issue open. For naturally STOPPED/FAILED sessions, explicitly reconnect; for unknown operations, use the reconciliation button. Do not deliberately destroy a paired session to obtain QR evidence. Keep all real content, contact IDs, QR and credentials out of reports.

### Manual checklist after automated checks

1. **Upgrade/start your own installation.** Team-profile installations run `python scripts/waha_team.py up`, then `doctor`; use `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on macOS. Existing legacy installations first set their own DATABASE_URL/PYTHONPATH, run Alembic upgrade head/check, import-legacy, and rebuild ingress/worker/monitor with the existing private Compose environment and correct internal WAHA_DATABASE_URL. Preserve database, private config and session volumes. Never run init over an existing installation. This operator's database-port override remains 16433; new team installs use their own profile port.
2. **Open the live page.** In apps/web set GIGMATE_API_URL to the actual ingress (normally http://127.0.0.1:18702), run npm run dev and open the printed local URL. On Windows: `$env:GIGMATE_API_URL='http://127.0.0.1:18702'`; on macOS: `GIGMATE_API_URL=http://127.0.0.1:18702 npm run dev`. Log in with your local development account. Check freshness and readiness separately. Scan with your phone only if requested; an existing WORKING session needs no new scan. Physical Apple Silicon pairing must be recorded by the teammate.
3. **Save a consenting test chat.** Load conversations, identify it privately by label, select and save explicit permission. Other developers use their own account/chat. Do not publish the contact list.
4. **Test one new text end to end.** From repository root run `python scripts/waha_team.py checkpoint`. Send a NEW text in that chat, query `python scripts/waha_ingress.py status`; edit that same text and query again; delete it for everyone and query again. Allow the worker to finish between actions. Run `python scripts/waha_team.py verify`: require mutation_sequence_verified=true. Accepted can also rise from ACK/status; the verifier proves the actual same-message 1/2/3 revision sequence. A needs-review extraction outcome is expected until real models are implemented.
5. **Check authorization and pause.** In the page remove the test chat and save; send a new text and confirm CONVERSATION_NOT_ALLOWED/no content sync from it. Rediscover and restore explicit authorization. Pause reception, send another new text, expect CONSENT_REVOKED and enabled=false, with no content sync from that text. Wait for bounded callback retries to finish; resume and send a NEW text, confirming fresh reception. Neither restoration nor resume promises importing messages denied during the gap.
6. **Check recovery and audit.** If naturally disconnected, explicitly reconnect; unknown result uses the no-resend reconciliation button. For recovered incidents you actually checked, confirm no history import is needed before reviewing; active incidents remain. Reopen/refresh the page to verify state persists and QR disappears when paused/logged out. Router interruption/WhatsApp logout and missed-content recovery are separate live gates; do not destroy the paired session for this batch.
7. **E's independent review.** Record commit SHA, OS/chip and safe status/verify metadata, separately from A's automated evidence. Review ownership, stale consent/context, migration preservation and unknown outcomes. Do not include real content, contact IDs, QR or credentials. Phone-only actions and peer independence cannot be automated by A.

### This operator's legacy Windows installation: preparation commands

These are specifically for the existing private installation whose original database was mapped to **16433**. Team-profile installations use `waha_team.py up` instead. The password below is the repository's public local development default, not a WhatsApp credential. Preserve the existing database-port override, private .env and named session/config volumes. Do not run provision/init/configure-live merely to upgrade the code: those can replace authorization or callback configuration.

```powershell
# Repository root; start Docker Desktop first.
docker compose --env-file .env.example -f infra/compose.yaml -f local-data/waha-a02/database-port-override.yaml up -d --wait db
$env:PYTHONPATH = 'apps/backend/src'
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:16433/gigmate_waha_a03'
$env:WAHA_DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@host.docker.internal:16433/gigmate_waha_a03'
.venv/Scripts/python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv/Scripts/python.exe -m alembic -c apps/backend/alembic.ini check
.venv/Scripts/python.exe scripts/waha_team.py import-legacy
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml -f infra/waha-ingress.compose.yaml up --build -d --wait ingress ingress-worker ingress-monitor
.venv/Scripts/python.exe scripts/waha_team.py doctor
.venv/Scripts/python.exe scripts/waha_ingress.py status

# In another terminal, from apps/web:
$env:GIGMATE_API_URL = 'http://127.0.0.1:18702'
npm run dev
```

Proceed to phone tests only after doctor is healthy and status is fresh/connected/pipeline_ready=true. Leave historical incidents open until actually reviewed. A naturally stopped or unpaired session can require explicit page connect/reconcile and the user's scan. In each new terminal, keep the same database environment for checkpoint/verify/status; missing DATABASE_URL is a setup error, not an ingress failure.
