# Role A technical evolution and unified acceptance

Updated: 2026-10-02. This is a development plan, not completed implementation. Scope is ingestion, authentication, durable jobs and connection monitoring. See [responsibilities](role-a-responsibilities.md) and the [Chinese counterpart](../zh/role-a-development-roadmap.md).

## Starting point and operating policy

The [WhatsApp connection flow](whatsapp-connection-flow.md) explains pairing, session ownership, conversation selection and initial history synchronization for A-02/A-03.

v0.2 uses FastAPI, SQLAlchemy/Alembic, PostgreSQL, one modular backend and a separate worker. Development authentication, allowlisted replay create/edit/revoke, inbox/jobs, version checks, fixed extraction and internal schedule confirmation exist. Live WAHA, production authentication, general AI and external approval/outbox/reconciliation do not.

Target flow: adapter → source authentication/trusted ownership → consent/allowlist → normalized event → atomic PostgreSQL reception/jobs → worker → proposals/business services. Persist connection state separately and expose an account-scoped API. Future sending passes through approved actions.

Read [architecture](architecture.md), [ADRs](adr/README.md), [contracts](../../contracts/README.md), [API agreement](../../contracts/api-v1.md) and [setup/checks](getting-started.md). The kickoff plan is historical.

For every authorized milestone, define tasks, dependencies, exclusions and acceptance first; then complete as many related tasks as practical in a coherent batch: design/contracts, implementation/migrations, tests/fixes, integration/docs, one acceptance package. Adjacent batches below may be combined when dependencies and authorization permit. They do not require per-task user acceptance. Continue editing, checking and reporting without stopping after every subtask.

If accounts or environment block live tests, finish independent adapters, synthetic tests, persistence, APIs and docs, and report blocked checks. Mock results cannot establish live capability. Preserve reviewability, independent review and scope boundaries. This documentation change authorizes no future live implementation by itself.

## Implementation locations

| Location | Evolution |
| --- | --- |
| messaging.py | Preserve common ingestion; separate replay-only restrictions from adapter capabilities rather than simply accepting waha |
| identity.py / api.py | Keep browser session/CSRF; add separate provider webhook authentication and trusted account context |
| db.py / migrations/versions | Add constraints/indexes and versioned migrations for actual state/mapping/reconciliation implementation; never rewrite 0001 |
| worker.py | Coordinate locks/leases/transactions with C; retain context/consent checks; no unapproved sends |
| contracts/events / examples | Independent schema versions, manifest, positive/negative examples and consumer coordination |
| contracts.py / export_contracts.py | Modify source response models/routes and regenerate implemented OpenAPI/types |
| backend tests / infra / .env.example | Implement meaningful behavior/failure tests and safe configuration placeholders |
| apps/web | Coordinate status/error presentation with D; no connector credentials |

These are under apps/backend/src/gigmate, apps/backend/migrations, contracts and scripts respectively. Add responsibility-named service files when implementation needs them; split packages only when code grows. Future table/endpoint/signature names and fields are decided in the relevant batch, not frozen by this plan.

## A-01: stable contracts and replay failure baseline

2026-10-02: independent adapter/corpus/tests/demo delivered under the user's new-file/no-shared-code restriction. See [A-01 acceptance](role-a-stage1-acceptance.md) for evidence, mappings and pending shared integration. This is not completion of live ingress.

Goal: downstream development can rely on one input structure without live accounts.

1. Inventory five schema types against three implemented ingestion types; distinguish defined, accepted, consumed and live-tested capabilities.
2. Document ownership/session mappings, event vs message identity, revisions, timestamps, source/direction and payload. Never derive event identity from arrival time.
3. Coordinate B/C/D consumers, errors and compatibility; version and document breaking migrations.
4. Extend synthetic fixtures/manifest and replay tooling for edits, revokes, malformed fields, duplicates, identity conflicts, revision gaps and cross-conversation message IDs.
5. With E, fill meaningful normal/failure test gaps and write reproducible steps.
6. Verify atomic inbox/message/context/proposal-invalidation/job writes and acknowledgment after commit; failure leaves no partial business data.

Deliver contract notes, examples, capability matrix, tooling/tests, compatibility changes and bilingual docs. Accept the batch when valid inputs create durable jobs, unauthorized/invalid inputs store no business content, duplicates do not multiply work, conflicts are explicit, and stale content cannot create actionable proposals. C owns domain confirmation rules.

## A-02: live adapter and secure ingress

Dependencies: A-01, authorized noncritical test account, usable WAHA environment and applicable collaboration gates. Probe capabilities before selecting implementation.

1. Test and pin WAHA version/engine/deployment; record text/edit/revoke/ack/history/reconnect recovery capabilities.
2. Determine persistent provider/internal ID and revision mappings from tests, including redelivery and missing fields. Changed receipt time must not alter semantic identity/digest; evaluate current whole-event digest compatibility.
3. Implement strict normalization with size/type restrictions and explicit unsupported media/event handling.
4. Add a separate provider webhook route with the pinned version's tested key/signature mechanism. Resolve account/session from server configuration and check consent/allowlist before content storage. Design timestamp/replay protection if the actual provider supports it.
5. Keep secrets and administration server-side; sanitize request/exception logging.
6. Define responses for rejected input, connection timeouts and failed commits according to tested provider redelivery behavior. Success means committed reception only.
7. Preserve account-free Replay; implement synthetic/mock integration tests and separately authorized live checks.

Deliver capability report, adapter/webhook, safe configuration, necessary migrations, integration tests and sanitized live findings. Accept when allowed live text enters durable processing, forged/cross-account/non-allowlisted input is blocked, duplicates do not create jobs, and restart preserves mapping/data. Unsupported edits/revokes remain explicit limitations.

## A-03: state, observability and recovery

Depends on A-02 capability findings; may ship in the same complete batch.

1. Design/persist account-owned connector/session state: connected/connecting/disconnected/failed, source timestamp, last successful sync, freshness and safe error codes; add migration/model.
2. Handle duplicate/late notifications and restart using provider ordering or reconciliation; do not overwrite current state with late old notifications.
3. Extend connection-status source API/model, regenerate contracts/types, and coordinate D's replay/live/disconnected/stale UI. API health does not establish chat connectivity.
4. Measure reception/duplicate/rejection counts, ingestion-to-processing latency, backlog, failed jobs, expired leases and disconnection duration. Choose thresholds from measured load rather than inventing guarantees.
5. Implement recovery or manual reconciliation according to tested lookup/backfill support. Recovered events still pass authentication/allowlist/dedup/source rules. Document gaps when backfill is unavailable.
6. With C, verify concurrent claims, conversation serialization, account lock order, leases and retry bounds. If renewals are needed, prevent former lease owners from committing.
7. With E, inject reception/worker database outages, lost responses after commit, worker crashes, disconnects, repeated backfill and out-of-order revisions; verify no partial writes or repeated business effects.

Current worker locks accounts more coarsely than conversations; finer parallelism is a target. Replay rejects revision gaps; live order recovery needs durable waiting/lookup or manual review rather than arrival-time overwrites.

Deliver persisted status/API/UI, metrics/runbooks, recovery policy and PostgreSQL failure evidence. Accept when status is scoped/fresh, restart recovers, two workers do not duplicate commits, retries are bounded, gaps are reconciled or explicitly reviewed, and logs contain no private content.

## A-04: approved external execution integration

Future milestone, outside default replay expansion. Depends on C's action snapshots, approvals, final version checks, transactional outbox, cancellation and reconciliation. No arbitrary-send shortcut.

1. Implement tested sending/lookup capabilities and distinguish definitely-not-submitted, accepted, delivered and unknown outcomes; acceptance is not customer confirmation.
2. Supply availability/error classifications; C revalidates consent, ownership, connection, cancellation, expiry and work-order/context/action versions before dispatch.
3. Recognize API echoes: advance context without recursive replies or retroactive cancellation of dispatched sends; later queued actions still require current context.
4. Possible-submission timeouts become result_unknown and reconciliation, never blind resends. Only definite non-submission permits bounded retries after fresh checks.
5. With C/E, test disconnection, consent revocation, inbound/dispatch races, echoes, unknown outcomes and restart. Local serialization cannot cover remote events not delivered yet; do not promise external exactly-once.

Deliver adapter/outcome semantics and synthetic plus authorized live evidence. Accept the complete approval/execution chain, not one successful send.

## Planned acceptance matrix

| ID | Group | Required assertion / level |
| --- | --- | --- |
| A-E-01 | Shape/version/payload | Positive pass, negative fail, unsupported types rejected; schema/service, A-01 |
| A-E-02 | Duplicates/identity | No new records on replay; identity conflicts; revisions not collapsed; service/database, A-01/02 |
| A-E-03 | Authentication/ownership/allowlist | No business storage/jobs/model call after rejection; API/service, A-01/02 |
| A-E-04 | Edit/revoke/order | Traceable sources, stale proposals invalidated, reject/reconcile gaps; service/integration, A-01/03 |
| A-E-05 | Reception transaction/lost response | Rollback has no partial writes, committed redelivery is idempotent; PostgreSQL injection, A-01/03 |
| A-E-06 | Concurrency/leases/failure/restart | No duplicate commits, bounded failures, durable jobs/mappings; PostgreSQL/process, A-03 |
| A-E-07 | State/disconnect/backfill | Isolation, freshness, recovery and gap reconciliation; mock/authorized live, A-02/03 |
| A-E-08 | Send/echo/unknown | Approval checks, no reply loop or blind resend; actions/live, A-04 |

These are planned group IDs, not pass claims or replacements for AC-001 through AC-012. Expand each with inputs, initial state, fault steps, database/HTTP/model-call expectations, actual outcome, defect and retest evidence.

## Unified verification and delivery

Use the project .venv and backend lock with [documented commands](getting-started.md). Document-only batches run baseline. Code changes require applicable Ruff check/format, generated drift, baseline, migration upgrade/check and pytest. API/frontend changes require check:api, format:check and build; running deployments require smoke, restart and failure recovery checks.

```powershell
.venv/Scripts/python.exe scripts/check_baseline.py
.venv/Scripts/python.exe -m ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py
.venv/Scripts/python.exe -m ruff format --check apps/backend scripts/export_contracts.py scripts/smoke_replay.py
.venv/Scripts/python.exe scripts/export_contracts.py --check
.venv/Scripts/python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv/Scripts/python.exe -m alembic -c apps/backend/alembic.ini check
# Set PYTHONPATH and isolated PostgreSQL test URL as documented first:
.venv/Scripts/python.exe -m pytest apps/backend/tests -q --basetemp=local-data/pytest
# In apps/web: npm run check:api / npm run format:check / npm run build
```

This is a future checklist, not commands executed for this document. Missing dependencies fail clearly. SQLite does not prove row locking. basetemp is disposable test-only storage, never user/workspace data. Repository fixtures remain synthetic.

One acceptance package contains batch ID/authorized scope/baseline, completed/blocked/pending tasks, behavior/capability changes, contract/migration/configuration notes, actual commands and database versions, A-E results and live limits, recovery/defect/retest evidence, review impacts, bilingual completion records and next dependencies.

Developers complete self-checks/fixes before E organizes one batch acceptance. Preserve independent cross-module code review. Fix acceptance failures within the batch and retest affected behavior; do not repeat unaffected passing checks for formality. Record completion only when requirements actually pass. Do not commit, push or externally deploy without request.
