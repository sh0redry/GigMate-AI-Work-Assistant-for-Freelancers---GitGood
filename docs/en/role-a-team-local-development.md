# Team local WAHA development and integration framework

2026-10-08: after bootstrapping below, use the [merged integration guide](role-a-integration-acceptance.md) for the implemented browser setup/authorization and legacy journal upgrade. D now uses A's canonical backend; no local-pairing bridge is needed.

Updated: 2026-10-06. [Chinese](../zh/role-a-team-local-development.md). Current capabilities: [handoff](role-a-waha-handoff.md). This batch provides developer tooling, not production onboarding, AI or sending. Cloud API is outside the current plan.

## Environment ownership

Each developer uses their own machine/clone, controlled test number and consenting test chat. Nobody copies Andy's configuration, QR, session or database. The GigMate development login (`merchant` / `demo-only-change-me`) is a separate local application identity; scanning your WhatsApp does not authenticate the browser. These public development credentials are loopback-only, not production identity. WAHA remains an unofficial connector; use a noncritical test number rather than a primary business number.

One installation per machine: fixed project `gigmate-waha-a02`, ports 18700/18701/18702, and separate `gigmate-waha-team` PostgreSQL 17.9 on 54349. Configuration, binding and session volumes belong to that developer. A second clone on the same machine is not isolated merely by its folder: init refuses existing project resources and up requires the originating workspace profile. Multiple machines can use identical port/project names. Multi-instance same-host support is not implemented.

## Clean checkout: own account, no Replay prerequisite

Install Python 3.12.10 and Docker Desktop/Linux engine, start Docker, then from repository root:

### macOS (Intel or Apple Silicon)

Install Python 3.12 and Docker Desktop for your Mac's chip. Host tools are Python scripts, not Windows executables:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r apps/backend/requirements.lock
.venv/bin/python scripts/waha_team.py init
.venv/bin/python scripts/waha_team.py up
.venv/bin/python scripts/waha_team.py doctor
.venv/bin/python scripts/waha_team.py run local create
.venv/bin/python scripts/waha_team.py run local status
.venv/bin/python scripts/waha_team.py run local qr
open local-data/waha-a02/qr.png
```

For subsequent commands below, replace `.venv\Scripts\python.exe` with `.venv/bin/python`; no PowerShell is needed. A new environment is required per machine: do not copy Windows .venv, private profile/config or Docker sessions. Existing installations should use their original setup rather than rerunning init.

Team up/stop reads the Docker daemon's architecture, not the host Python architecture (Python may run under Rosetta). For arm64/aarch64 it appends `infra/waha-arm64.compose.yaml`, pinning native `arm-2026.9.1` digest b4216daddb7d5c1eb3ab99e608b76a005ec7523e766f923939d229718df4aafb and WEBJS. x86 remains on the previously tested image. Manual Compose users must also append that override on ARM and retain their correct database environment. Do not switch to unpinned :arm or another engine to work around a manifest error. ARM image architecture/configuration has been checked; a physical Mac account scan has not been verified.

Docker is not automatic CPU translation: the original fixed index has linux/amd64 only (plus an attestation), so Apple Silicon can fail pulling it without an ARM override/emulation. WAHA publishes separate [ARM images](https://waha.devlike.pro/docs/how-to/engines/); [Docker's multi-platform explanation](https://docs.docker.com/build/building/multi-platform/) distinguishes native execution and emulation. Backend/config helper Python images are multi-platform. This local path requires Docker Desktop; an alternative Docker engine's host networking is not implicitly validated.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r apps/backend/requirements.lock
.venv\Scripts\python.exe scripts/waha_team.py init
.venv\Scripts\python.exe scripts/waha_team.py up
.venv\Scripts\python.exe scripts/waha_team.py doctor
.venv\Scripts\python.exe scripts/waha_team.py run local create
.venv\Scripts\python.exe scripts/waha_team.py run local status
.venv\Scripts\python.exe scripts/waha_team.py run local qr
```

Open ignored `local-data/waha-a02/qr.png` locally and scan through WhatsApp linked devices. QR is generated only in SCAN_QR_CODE; if WORKING, do not request another QR. `create` is for a new session only; never repeat mutations blindly after a timeout. Check status first. A failed/stopped session has the explicit local `restart` command. Up never creates/restarts the provider session automatically.

Init generates private keys and a workspace-bound team profile; up upgrades migrations, creates only the local application account, provisions the initial empty allowlist and starts API/worker/monitor. It does not seed Replay orders or send messages. Every `waha_team.py` invocation reads its own database profile, so new terminals need no DATABASE_URL export. An incompatible preexisting DATABASE_URL causes DATABASE_ENV_CONFLICT; remove that terminal override for team mode. Existing legacy setup users must not run init/up: continue the recovery runbook and set their existing DATABASE_URL; doctor/checkpoint/verify/run can operate against that explicit local PostgreSQL.

After WORKING, select ONLY the consenting test chat:

```powershell
.venv\Scripts\python.exe scripts/waha_team.py run local select-chats --limit 20
.venv\Scripts\python.exe scripts/waha_team.py run ingress provision
.venv\Scripts\python.exe scripts/waha_team.py run ingress sync-container-config
.venv\Scripts\python.exe scripts/waha_team.py up
.venv\Scripts\python.exe scripts/waha_team.py run ingress configure-live
.venv\Scripts\python.exe scripts/waha_team.py run ingress diagnose
.venv\Scripts\python.exe scripts/waha_team.py run smoke http
```

Selection prints names/IDs only to your terminal; do not share this output. Provision updates authoritative allowlists and enables the connection, so use it only when explicitly granting access. Up reuses an existing binding and preserves paused state/allowlists; after changing host settings it synchronizes private volumes and rebuilds services. Configure-live switches from volatile probe to durable ingress and may restart the provider; inspect status afterward. Setting a local consent flag alone does not pause the database-owned connection. Pause with `run ingress pause`; remove selected chats in your private config and run provision to update authorization. No product consent UI exists yet.

## Self-service live acceptance

```powershell
.venv\Scripts\python.exe scripts/waha_team.py checkpoint
# In ONE selected consenting chat: send a NEW text, edit it once, then delete for everyone.
# Query run ingress status after each action; allow the worker to finish.
.venv\Scripts\python.exe scripts/waha_team.py verify
.venv\Scripts\python.exe scripts/waha_team.py run smoke http
```

Require mutation_sequence_verified=true. An incomplete sequence exits with code 2, not a successful acceptance exit. The tool checks account/connection scope, ordered create/edit/revoke revisions 1/2/3, one internal identity, canonical provider identity, persisted final revocation and completed jobs. ACK/state notifications can increase accepted without business jobs. No text/chat/provider IDs are returned; sample_group is a temporary number. A missing event, wrong identity, processing job or unrecalled message does not pass. A checkpoint range over 100 events refuses verification rather than silently truncating; make a fresh checkpoint and new test. Verification is read-only; checkpoint writes only ignored metadata. It does not clear incidents or prove AI/business confirmation/send.

Run up again and repeat status/verify to check restart persistence. Recheck an unselected chat with authorized participants: accepted content sync must not advance from that chat, and safe rejection metrics can rise; do not persist rejected content as evidence. Pause and confirm no new business events are accepted. These manual checks require the developer's real account; automated fixtures are retained only for reproducible regression/fault checks, not as their required development experience.

Stop safely: `waha_team.py stop` stops only team services and preserves volumes. Never use down -v or delete sessions as routine troubleshooting. Failed up may leave successfully completed stages running; doctor identifies safe checks, then retry up after resolving the cause. A failure is never reported as successful startup.

## Troubleshooting

| Result | Action |
| --- | --- |
| EXISTING_SETUP_PRESERVED / EXISTING_DOCKER_SETUP | Existing installation is untouched; use its original clone/runbook, do not delete volumes to force init. |
| LOCAL_PORT_IN_USE | Identify the owning process; stop only your own conflicting service or use a separate machine. |
| TEAM_PROFILE_WORKSPACE_MISMATCH | Return to the originating clone; migration/copy is an explicit operation, not automatic adoption. |
| Docker unavailable | Start Docker Desktop Linux engine; verify docker version. |
| Database unavailable/migration required | Team mode: up; legacy mode: verify the existing DATABASE_URL and migration head. |
| Binding/database mismatch | Check configuration ownership/database choice, do not reprovision another person's session. |
| API unavailable/check binding | Start services and sync private configuration; health intentionally fails for unreadable/invalid bindings. |
| Pipeline false / review true | Diagnose components; review_required is independent of readiness. Recovered gaps require human review, not automatic acknowledgment. |

## Concrete integration framework

Runtime uses built images, not live host source mounts. After backend changes run team up to rebuild/recreate, then diagnose/smoke and new-message acceptance. Existing completed jobs are not a substitute for new input. Before frontend development install the locked dependencies with `npm ci` in apps/web; run check:api/format:check/build. Frontend can now use the [owned setup/QR/chat APIs](role-a-setup-api-acceptance.md) for the operator-prepared local connection; product screens remain D's work. Keep a feature branch from the team's agreed main commit and coordinate shared contracts with A/C; do not merge or send automatically from this tool.

Entry chain: `api.waha_events` → source HMAC → `waha_ingress.receive` → `messaging.ingest` → Inbox/MessageRow/ConversationRow/Job → `worker.run_once`. Pydantic/domain/OpenAPI types are generated; independent event schema remains versioned. Account ownership comes from trusted configuration, never provider-supplied account IDs. Do not bypass this chain to call a model directly from the webhook.

| Role | Integration surface and next batch | Required invariants |
| --- | --- | --- |
| B | Live WAHA jobs now route through `gigmate.extraction.provider()` and persist `proposals` + `model_call_traces` rows; unknown content ends with `EXTRACTION_NEEDS_REVIEW` instead of `LIVE_EXTRACTION_PENDING`. Scope, contracts and evaluation harness live in the dedicated [Role B extraction subsystem](role-b-extraction.md). Use the Inbox normalized event, latest `MessageRow` source revision and `ConversationRow.context_version`; `gigmate.understanding.extract` remains the legacy Replay entry point. Real-model integration is a separately authorized batch. | Ambiguous multi-order assignment needs review. Persist proposals only for current context/source. Real-model credentials remain server-side. Completed old jobs are not automatically re-extracted; reprocessing needs an explicit idempotent design. |
| C | messaging.ingest advances context and invalidates changes; workorders.confirm owns existing internal confirmation. Design actions/outbox/executor/reconciliation before requesting WAHA sending. | Customer proposal/confirmation and merchant approval separate. Immutable approval snapshot/version/expiry checks. Unknown outcomes never blindly resend. No external adapter now. |
| D | GET /api/v1/connectors/recovery-issues plus local setup/QR/opaque chats/control operations; generated types in api.d.ts. Vite currently proxies Replay API; switching to ingress requires explicit origin/auth checks. | Distinguish readiness/review and operation outcome; poll 202 intents, preserve request keys and refresh control_version. Use the setup agreement; never call WAHA administration directly. |
| E | waha_team checkpoint/verify + smoke_waha_ingress + check_waha_recovery --run. Record fresh clone SHA, dependency versions, actual outputs and defects. | Independent review; no real content/keys/QR in tracked evidence. SQLite cannot establish PostgreSQL locking. Router/logout/missing-history recovery remain separate checks. |

Develop coordinated related tasks as one authorized batch, including migrations/contracts/tests/bilingual docs, then one acceptance. Do not change shared migrations or generated artifacts manually. Before main merge, an independent teammate should execute the clean own-account path; developer self-tests cannot replace this. Cloud API remains excluded, and this document does not authorize sending, general AI or production deployment.
