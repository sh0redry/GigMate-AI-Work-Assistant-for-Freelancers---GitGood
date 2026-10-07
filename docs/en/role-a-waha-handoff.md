# WAHA implementation and team handoff

Updated: 2026-10-06. This is the current capability summary, not a claim that every feature in WAHA itself is implemented in GigMate. [Chinese counterpart](../zh/role-a-waha-handoff.md). [Evidence and incident history](role-a-recovery-acceptance.md).

## What works now

2026-10-07 extension: [setup API delivery](role-a-setup-api-acceptance.md) implements owner-scoped backend connection intents, QR, opaque chat selection and pause/resume for the already bootstrapped local session. Product screens and production/multi-merchant onboarding remain pending; earlier CLI-only notes below are historical for those backend operations.

The optional local WAHA connector feeds trusted events into the existing modular backend, PostgreSQL inbox and separate worker. Replay remains available. Pinned provider: WAHA Core 2026.9.1, WEBJS, image digest in [Compose](../../infra/waha.compose.yaml). Other provider versions/engines are not validated.

| Capability | Implemented behavior and limits |
| --- | --- |
| Local pairing | Private initialization, session start/status, QR saved privately for operator scanning; existing Linux session volume reused across service restarts. No product onboarding UI. |
| Conversation selection | CLI lists recent chats for local selection; appends selected chats to ignored configuration. `provision` synchronizes authoritative database allowlists and account/session mapping. Local selection alone does not update database authorization. |
| History probe | Counts available records for an allowed chat, returns complete_history=false. It does not import old messages into business storage or prove completeness. |
| Text events | Incoming/outgoing text creation, editing and revocation normalized into versioned events. Canonical and short provider targets mapped conservatively; direction/ambiguity checks reject uncertain targets. Real same-message revisions 1/2/3 verified twice after recovery. |
| ACK and session events | Delivery acknowledgments update delivery metadata, not content/context or extraction jobs. Session state notifications update connection samples and reject conflicting ordering; accepted counts include these events, not just texts. |
| Source security | Raw-body HMAC, size/type checks, server-owned account/session mapping, consent and conversation allowlists before business persistence. Connector secrets never enter browser/model contexts. Browser authentication remains seeded development sessions/CSRF, not production identity. |
| Durable reception | Transactional inbox/message revisions/context/job writes, commit before success, stable event identity, duplicate detection, identity-conflict rejection, context changes and stale proposal invalidation. Does not promise provider retry completeness or external exactly-once delivery. |
| Durable worker | PostgreSQL claims/locks, leases, version/consent checks, three-attempt budget including crash recovery, stale-owner protection, terminal timing and bounded database waits. Real content completes with LIVE_EXTRACTION_PENDING or SOURCE_SUPERSEDED rather than fictional extraction. |
| Health/status | Persisted state/freshness, last content sync, receipt/duplicate/stale counts and job counts; separate API/provider/worker/monitor health, pipeline_ready, review_required and safe metrics. Health also validates configured private binding/ownership. |
| Recovery review | Persisted provider/API/monitor/worker gaps and source issues; recovery timestamp does not clear review. `issues` and explicit `ack-issue` outcomes support review without history import. Database outages cannot always be persisted while they occur. |
| Local operations | Diagnose/reconcile, pause, provision, webhook configuration, private-binding migration/configuration-volume sync and explicit 30-day content cleanup. No arbitrary send command. Private configuration uses Docker volumes; session volume is preserved. |
| Verification | PostgreSQL 241 tests; SQLite 236 passed/5 PostgreSQL-specific skips; isolated real database/API/worker fault runner eight checkpoints; local WAHA interruption; seven HTTP checks; repeated real create/edit/revoke verification. E's independent signoff remains separate. |

## API, commands and reading order

New teammates should follow [own-account local development](role-a-team-local-development.md): isolated team database, startup/doctor/checkpoint/verify wrapper and concrete downstream integration surfaces. Legacy installations remain supported without automatic adoption.

- Browser: authenticated, account-scoped `GET /api/v1/connectors` and `GET /api/v1/connectors/{connection_id}/recovery-issues`.
- Provider: signed `POST /api/v1/connectors/waha/{connection_id}/events`, separate from browser authentication. Frontend must not administer WAHA or access its keys.
- `scripts/waha_local.py`: init/probe/create/status/qr/restart/observations/select-chats/history/sync-container-config; capability probe observations are volatile, not the durable business inbox.
- `scripts/waha_ingress.py`: provision/status/diagnose/reconcile/watch/pause/purge/configure-live/issues/ack-issue/migrate-binding/sync-container-config. Review does not perform imports. Purge is an explicit destructive retention operation, not a routine acceptance step.
- Read this summary first, then [responsibilities](role-a-responsibilities.md), [recovery runbook and E matrix](role-a-recovery-acceptance.md), [API agreement](../../contracts/api-v1.md) and [current implementation evidence](implementation-status.md). Earlier stage notes preserve development history; use the latest dated results.

For a new host PowerShell terminal, start Docker Desktop and the existing database/WAHA services and set the local database explicitly:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:54329/gigmate_waha_a03'
.venv\Scripts\python.exe scripts/waha_ingress.py diagnose
.venv\Scripts\python.exe scripts/smoke_waha_ingress.py
```

For setup/migrations/Compose/private-volume synchronization, use the recovery runbook rather than reprovisioning an existing installation. Never copy credentials, QR, real chats or session files into tracked artifacts. Do not delete live-project volumes to fix a connection error.

## Handoff to other roles

| Role | Ready to use | Still required |
| --- | --- | --- |
| B | Trusted allowlisted events, source revisions and context; synthetic fixtures and preserved business storage | General extraction, prompts/evaluation and integration for real content. A completed live ingress job does not currently produce an AI proposal. |
| C | Persistent ownership, inbox/jobs, source/context invalidation, locks and bounded recovery | Business confirmation/approval semantics; approved external actions, outbox, final checks and unknown-outcome reconciliation. Existing Replay internal confirmation is not WAHA external execution. |
| D | Generated ConnectorStatus/RecoveryIssue types and scoped APIs | Product QR/selection/consent flow, health/review UI and safe errors. connected alone is insufficient: display pipeline readiness separately from review_required. |
| E | Stage evidence, safe HTTP smoke, disposable fault runner, independent real text evidence | Independent acceptance and review; Internet/router/logout/QR recovery and missing-content restoration are not established. |

## Not implemented or not established

- Complete historical import, automatic missed-message backfill, automatic recovery of missing revisions, or guaranteed ordering/completeness after outages.
- General media ingestion/transcription, full chat mirroring, group/media coverage and cross-engine behavior. Provider features are not product features unless explicitly adapted and tested.
- General live AI extraction, automatic confirmed work orders or automatic formal calendar writes. AI remains proposals/drafts; no external send adapter, approvals/outbox/send echoes or unknown-send reconciliation.
- Production authentication, multi-merchant self-service onboarding, production secret management, public deployment hardening, alert delivery, or completed frontend connector screens.
- Independent E signoff or a guarantee that no messages were lost. Eleven local historical review records remain unacknowledged at the latest check.

## Remaining batch plan

Official Cloud API work is deferred by the user and is not in the current plan. Next is unified A-03 review with E and explicit human review of recorded gaps. Subsequent WAHA work requires authorization and confirmed dependencies: D's connector UI, B's real-content processing, then C's approved execution chain before any A-04 send adapter. Preserve batch development and unified acceptance; this summary authorizes no additional implementation or external deployment.
