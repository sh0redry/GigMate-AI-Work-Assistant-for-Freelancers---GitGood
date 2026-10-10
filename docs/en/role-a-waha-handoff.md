# WAHA implementation and team handoff

Current baseline (2026-10-10): PR #11, #13 and D01 #15 are merged into main (1336c60). Andy_WAHA_message_sync includes that main plus the verified D01 compatibility below. PR #14 now targets main; retain its 0008 migration, bounded timeline/history/media observations and pagination rather than replacing the branch with main. Older dependency-target notes below are historical.

2026-10-10 D01 compatibility: combine PR #15's persisted original-request recovery, expiry/authority guards, saved-authorization reload and replay workspace with message-sync discovery pagination, loaded search/type filters and WahaMessages. A restored discovery retains its original offset/limit/version/key and returns choices plus next_offset to the UI; it does not automatically submit a new page or reset unsaved selections. Retried connect/recover remains distinct from explicit server result_unknown reconciliation. Real phone/group/media and independent acceptance limits remain unchanged.

Review correction (2026-10-09): withdrawal no longer depends on provider configuration; new/repeated grants still do. Discovery across windows/pages preserves valid choice IDs without extending their expiry. D should refresh after successful selection and handle real expiry/version conflicts explicitly. A's message-sync branch also cancels active sync and records exclusion intervals during configuration-free withdrawal. See [setup rules](role-a-setup-api-acceptance.md). Baseline fixes are pushed to PR #11 as 99e73b1 and included in Andy_WAHA_message_sync. The additional message-sync PR targets Andy_WAHA_upgrade until PR #11 merges.

Updated: 2026-10-09. This is the current capability summary, not a claim that every feature in WAHA itself is implemented in GigMate. [Chinese counterpart](../zh/role-a-waha-handoff.md). [Evidence and incident history](role-a-recovery-acceptance.md). Latest batch: [message synchronization](role-a-message-sync-acceptance.md).

## What works now

2026-10-08: [merged integration delivery](role-a-integration-acceptance.md) connects D's screens to the [setup API](role-a-setup-api-acceptance.md): owner-scoped durable connection intents, transient QR, opaque chat selection, pause/resume and recovered-issue review. Local product screens are implemented; production/multi-merchant onboarding remains pending.

The optional local WAHA connector feeds trusted events into the existing modular backend, PostgreSQL inbox and separate worker. Replay remains available. Pinned provider: WAHA Core 2026.9.1, WEBJS, image digest in [Compose](../../infra/waha.compose.yaml). Other provider versions/engines are not validated.

| Capability | Implemented behavior and limits |
| --- | --- |
| Local pairing | Private initialization and durable backend control; the authenticated UI displays transient QR and status, reusing existing session volumes. No production onboarding. |
| Conversation selection | The UI discovers opaque choices and explicitly saves authoritative database authorization. CLI configuration selection/provision remains an operator alternative; mixing the two can replace choices. |
| History/sync | Legacy CLI still counts records. The product now explicitly imports bounded owned snapshots, with progress/cancel/retry, recorded permission exclusions and complete_history=false. No automatic business processing or complete-history guarantee. |
| Groups/media metadata | Participant/reply provenance, captions and declared attachment metadata, supported media ACK/edit/revoke observations. No original files, OCR/transcription or media GenAI; real-format acceptance pending. |
| Text events | Incoming/outgoing text creation, editing and revocation normalized into versioned events. Canonical and short provider targets mapped conservatively; direction/ambiguity checks reject uncertain targets. Real same-message revisions 1/2/3 verified twice after recovery. |
| ACK and session events | Delivery acknowledgments update delivery metadata, not content/context or extraction jobs. Session state notifications update connection samples and reject conflicting ordering; accepted counts include these events, not just texts. |
| Source security | Raw-body HMAC, size/type checks, server-owned account/session mapping, consent and conversation allowlists before business persistence. Connector secrets never enter browser/model contexts. Browser authentication remains seeded development sessions/CSRF, not production identity. |
| Durable reception | Transactional inbox/message revisions/context/job writes, commit before success, stable event identity, duplicate detection, identity-conflict rejection, context changes and stale proposal invalidation. Does not promise provider retry completeness or external exactly-once delivery. |
| Durable worker | PostgreSQL claims/locks/leases, permission/version checks, bounded retry/crash recovery and stale-owner protection. Real text routes into B's evidence seam with EXTRACTION_NEEDS_REVIEW or SOURCE_SUPERSEDED. Independent GET-only sync tasks have page progress/backoff and do not create business Jobs. |
| Health/status | Persisted state/freshness, last content sync, receipt/duplicate/stale counts and job counts; separate API/provider/worker/monitor health, pipeline_ready, review_required and safe metrics. Health also validates configured private binding/ownership. |
| Recovery review | Persistent gaps/source issues, explicit bounded incident/source lookup and independent human review. Finding a snapshot does not reconstruct revisions or clear incidents. Database outages cannot always record themselves. |
| Local operations | Diagnose/reconcile, pause, provision, webhook configuration, private-binding migration/configuration-volume sync and explicit 30-day content cleanup. No arbitrary send command. Private configuration uses Docker volumes; session volume is preserved. |
| Verification | Latest PostgreSQL-configured suite 340 passed, SQLite 333 passed/7 skipped; actual disposable HTTP/worker/history/source/evaluation checks. Earlier real text/authorization/pause evidence is retained separately. Group/media/history and E independent live acceptance remain separate gates. |

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
| B | Trusted allowlisted events, source revisions and context; synthetic fixtures and preserved business storage; provider interface plus deterministic default; offline evaluation harness; durable `proposals` + `model_call_traces` evidence | Real-model integration for live content. The deterministic provider refuses unknown live content with `EXTRACTION_NEEDS_REVIEW`; lifting that guard requires a separately authorized real-model batch. |
| C | Persistent ownership, inbox/jobs, source/context invalidation, locks and bounded recovery | Business confirmation/approval semantics; approved external actions, outbox, final checks and unknown-outcome reconciliation. Existing Replay internal confirmation is not WAHA external execution. |
| D | Implemented local QR/selection/consent/health/review screens and message/sync panel, generated types and owner APIs | Refine independent live UX; keep connection/readiness/review/sync completion separate. Stable display IDs are not canonical SourceRef IDs unless source_message_id/revision exist. |
| E | Stage evidence, safe HTTP smoke, disposable fault runner, independent real text evidence | Independent acceptance and review; Internet/router/logout/QR recovery and missing-content restoration are not established. |

## Not implemented or not established

- Complete historical coverage, automatic unconsented backfill, reconstruction of missing revisions or guaranteed ordering/completeness. Bounded snapshot import/explicit gap lookup are implemented.
- Original media reading/transcription/OCR/GenAI, complete chat mirroring, group management and cross-engine behavior. Basic group/media metadata is implemented; physical formats need acceptance.
- General live AI extraction, automatic confirmed work orders or automatic formal calendar writes. AI remains proposals/drafts; no external send adapter, approvals/outbox/send echoes or unknown-send reconciliation.
- Production authentication, multi-merchant self-service onboarding, production secret management, public deployment hardening and alert delivery. Local connector screens are implemented.
- Independent E signoff or a guarantee that no messages were lost. Historical unresolved counts are runtime metadata; use current status rather than old dated counts.

## Remaining batch plan

Official Cloud API remains outside the plan. Next is own-account unified history/group/media-metadata acceptance and E's independent review. Original-file/GenAI design is deferred by the owner. Later multi-session/deployment and approved sending batches need explicit scope; C's approval/outbox/reconciliation precedes any send adapter. Preserve batch development and unified acceptance; this summary does not authorize additional deployment or sends.
