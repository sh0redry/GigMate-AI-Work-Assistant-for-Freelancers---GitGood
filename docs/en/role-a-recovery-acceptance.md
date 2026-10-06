# A-03 recovery and operational acceptance

Date: 2026-10-02. Baseline: `83aa75e`, Andy_WAHA. This is the authorized follow-up to [durable ingress](role-a-stage3-acceptance.md), not A-04 external sending. [Chinese counterpart](../zh/role-a-recovery-acceptance.md).

## Delivered scope

- Versioned `0004_waha_recovery` adds safe health/diagnostic tables, worker heartbeats and optional job completion timing/lease-recovery fields. Earlier migrations are preserved; historical completed jobs are not given invented timings.
- Connector status separates API, provider, worker and monitor samples. States are healthy/unavailable/stale/unknown. `live_connected` retains its WhatsApp-session meaning; `pipeline_ready` requires enabled, fresh connected state and all four healthy components. `review_required` is independent: a healthy pipeline may still have unresolved gaps.
- Monitor probes API `/health` and trusted provider status every 30 seconds. API/provider/monitor samples expire after 120 seconds; worker records a heartbeat every 10 seconds and expires after 30. These are configured test-environment windows, not performance or availability guarantees. A heartbeat means a worker recently reached its loop/database, not that every job is healthy.
- Monitor uses its own Compose network namespace. Its fixed internal WAHA target is `http://waha:3000`; host configuration remains loopback-only, redirects/proxies remain disabled and arbitrary internal endpoints are not accepted. WAHA shutdown no longer removes the monitor's database/API connectivity.
- Persisted incidents describe ingress/provider unavailability, worker/monitor gaps and authenticated source/order conflicts. Component recovery records recovered_at but does not automatically clear manual review. No provider payload, real chat/message identifier, credential or free-form review text enters the new tables.
- Signed business rejections increment a scoped safe-code counter in a separate transaction after content rollback. Unauthenticated payloads create no diagnostic records. A failed database cannot count its own failed writes; a surviving monitor keeps the failure start in memory and records the uncertain window once writes recover. If the monitor also restarts, this start can be lost; a later sampling gap may still be detected. Brief unsampled outages cannot be ruled out.
- Metrics expose retained-job retries, recovered/expired leases, oldest unfinished-job age, measured terminal-job processing duration and receipt-to-completion latency. Metrics cover retained jobs, not lifetime throughput or AI accuracy. Null timings indicate no measured samples. Existing jobs retain unknown timing values.
- Worker crash recovery observes the same three-attempt budget as normal failures. An expired processing lease at the budget is marked failed/RETRY_EXHAUSTED rather than reclaimed indefinitely. A stale owner cannot commit another owner's result. Real content still completes without fictional extraction, proposals or external execution.
- PostgreSQL reception/diagnostic lock waits are bounded at 3 seconds and statements at 5 seconds; connection/pool waits are bounded at 5 seconds. Failed reception returns an error, never durable success. Recovery does not promise that provider retries cover a prolonged outage.
- Development login/logout commits before success; login-session presence is checked at ASGI response-start in a regression test. The safe HTTP smoke now also checks the scoped recovery list and reports a fixed failure step without response content.

## Operator workflow

The current local system has already been upgraded/deployed. For another existing local installation:

```powershell
$env:PYTHONPATH = 'apps/backend/src'
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:54329/gigmate_waha_a03'
.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv\Scripts\python.exe scripts/waha_ingress.py migrate-binding
.venv\Scripts\python.exe scripts/waha_ingress.py sync-container-config
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml -f infra/waha-ingress.compose.yaml up --build -d --wait ingress ingress-worker ingress-monitor
.venv\Scripts\python.exe scripts/waha_ingress.py diagnose
.venv\Scripts\python.exe scripts/waha_ingress.py issues
```

`status` reads persisted state; `diagnose` actively samples local health; `reconcile` retains its provider-state-only behavior. All operator commands resolve the private binding and server account ownership. Browser `GET /api/v1/connectors/{connection_id}/recovery-issues` is authenticated and account-scoped; it exposes safe operational metadata only. No browser credential or provider administration endpoint was added. D's UI integration remains a handoff.

For each recovered incident, compare the affected interval with the consenting participant's local records. Do not copy messages into issue notes or public fixtures. Choose an explicit outcome using the issue UUID printed by `issues`:

```powershell
.venv\Scripts\python.exe scripts/waha_ingress.py ack-issue --id "<issue UUID>" --resolution needs_followup
# After reviewing and deciding no history import is to be performed:
.venv\Scripts\python.exe scripts/waha_ingress.py ack-issue --id "<issue UUID>" --resolution reviewed_no_import
```

`needs_followup` keeps review required and can later be finalized. A final review is idempotent and cannot be changed to a different outcome. An actively unavailable component cannot be acknowledged. Review acknowledgement performs no history import and is not proof that no messages were lost. Do not acknowledge merely because connected/pipeline_ready becomes true.

Unknown originals, ambiguous/old edit targets or missing revisions require manual review; neither history record counts nor a fresh connection reconstruct deleted revisions. There is no automatic backfill in this batch. Approval/outbox/send and production identity/secrets remain outside scope.

## Reproducible fault environment for E

```powershell
.venv\Scripts\python.exe scripts/check_waha_recovery.py --run
```

The runner creates only `gigmate-waha-recovery` from [dedicated Compose](../../infra/waha-recovery.compose.yaml), with PostgreSQL 17.9 on loopback 54339 and API on 18712. It refuses existing project containers or its existing test volume, uses synthetic content/private binding under ignored `local-data/waha-recovery`, and stops/restarts only its own services. Its finally cleanup removes only this disposable test project's containers/volume. The shared database, WAHA session and real chats are never used. Results are safe metadata in ignored `result.json`. Keep ports free. Interrupted cleanup must be resolved against this named test project before another run; do not remove live-project volumes.

| Case | Expected and evidence source |
| --- | --- |
| R-01 Concurrent HTTP delivery | One durable original, duplicates, health responsive; real server runner and PostgreSQL ASGI tests |
| R-02 API outage/restart | Health unavailable; receipt survives; retry creates no extra job; gap remains for review |
| R-03 Database outage | Health/reception return 503, never false acceptance; real disposable database stop/start |
| R-04 Database recovery | Retrying the same failed signed event commits once; persisted jobs later drain |
| R-05 Worker crash | API remains healthy while worker sample becomes stale; actual disposable process killed/restarted |
| R-06 Expired worker lease | Exactly one recovery/extra attempt; runner explicitly seeds a synthetic expired lease, not a claim that the killed process owned it |
| R-07 Review workflow | Component recovery retains issues; explicit synthetic review clears them without import |
| R-08 WAHA outage | Live provider container interruption; API/worker/monitor remain independently reachable after network fix |
| R-09 Authorization/diagnostics | Forged signature has no diagnostic mutation; signed rejected content rolls back; issue list is account-scoped |
| R-10 Ordering/limits | Late health samples cannot regress; repeated crashes exhaust attempts; row-lock wait returns failure |

Tests use synthetic messages. SQLite proves compatibility only; PostgreSQL supplies lock/concurrency evidence. A passing automated suite is not E's independent review. Detailed actual results and live interruption evidence are recorded in [implementation status](implementation-status.md).

Private host binding now lives at `local-data/waha-a02/bindings/ingress.json`; `migrate-binding` preserves the old binding and paused state. `sync-container-config` transfers private configuration through subprocess stdin into project-scoped Docker volumes `waha-monitor-config` and `waha-ingress-bindings`, without secrets in command arguments/output. Containers mount these volumes read-only. After changing host settings, synchronize again and recreate relevant services; chat authorization still requires `provision`, and HMAC rotation still requires updating the provider through `configure-live`. Configuration volumes contain credentials: do not publish or export them. Preserve the live session volume; do not use live-project `down -v`. The disposable fault runner uses its own binding volume and cleans only its own resources.

API `/health` now checks database access and, when WAHA is configured, readability/validity and persisted ownership mapping of the private binding. It returns 503 for an unusable binding. Replay without a WAHA binding remains supported. This is readiness evidence, not proof of real webhook delivery.

Subsequent diagnosis confirmed an independent reception fault: the Windows bind-mounted private configuration returned `ENODEV` inside the API while the host file remained valid. A forged-signature probe returned `503 CONNECTOR_CONFIG_INVALID`, revealing the earlier health endpoint missed this dependency. Recreating host mounts also failed because Docker Desktop's D-drive sharing was unavailable. Moving runtime configuration to private Docker volumes restored reception checks without restarting Docker Desktop, WAHA or the session. At 13:39 UTC all four components were healthy and pipeline_ready=true; seven HTTP checks and the eight-checkpoint disposable fault run passed. Nine review records remain unacknowledged, including repair interruptions. Fresh real creation/edit/revoke acceptance still needs the user's retry. The provider's earlier temporary connecting cause remains unestablished.

## Remaining limits

### Successful post-recovery live mutation check — 2026-10-06

Repeat run at 07:07 UTC: read-only scoped database metadata confirms one earlier ACK at 06:48:01 UTC (accepted 34 to 35, no content job), then the same new message's creation/edit/revocation at 07:07:12/31/41 UTC (accepted 35 to 38). Persisted revisions are 1/2/3, internal and canonical provider identities agree, latest mapping revision 3 is revoked. Three jobs completed on attempt 1, processing 9/8/10 ms and completion latency 114/321/266 ms. Seven safe HTTP smoke checks passed again; current pipeline_ready=true and queues/failures zero. Rejected count 88 and last SOURCE_MESSAGE_UNRESOLVED at 06:48:08 UTC precede this new mutation sequence and did not increase during it; the aggregate counter does not identify rejected event types. Eleven review records remain unacknowledged. No runtime changes or commit/push.

Account/connection-scoped read-only PostgreSQL metadata confirms four new content events on October 6. At 06:02:32 UTC an independent creation persisted revision 1. A second message then persisted creation at 06:37:17, edit at 06:37:23 and revocation at 06:37:34 UTC, with revisions 1/2/3. All three share one internal message identity and the canonical provider identity; the latest mapping is revision 3 and its persisted revision is revoked. No real identifiers or content were exported. Accepted receipts advanced 30 to 34; all four jobs completed, with no pending/processing/failed jobs in the user's status samples. Measured processing durations were 12/8/11/9 ms; receipt-to-completion latencies 539/242/75/205 ms. These four samples are local evidence, not performance guarantees. LIVE_EXTRACTION_PENDING and SOURCE_SUPERSEDED are expected terminal codes in this milestone; completion does not mean model extraction or external execution occurred. This closes the fresh text mutation check pending after the configuration-volume fix; earlier pending statements below describe October 2 history. Eleven recovery records still require separate human review and were not acknowledged. Missing-message recovery and E's independent signoff remain unproved.

Manual follow-up at 13:24–13:25 UTC: the user's samples showed fresh connecting state, healthy API/worker/monitor, provider unavailable and no new content sync. At 13:27 the provider was WORKING and active diagnosis reported all four components healthy/pipeline_ready=true without any restart or rescan by the agent. The latest provider incident has a recovery timestamp, but six review items remain unacknowledged. Receipt metadata contains 22 session-state notifications plus the six previously verified content/ACK receipts (total 28); no new manual text mutation has persisted. Private selected-chat and authoritative database allowlists match (one chat). Earlier safe logs identify SOURCE_MESSAGE_UNRESOLVED on an ACK at 10:48 and CONVERSATION_NOT_ALLOWED on message.any at 11:34; these do not prove what happened to the user's latest test. The cause of the connecting interval is not established. Manual content acceptance remains pending; retry only after pipeline readiness is healthy, using a new test in the selected consenting chat. No incidents were acknowledged automatically.

Network fault evidence is local container interruption, not a router/Internet or WhatsApp logout/QR recovery test. Provider retries are bounded; real missed-content restoration is unproved. Diagnostics cannot capture every outage while persistence is unavailable. Status reflects sampled health, not guaranteed callback delivery. No production alert transport, frontend status UI, historical import, model extraction, sending or external execution was added. This batch is prepared for a single independent review with E; no automatic commit/push.
