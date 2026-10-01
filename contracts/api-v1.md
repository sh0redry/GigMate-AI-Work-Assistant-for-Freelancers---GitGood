# Business API agreement

Status: **wire baseline 0.1.0, v0.2 subset implemented**. Prefix: `/api/v1`. JSON and server-session HttpOnly/SameSite=strict cookies; CSRF tokens and trusted-origin checks protect mutations. COOKIE_SECURE defaults false for loopback HTTP development; this is not production authentication. Resources are scoped by trusted account context, never client account IDs. Implemented routes are listed in generated [OpenAPI](openapi.json).

Implemented: login/logout; order list/detail/change list/schedule confirmation; conversation detail/latest-revision message list; task/calendar list; replay connection status; synthetic replay and custom-event ingestion. Changes include context_version and computed conflict_ids in the response view. Not implemented: rejection/edit commands, actions/approvals/cancellation/outbox/sending, and calendar start/end filters or task work_order filters. The inventory below is a target; OpenAPI is the implemented subset. All skeleton lists use stable ID order, with the UI sorting displayed messages by occurred_at. Larger-volume database-side pagination is future work.

POST /auth/login is a pre-auth development credential flow with origin checking; logout requires session/CSRF. These auth endpoints do not use business idempotency keys. POST /replay accepts scenario=reschedule or available; POST /replay/events accepts a normalized replay event; both require session, CSRF and Idempotency-Key. No public provider webhook exists yet.

## Responses and errors

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

Connector webhook ingestion is an adapter endpoint with separate key/signature authentication, not a browser endpoint. Map the pinned provider's body to the normalized event schema, allowlist before business storage, persist accepted context and durable jobs, then acknowledge. Provider route/payload/signature details remain unverified until LIVE-01.

There is no browser `send arbitrary text` endpoint. An approved action is queued and revalidated by the worker before connector dispatch. Provider acceptance, delivery acknowledgment and customer confirmation are separate. A timeout after possible submission becomes result_unknown. Reconciliation and definitely-not-submitted retries are internal services, not a permission shortcut.

## Skeleton transition

Pydantic domain generation, implemented OpenAPI, frontend type generation, ownership/CSRF/version tests and drift checks are present. Extend the remaining inventory through source models/routes and regenerate contracts. This document records behavior and planned scope; OpenAPI reflects actual implementation.
