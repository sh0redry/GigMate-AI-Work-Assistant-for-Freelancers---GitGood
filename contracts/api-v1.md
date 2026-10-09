# Business API agreement

Status: **wire baseline 0.1.0, v0.2 subset implemented**. Prefix: `/api/v1`. JSON and server-session HttpOnly/SameSite=strict cookies; CSRF tokens and trusted-origin checks protect mutations. COOKIE_SECURE defaults false for loopback HTTP development; this is not production authentication. Resources are scoped by trusted account context, never client account IDs. Implemented routes are listed in generated [OpenAPI](openapi.json).

Implemented: login/logout; order list/detail/change list/schedule confirmation; conversation detail/latest-revision message list; task/calendar list; replay connection status; synthetic replay and custom-event ingestion. Changes include context_version and computed conflict_ids in the response view. Not implemented: rejection/edit commands, actions/approvals/cancellation/outbox/sending, and calendar start/end filters or task work_order filters. The inventory below is a target; OpenAPI is the implemented subset. All skeleton lists use stable ID order, with the UI sorting displayed messages by occurred_at. Larger-volume database-side pagination is future work.

POST /auth/login is a pre-auth development credential flow with origin checking; logout requires session/CSRF. These auth endpoints do not use business idempotency keys. POST /replay accepts scenario=reschedule or available; POST /replay/events accepts a normalized replay event; both require session, CSRF and Idempotency-Key. Optional WAHA reception and monitoring are implemented as described below.

## Opt-in WAHA ingress and monitoring

`POST /connectors/waha/{connection_id}/events` authenticates the pinned provider raw body using SHA-512 HMAC, not browser cookies/CSRF or a browser idempotency key. A private server configuration and database binding resolve ownership. It accepts bounded strict provider JSON, then checks active account/connector and allowlisted conversation before content storage. HTTP 200 with ConnectorReceipt/durable_acceptance true means reception committed; it does not mean AI processing, customer confirmation or external sending. Invalid signature is 401, mapping/allowlist/consent denial is 403, identity/order/source conflicts are 409, oversized bodies are 413, unsupported/invalid payloads are 422, disabled configuration/database failures are 503. No credentials or raw content appear in errors. Body timestamps are authenticated but no unsigned timestamp header is used as freshness proof. Persistent identities, local revision ordering and 30-day expiry constrain replay; remote gaps still require reconciliation.

`GET /connectors` requires the existing authenticated account and returns paginated ConnectorStatus values: persistent state, freshness, sync timestamp, safe counters and queue counts. No connector administration, credentials or chat identifiers are returned. State older than 120 seconds is stale and not live-connected; the local monitor polls every 30 seconds. The original `/connection-status` continues to describe Replay, preserving its clients. The local capability probe is separate and never claims durable acceptance. See [stage-three setup/limits](../docs/en/role-a-stage3-acceptance.md).

## Operational health and recovery

Local WAHA product setup routes are now implemented for one preprovisioned owned connection: GET setup/qr/chats, POST operations, GET operation, POST operation reconcile, PUT chats and POST pause/resume. Source models WahaSetup/WahaControlResult/WahaChoice and commands generate the route contracts. Mutations require browser session/CSRF, trusted ownership and control_version; operations additionally require Idempotency-Key and commit durable intent before 202. Unknown outcomes use explicit read-only reconciliation, not resend. Chat choices are opaque application UUIDs, not provider IDs. See [English setup agreement](../docs/en/role-a-setup-api-acceptance.md) and [Chinese counterpart](../docs/zh/role-a-setup-api-acceptance.md) for exact paths, limits and UI sequence. No product UI, arbitrary account/session creation, history import, AI or external-send routes are implied.

`GET /health` checks database access and, when WAHA is configured, private-binding readability/validity and persisted ownership mapping. An unusable binding returns 503. Replay without WAHA configuration remains supported. This does not prove real webhook delivery. `/health` 在启用 WAHA 时同时验证私有绑定及持久归属；绑定不可用返回 503，无 WAHA 配置的 Replay 保持支持，不能代替真实回调验收。

WAHA status additionally exposes API/provider/worker/monitor health samples, `pipeline_ready`, independent `review_required`/`unresolved_issues`, and safe metrics. `live_connected` remains a provider-session signal; clients should use `pipeline_ready` for sampled end-to-end readiness. Worker samples expire after 30 seconds, the other samples after 120 seconds. Timings are nullable and cover measured retained jobs only. Generated client types include these additions.

`GET /connectors/{connection_id}/recovery-issues` is a session-authenticated, account-scoped paged list of safe outage/review metadata, with no provider IDs or content. Review acknowledgement is operator-only; recovery never automatically acknowledges missing-message risk or imports history. Signed rejected business input is counted after rollback where persistence is available; forged signatures do not create diagnostics. See [recovery operations and limits](../docs/en/role-a-recovery-acceptance.md).

## Responses and errors

Local message synchronization: [implemented batch](../docs/en/role-a-message-sync-acceptance.md), [ADR 0005](../docs/en/adr/0005-bounded-waha-observations.md). Owner-scoped POST /connectors/{id}/sync-jobs uses explicit consent, current control_version and a stable request key; GET job status, POST cancel, GET authorized chat timeline and source-gap metadata are implemented. Media-only durable receipts carry acceptance_kind=observation, without normalized Inbox/Jobs. Live text receipts retain normalized_event; the five-type 0.1 event contract remains text-only. Timeline display IDs are stable; canonical source_message_id/revision are null for snapshots. Historical/media context does not grant proposal confirmation or execution. Regenerate clients for new choice kind, discovery pagination and receipt/timeline/sync fields. Downloaded files, OCR/transcription/GenAI, full history and sending are not implemented.

WAHA integration uses the implemented `/api/v1/connectors/{id}` setup/control routes described in [setup acceptance](../docs/en/role-a-setup-api-acceptance.md) and [merged integration](../docs/en/role-a-integration-acceptance.md). `inspect`/`discover` do not increment control_version; authorization and provider mutations do. POST `/{id}/recovery-issues/review` requires session/CSRF, owner-scoped unique issue_ids and confirmed_no_import=true; it atomically acknowledges only recovered issues as reviewed_no_import, retaining audit history. Generated OpenAPI governs command shapes. The retired Vite bridge is not an API surface.
Details: `{"data": <resource>, "request_id": "<uuid>"}`. Lists: `{"items": [], "next_cursor": null, "request_id": "<uuid>"}`. Default limit 20, maximum 100; opaque cursor; deterministic ordering with stable ID tie-breaker. Calendar list additionally filters start/end UTC times and includes date-only entries for the user's date range.

Errors: `{"error": {"code": "VERSION_CONFLICT", "message": "Refresh and review the current version", "details": {}}, "request_id": "<uuid>"}`. Do not include private content in details.

| Status | Codes | Behavior |
| --- | --- | --- |
| 401 | UNAUTHENTICATED | No valid session |
| 403 | FORBIDDEN, CONSENT_REVOKED, CSRF_REJECTED | Denied mutation; no permission bypass retry |
| 404 | NOT_FOUND | Missing or another account's resource |
| 409 | VERSION_CONFLICT, APPROVAL_STALE, IDEMPOTENCY_CONFLICT, SCHEDULE_CONFLICT | Refresh and review; never overwrite or accept overlap |
| 422 | VALIDATION_FAILED | Invalid shape or domain input |
| 429 | RATE_LIMITED | Respect retry instruction |
| 503 | CONNECTOR_UNAVAILABLE | No claim of send success |

## Initial endpoint inventory

| Method and path | Input | Result and rule |
| --- | --- | --- |
| GET /work-orders | cursor, limit, optional status | Account-owned work orders |
| GET /work-orders/{id} | resource ID | Confirmed fields, proposals, provenance and version |
| GET /work-orders/{id}/changes | pagination | Requirement changes and customer-confirmation state |
| POST /work-orders/{id}/changes/{change_id}/confirm | ConfirmChangeCommand | Merchant-approved internal mutation; conflict checks and atomic dependent updates |
| POST /work-orders/{id}/changes/{change_id}/reject | RejectCommand | Record rejection; preserve history |
| GET /actions | pagination, optional state | Review queue or execution history |
| GET /actions/{id} | ID | Server-produced snapshot hash and provenance |
| POST /actions/{id}/approve | ApproveActionCommand | Approve exact current snapshot, create durable work; return 202, not sent |
| POST /actions/{id}/reject | RejectActionCommand | Cancel non-dispatched action, record reason |
| POST /actions/{id}/cancel | RejectActionCommand | Cancel only before dispatch; cannot retract sent content |
| GET /tasks | pagination, optional work_order_id | Account-owned tasks and dependencies |
| GET /calendar-events | start, end, cursor, limit | Formal/tentative events and date-only deadlines |
| GET /conversations/{id}/messages | pagination | Allowlisted account-owned message timeline |
| GET /connection-status | none | Connector/session state and last successful sync |

Command schemas are in [models.schema.json](domain/models.schema.json). Work-order path and linked resource ownership must agree. Commands are not arbitrary write payloads. A calendar change inside a work-order confirmation requires explicit merchant intent and cannot silently replace unrelated events. A future draft edit endpoint needs a new contract before use; action revision and hash must change.

Mutating POSTs require Idempotency-Key. Scope keys by account, command and target; same key/body returns the recorded result, changed body returns409. Keep the record through action archival and at least the prototype retention period. expected_version refers to the work-order version; action commands additionally bind expected_context_version, expected_action_revision and snapshot_hash. Server verifies stored snapshot, consent and all ownership.

For send_text snapshots, hash exactly these fields from the stored action: id, account_id, work_order_id, conversation_id, kind, revision, recipient, body, bound_work_order_version, bound_context_version, expires_at, sources. Encode JSON as UTF-8, preserve string code points without Unicode normalization, sort object keys recursively, omit separator whitespace, and preserve array order; prefix the SHA-256 lowercase hex digest with `sha256:`. The projection contains strings and integers, not floating point values. Execution state, approval actor/time, provider IDs and delivery status are not part of the content snapshot. Other action kinds require a separately defined projection before implementation.

## Ingestion and execution boundary

Connector webhook ingestion is an adapter endpoint with separate key/signature authentication, not a browser endpoint. The opt-in WAHA route implements normalization, allowlisting and transactional reception/jobs. Real signed status callbacks and earlier live capability checks are verified; complete durable text/edit/revoke/ACK and outage checks remain independent live acceptance work. No full-history or universal engine compatibility is claimed.

There is no browser `send arbitrary text` endpoint. An approved action is queued and revalidated by the worker before connector dispatch. Provider acceptance, delivery acknowledgment and customer confirmation are separate. A timeout after possible submission becomes result_unknown. Reconciliation and definitely-not-submitted retries are internal services, not a permission shortcut.

## Skeleton transition

Pydantic domain generation, implemented OpenAPI, frontend type generation, ownership/CSRF/version tests and drift checks are present. Extend the remaining inventory through source models/routes and regenerate contracts. This document records behavior and planned scope; OpenAPI reflects actual implementation.
