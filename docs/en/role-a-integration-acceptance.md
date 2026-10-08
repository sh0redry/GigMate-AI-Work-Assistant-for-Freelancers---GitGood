# WAHA integration after PR #4 and #5

2026-10-08 · Andy_WAHA_upgrade · main d31aa7d merged at 20611ce. [Chinese](../zh/role-a-integration-acceptance.md).

This batch connects D's workspace to A's durable backend and preserves C's task-title feature. It does not implement general AI extraction, sending, complete history import, production onboarding or Cloud API. Earlier acceptance documents retain their dated evidence; this document governs current integration.

## One control path

The browser now calls authenticated `/api/v1` routes for setup, queued connect/recover/inspect/discover, private QR, chat authorization, pause/resume and explicit unknown-result reconciliation. The Vite/Python local-pairing bridge and its separate restart journal are retired. Vite only proxies the backend; `GIGMATE_LOCAL_PAIRING` is unnecessary. Provider secrets and raw chat IDs remain server-side. Login/CSRF/ownership, version checks and explicit consent apply to every relevant mutation.

`inspect` and `discover` hold the current control-version snapshot without incrementing it. Connect/recover and authorization changes advance the version. Polling therefore cannot invalidate a chat selection merely by reading status. After discovery/save, reread setup/chats for current versions and persistent selected UUIDs. A lost operation response preserves the exact body/version/key; pending and unknown intents block another provider command. Reconciliation performs GET-only verification, never blind restart.

Migration `0006_waha_provider_sample` adds raw provider state/sample time alongside normalized connection health. Control reads and signed callbacks update it without allowing an older provider lookup to overwrite a newer callback. Provider connectivity, reception permission, sample freshness and pipeline readiness remain separate UI signals. Pause hides QR and denies reception; resume restores existing choices explicitly.

A STOPPED WEBJS session may omit runtime engine metadata. In that case only, the adapter verifies `/api/server/version` is exactly pinned Core 2026.9.1/WEBJS before accepting the sample. Wrong engines/versions and active sessions missing metadata still fail. This avoids both the former false incompatibility and blindly trusting an unknown installation.

`POST /api/v1/connectors/{id}/recovery-issues/review` takes unique `issue_ids` and `confirmed_no_import: true`. It atomically checks ownership and recovery, records `reviewed_no_import`, and retains history. Mixed active/recovered requests fail without partial acknowledgement. Reviewing is possible while reception is paused; it does not resume, import or delete messages.

## Upgrade existing installations

1. Preserve private configuration, database and WAHA session volumes. Do not use `down -v` on a real installation. Run the existing team `up` workflow to migrate/rebuild. Legacy installations must migrate their own database to head and rebuild API/worker/monitor before using the updated frontend.
2. An old D bridge restart journal in `local-data/d01-operations/restart-{application_connection_uuid}.json` with `submitting` or `unknown` is imported by team startup into a blocking durable unknown operation. The journal is retained and marked migrated. Conflicting active intent or invalid evidence fails clearly. For a legacy installation, set its correct DATABASE_URL and run `python scripts/waha_team.py import-legacy` before opening the page. The command uses the private configured binding; no raw account IDs or secrets are entered in the browser.
3. In `apps/web`, set `GIGMATE_API_URL` to your local ingress API, then `npm run dev`. Typical API is `http://127.0.0.1:18702`; team ports can differ. Use the API origin configured by your installation. Old bridge environment flags and commands are obsolete.
4. Log in as the account bound to this installation. Inspect first; an already WORKING session needs no new scan. If scanning is needed, the user scans locally. Load chats, explicitly save the intended selection, and keep contact names/QR private. CLI provision can replace database authorization from host config; do not mix it with browser selection casually.

For C, task readiness is computed by subtracting one elapsed hour from the UTC schedule instant, then converting that same instant for local title display. New tests cover both New York DST transitions and Hong Kong midnight; the displayed preparation time and stored due instant agree.

## Unified acceptance

The automated runner `python scripts/check_waha_setup.py --run --suite` uses disposable PostgreSQL, actual HTTP API and worker, and a synthetic provider. It preserves durable intent across worker restart, checks ownership/CSRF, QR caching, discovery, version conflicts and pause/resume, then runs the PostgreSQL suite. `--frontend` adds a disposable 30-minute browser environment on 18803. Its one-pixel PNG is a transport fixture, not a scannable WhatsApp QR. Automated fixtures support developer verification; teammates still use their own accounts for live acceptance.

Browser checks in that isolated environment covered discovery and authorization removal/save, pause/resume, STOPPED recovery through the worker, waiting-for-QR display, and explicit unknown-operation reconciliation. Database inspection confirmed one recovered issue reviewed, both audit rows retained, and the unrecovered issue untouched. Frontend tests cover exact request replay, opaque choices, conflicts, no automatic unknown-result retry and canonical backend routes.

Final command counts and limitations are recorded in [implementation status](implementation-status.md). Native Apple Silicon phone pairing, real phone mutations and independent E review are separate acceptance gates, not claims made by these automated checks.

## Team direction and manual gate

A maintains ingestion/control/monitoring; B consumes authorized message revisions for proposals; C confirms internal task/calendar updates with provenance; D builds on generated API types; E independently reviews ownership, concurrency, stale context and unknown outcomes. B/C must not call WAHA or introduce a second authorization source. Provider connection alone does not mean AI processing or sending is implemented.

On each consenting developer's own installation, validate the whole batch once: login and current status → scan only if needed → discover/save the intended test chat → checkpoint → send/edit/delete a new text on the phone → verify → remove chat authorization and confirm denial → restore it explicitly → pause and confirm denial → resume and send a new text. Check status freshness and pipeline health throughout. Review only recovered gaps actually checked; if missing messages need investigation, keep the issue open. For naturally STOPPED/FAILED sessions, explicitly reconnect; for unknown operations, use the reconciliation button. Do not deliberately destroy a paired session to obtain QR evidence. Keep all real content, contact IDs, QR and credentials out of reports.
