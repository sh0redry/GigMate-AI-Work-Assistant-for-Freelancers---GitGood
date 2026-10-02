# Role A: ingestion, authentication, durable events and connection monitoring

Updated: 2026-10-02. This defines the user's Role A scope, without assigning other contributors. The implemented baseline remains v0.2 synthetic replay. See the [development roadmap](role-a-development-roadmap.md) and [Chinese counterpart](../zh/role-a-responsibilities.md).

A converts chat changes into trusted, stable, traceable events, delivers them reliably to downstream processing, and exposes whether ingestion is working.

## Responsibilities and current boundaries

2026-10-02: independent offline normalization/failure verification delivered; see [A-01 acceptance](role-a-stage1-acceptance.md). Live capabilities below remain pending and existing services are not wired to WAHA.

See [WhatsApp connection flow](whatsapp-connection-flow.md) for pairing, selected conversations and live/historical message access.

| Area | Responsibility | Current state |
| --- | --- | --- |
| Ingestion | Maintain Replay; test and pin WAHA version/engine; normalize creation, edits, revocations, acknowledgments and session events | Replay text/create/edit/revoke implemented; live adapter, acknowledgment and session consumption pending |
| Authentication | Verify webhook source, resolve account/session/conversation ownership server-side, enforce consent and allowlist before content storage or model calls | Development sessions, CSRF, ownership and allowlists implemented; production identity and provider webhook authentication pending |
| Event contract | Maintain schema, provider mappings, stable identities/revisions, fixtures and capability records | Wire 0.1.0 defines five types; schema presence does not imply service support |
| Durable reception | Atomically persist inbox/message revisions/context/jobs; handle duplicates, conflicts, failure and recovery | PostgreSQL Inbox/Job and separate worker implemented; live identity and ordering reconciliation pending |
| Monitoring | Persist connection state and sync progress; expose account-scoped status, freshness and safe errors | Current endpoint returns synthetic_replay/replay/live_connected=false, not live monitoring |
| Environment | Maintain ingestion configuration, Compose, setup and recovery instructions | Reuse modular backend, separate worker and PostgreSQL; no new queue service by default |
| Testing with E | Supply reproducible inputs, fault injection, safe diagnostics and fixes | Some replay failures tested; live webhook/reconnect/send-echo cases pending |

## First deliverable: a stable event contract

Start from the [existing event schema](../../contracts/events/message-event.schema.json). Event schemas have independent versions. Pydantic governs domain shapes; generate domain/OpenAPI/frontend types instead of editing outputs.

| Fields | Meaning and required guarantees |
| --- | --- |
| schema_version / event_type | Format version, event kind and explicit support boundaries |
| event_id | Stable across redelivery of the same event; test and persist mappings when the provider lacks stable identity |
| account_id / session_id / conversation_id | Resolve through trusted server configuration for live ingress, not self-reported ownership |
| provider_message_id / payload.message_id | External and internal message identities, distinct from event identity |
| message_revision | Preserve source revisions for creation/edit/revoke |
| occurred_at / received_at | Provider and receipt time; UTC RFC3339 ending Z; receipt order does not establish revision order |
| direction / source | Incoming/outgoing and app/API/replay provenance, including future send echoes |
| payload | Strict type-specific structure; unknown business values remain missing |

Creation, editing and revocation of one message share message identity but have different event identities and advancing revisions. Only redelivery of the same change is deduplicated. A delivery acknowledgment is neither a customer message nor customer confirmation.

Deliver field definitions, provider mapping, capabilities, positive/negative fixtures, duplicate/conflict/order policies, compatibility impact, automated validation and consumer examples. Coordinate strict clients; breaking changes require major schema/API migration.

## Security and queue boundary

Sequence: authenticate source → resolve ownership → consent/allowlist → validate normalized event → atomically deduplicate, save inbox/message revisions, advance context, invalidate old proposals and create job → acknowledge after commit → worker processing.

Unauthorized content must not enter storage, logs or model calls. Keep connector credentials on the server. Logs contain IDs, stage, latency and stable error codes, not complete text, addresses, tokens, QR material or session files.

A and C jointly define transaction, uniqueness, lease, retry and version semantics. The current worker uses PostgreSQL SKIP LOCKED, a 30-second lease and a three-attempt processing-failure limit with backoff. Parameter changes require evidence. SQLite cannot prove PostgreSQL locking. Current replay rejects non-contiguous revisions with VERSION_CONFLICT; it does not automatically reconcile live out-of-order delivery. Reception success does not mean extraction, confirmation or sending completed.

## Handoffs

| Role | A supplies | Other role / joint decision |
| --- | --- | --- |
| B | Allowlisted input, source/context versions and reproducible fixtures | Extraction/prompts/evaluation; AI emits proposals and drafts only |
| C | Trusted ownership, context changes, durable events/jobs and connection state | Domain confirmation/approval/execution; jointly review contracts, migrations and transactions |
| D | Account-scoped status, freshness, capabilities and errors | UI; no connector administration or credentials in frontend |
| E | Fault steps, synthetic inputs, replay paths, diagnostic IDs and fixes | Acceptance cases, defects, user testing and evidence |

A does not directly confirm orders, mutate formal calendars or execute AI drafts. Ambiguous multi-order assignment requires downstream review. Future sending requires C's approval snapshots, transactional outbox, final revalidation and reconciliation; A supplies adapter capabilities and outcome information.

## Failure testing with E

| Case | Expected result | Evidence boundary |
| --- | --- | --- |
| Duplicate / changed content under same identity | No repeated records/jobs; identity conflict rejected | Replay tests exist |
| Missing authentication, CSRF, cross-account, allowlist or consent failure | Reject before business storage/model calls | Some development/replay tests; live webhook pending |
| Edit/revoke/stale task | Source revisions retained, old proposal cannot be confirmed | Revocation/stale-context tests; live ordering pending |
| Worker crash/expired lease/concurrent claims/persistent failure | Recovery without repeated proposals, bounded retries | Tests exist; concurrency requires PostgreSQL |
| Database unavailable | No false receipt acknowledgment; resume durable work after recovery | Worker poll test exists; complete reception-transaction cases need additions |
| Disconnect/reconnect/late state events | Accurate state and reconciliation of missing/duplicate events | Live implementation pending |
| API echo / unknown send outcome | No reply loop or retroactive cancellation; no blind resend | External execution pending |

Use synthetic repository fixtures. Live verification needs separately authorized test accounts and private local evidence; track only sanitized findings and synthetic reproductions.

## Development and acceptance policy

For current and future development, complete as many related tasks as practical within the authorized milestone as one coherent batch, then conduct unified acceptance. Include implementation, migrations, contract/type generation, normal/failure tests, configuration and bilingual documentation. Do not ask the user to accept each file or small task.

Run checks and fix failures during development; unified acceptance does not defer automatic validation. Continue independent work when accounts/credentials/environment block a dependency, but mark blocked live checks honestly. Keep changes reviewable, preserve independent code review, avoid unauthorized scope expansion, and do not commit/push without request.

Deliver a batch checklist, behavior/contract/migration changes, actual commands/results, failure matrix, recovery evidence, limitations and remaining tasks. Update [implementation status](implementation-status.md) and [Chinese progress](../zh/progress.md) with actual evidence.
