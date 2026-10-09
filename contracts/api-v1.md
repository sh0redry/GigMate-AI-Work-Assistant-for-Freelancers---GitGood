# Business API agreement

Status: **wire baseline 0.1.0, v0.2 subset implemented**. Prefix: `/api/v1`. JSON and server-session HttpOnly/SameSite=strict cookies; CSRF tokens and trusted-origin checks protect mutations. COOKIE_SECURE defaults false for loopback HTTP development; this is not production authentication. Resources are scoped by trusted account context, never client account IDs. Implemented routes are listed in generated [OpenAPI](openapi.json).

Implemented: login/logout; order list/detail/change list/schedule confirmation; conversation detail/latest-revision message list; task/calendar list; replay connection status; synthetic replay and custom-event ingestion. Changes include context_version and computed conflict_ids in the response view. Not implemented: rejection/edit commands, actions/approvals/cancellation/outbox/sending, and calendar start/end filters or task work_order filters. The inventory below is a target; OpenAPI is the implemented subset. All skeleton lists use stable ID order, with the UI sorting displayed messages by occurred_at. Larger-volume database-side pagination is future work.

POST /auth/login is a pre-auth development credential flow with origin checking; logout requires session/CSRF. These auth endpoints do not use business idempotency keys. POST /replay accepts scenario=reschedule or available; POST /replay/events accepts a normalized replay event; both require session, CSRF and Idempotency-Key. Optional WAHA reception and monitoring are implemented as described below.

## Opt-in WAHA ingress and monitoring

`POST /connectors/waha/{connection_id}/events` authenticates the pinned provider raw body using SHA-512 HMAC, not browser cookies/CSRF or a browser idempotency key. A private server configuration and database binding resolve ownership. It accepts bounded strict provider JSON, then checks active account/connector and allowlisted conversation before content storage. HTTP 200 with ConnectorReceipt/durable_acceptance true means reception committed; it does not mean AI processing, customer confirmation or external sending. Invalid signature is 401, mapping/allowlist/consent denial is 403, identity/order/source conflicts are 409, oversized bodies are 413, unsupported/invalid payloads are 422, disabled configuration/database failures are 503. No credentials or raw content appear in errors. Body timestamps are authenticated but no unsigned timestamp header is used as freshness proof. Persistent identities, local revision ordering and 30-day expiry constrain replay; remote gaps still require reconciliation.

`GET /connectors` requires the existing authenticated account and returns paginated ConnectorStatus values: persistent state, freshness, sync timestamp, safe counters and queue counts. No connector administration, credentials or chat identifiers are returned. State older than 120 seconds is stale and not live-connected; the local monitor polls every 30 seconds. The original `/connection-status` continues to describe Replay, preserving its clients. The local capability probe is separate and never claims durable acceptance. See [stage-three setup/limits](../docs/en/role-a-stage3-acceptance.md).

## Operational health and recovery

`GET /health` checks database access and, when WAHA is configured, private-binding readability/validity and persisted ownership mapping. An unusable binding returns 503. Replay without WAHA configuration remains supported. This does not prove real webhook delivery. `/health` 在启用 WAHA 时同时验证私有绑定及持久归属；绑定不可用返回 503，无 WAHA 配置的 Replay 保持支持，不能代替真实回调验收。

WAHA status additionally exposes API/provider/worker/monitor health samples, `pipeline_ready`, independent `review_required`/`unresolved_issues`, and safe metrics. `live_connected` remains a provider-session signal; clients should use `pipeline_ready` for sampled end-to-end readiness. Worker samples expire after 30 seconds, the other samples after 120 seconds. Timings are nullable and cover measured retained jobs only. Generated client types include these additions.

`GET /connectors/{connection_id}/recovery-issues` is a session-authenticated, account-scoped paged list of safe outage/review metadata, with no provider IDs or content. Review acknowledgement is operator-only; recovery never automatically acknowledges missing-message risk or imports history. Signed rejected business input is counted after rollback where persistence is available; forged signatures do not create diagnostics. See [recovery operations and limits](../docs/en/role-a-recovery-acceptance.md).

## Responses and errors
Details: `{"data": <resource>, "request_id": "<uuid>"}`. Lists: `{"items": [], "next_cursor": null, "request_id": "<uuid>"}`. Default limit 20, maximum 100; opaque cursor; deterministic ordering with stable ID tie-breaker. Calendar list additionally filters start/end UTC times and includes date-only entries for the user's date range.

Errors: `{"error": {"code": "VERSION_CONFLICT", "message": "Refresh and review the current version", "details": {}}, "request_id": "<uuid>"}`. Do not include private content in details.

| Status | Codes | Behavior |
| --- | --- | --- |
| 401 | UNAUTHENTICATED | No valid session |
| 403 | FORBIDDEN, CONSENT_REVOKED, CSRF_REJECTED | Denied mutation; no permission bypass retry |
| 404 | NOT_FOUND | Missing or another account's resource |
| 409 | VERSION_CONFLICT, APPROVAL_STALE, IDEMPOTENCY_CONFLICT, SCHEDULE_CONFLICT, OPEN_ORDER_EXISTS (planned) | Refresh and review; never overwrite or accept overlap |
| 422 | VALIDATION_FAILED | Invalid shape or domain input |
| 429 | RATE_LIMITED | Respect retry instruction |
| 503 | CONNECTOR_UNAVAILABLE | No claim of send success |

## Initial endpoint inventory

| Method and path | Input | Result and rule |
| --- | --- | --- |
| GET /work-orders | cursor, limit, optional status | Account-owned work orders |
| POST /work-orders | CreateWorkOrderCommand (planned) | Merchant-confirmed creation, usually from an AI creation proposal; ownership, consent and conflict checks; see below |
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

## Work orders from conversation to confirmation (planned, role C)

Status: **planned contract, not implemented**. Proposed 2026-10-09 for team review (see Issue #7). Implementation adds source models/routes and regenerated OpenAPI; until then OpenAPI remains authoritative for implemented behavior. Everything below is a local database operation: none of it requires the WhatsApp connector or a model to be available, and nothing is sent without merchant approval.

Today every work order comes from the development seed, so a live conversation has no order to attach changes to. This section covers the whole path: recognizing jobs in a conversation, creating the order, following up on missing information, and confirming. The rule stays the same throughout: **AI proposes, deterministic rules check, the merchant decides.**

### 1. Recognizing jobs (role B decides, role C enforces)

For every accepted message, the extraction provider receives the conversation's open orders and open creation proposals and returns one result **per job**:
- the message adds to an existing open order or creation proposal → update that one;
- the message starts a new job → a new creation proposal (assignment value such as `new_work_order`, owned by role B's contract);
- one message mentions several jobs → several proposals;
- the provider cannot tell whether it is the same job or a new one → `needs_review`, and the merchant is asked ("新的一单，还是加到『证件照拍摄』？").

Role C never guesses whether two messages are the same job. It merges or separates only as the provider's result says, and anything uncertain goes to the merchant. Merging and splitting happen only at proposal stage, before any order exists.

Relative dates are resolved by the provider against the message's send time and the account timezone (for example 下星期六 → a `DateOnly` 10/17). A resolved relative date is stored as `proposed` with customer confirmation `pending`, never as confirmed, because such phrases are often ambiguous in Cantonese.

Role B's evaluation manifest should cover: consecutive messages about one job, consecutive messages about two jobs, two jobs in one message, a job that is ambiguous, and relative dates.

A creation proposal stays usable until a newer proposal for the **same job** supersedes it or one of its source messages is edited or revoked. An unrelated message such as 谢谢 does not invalidate it. Change proposals for existing orders keep the stricter context rule of schedule confirmation.

### 2. Creating the order

`POST /work-orders` with `CreateWorkOrderCommand`: `conversation_id`, `summary` (1–120 characters, "customer + concrete job", for example 陈小姐证件照拍摄; task titles reuse it), optional `schedule` (`TimedSchedule` or `DateOnly`, timezone required), optional `address`, optional `from_proposal_id`, and `confirm_additional_order` (default false). The merchant may edit every suggested value before submitting. Manual creation uses the same command without a proposal. `Idempotency-Key` is required.

Checks, in one transaction serialized per account:
1. The session account owns the conversation; it is allowlisted and consent is active.
2. If `from_proposal_id` is given, the proposal belongs to the same account and conversation, is a creation proposal, is not superseded, and has not been used.
3. Safety net for manual creation: if the conversation already has an open order and the command has no proposal, creation returns 409 `OPEN_ORDER_EXISTS` with those orders unless `confirm_additional_order` is true. Orders created from distinct proposals do not need this flag, because the provider has already separated the jobs.
4. A timed schedule must start in the future and must not overlap confirmed appointments (excluding cancelled and completed orders); a conflict returns 409 `SCHEDULE_CONFLICT` with the conflicting order IDs.

Missing information is never guessed: omitted values are stored with field status `missing`, and nothing is filled from a template or a model. The proposal is marked used, field sources come from the proposal's messages (none for merchant-entered values), and an audit record is written; all of this commits together. An order created by mistake is cancelled through the planned status command, keeping history; there is no hard delete.

### 3. Follow-up until everything is confirmed

The open items live **on the work order**, not on a draft. Key fields in P0 are a timed schedule and an address. An item is open while its field is `missing`, `proposed` with customer confirmation not yet `confirmed`, or deferred by the customer. Each open item records what is needed (value, customer confirmation of a resolved date, or a later answer).

- **Pending order.** An order with open key items is `pending_confirmation`. A `DateOnly` schedule adds a tentative all-day calendar entry so the merchant sees the day; tentative entries do not count in conflict checks.
- **Asking.** While items are open, the system keeps one clarification draft per order that asks only for those items and echoes resolved values for checking (for example 「你说的下星期六是 10/17 吗？几点方便？见面地址是？」). Body: the provider's `draft_text` if present, otherwise a role C template. The draft records why it exists (missing items, a schedule conflict, or a date to verify) so the interface can show it.
- **After each new message.** Any accepted message, edit or revocation — including a reply the merchant types directly in WhatsApp — replaces the non-dispatched draft with one regenerated from the order's current open items. Nothing is forgotten: if nothing changed, the new draft asks the same question; if the customer answered part of it, the new draft asks only for what remains; if everything is answered, no draft remains. The merchant never approves text written against an older context.
- **Customer answers.** An answer becomes an ordinary proposal; the field moves to `proposed` and is confirmed through the normal confirm flow, never written directly.
- **Customer defers** (还未确定，之后再确认). The provider marks the item deferred with the date the customer gave, or the account default of 3 days. The order stays `pending_confirmation` and a follow-up task is created in the memo format, for example `10/12 10:00 跟进 陈小姐证件照拍摄：确认时间`.
- **All key items confirmed.** The order moves to `confirmed` in the same transaction as the last confirmation, the tentative entry becomes a formal calendar event, and the preparation task is created (title format `MM/DD HH:MM 准备 HH:MM 的{summary}`).
- **No reply (P1, after P0).** If a draft is approved and sent but the customer does not answer within 24 hours, a follow-up task and a new draft for the remaining items are created, at most twice; after that the order is flagged 客人未回复 for the merchant to decide. This needs a scheduled worker check and is not part of P0.

### 4. Draft rules

- Stored as a `send_text` action in `pending_approval` with recipient, body, `bound_work_order_version`, `bound_context_version`, `expires_at` (24 hours) and message sources; `snapshot_hash` follows the `send_text` projection rule above.
- At most one non-dispatched clarification draft per order; regeneration cancels the previous one with reason `superseded`. A draft is unique per triggering event, so a retried worker job cannot create a second one.
- An unapproved draft becomes `expired` at `expires_at` and is never sent; the open items stay on the order and the next new message regenerates a draft.
- Cancelling or completing an order cancels its non-dispatched drafts.
- Rejecting or cancelling a draft only changes local state and must succeed even when the connector is disabled or unavailable.
- Drafts are approve-or-reject in P0. Editing a draft before approval needs its own command (new action revision and snapshot hash) and is not part of this contract.

### 5. Model additions this requires

| Owner | Addition |
| --- | --- |
| B | Creation proposals per job (`new_work_order` assignment, several per message, link to an existing open proposal or order); relative-date resolution; deferral with a follow-up date; evaluation cases listed in section 1 |
| C | `CreateWorkOrderCommand` and route; open follow-up items on the work order; action trigger reason; `pending_confirmation` → `confirmed` when the last key item is confirmed; tentative date-only calendar entries; follow-up and preparation tasks |
| D | Creation proposal review (accept, edit, or answer "same job or new job"); open items and follow-up tasks on the order; draft reason shown with each approval |

Errors: 403 `CONSENT_REVOKED`, 404 `NOT_FOUND`, 409 `APPROVAL_STALE` (proposal superseded, used, or its source changed), 409 `OPEN_ORDER_EXISTS`, 409 `SCHEDULE_CONFLICT`, 422 `VALIDATION_FAILED` (including a schedule in the past).

## Ingestion and execution boundary

Connector webhook ingestion is an adapter endpoint with separate key/signature authentication, not a browser endpoint. The opt-in WAHA route implements normalization, allowlisting and transactional reception/jobs. Real signed status callbacks and earlier live capability checks are verified; complete durable text/edit/revoke/ACK and outage checks remain independent live acceptance work. No full-history or universal engine compatibility is claimed.

There is no browser `send arbitrary text` endpoint. An approved action is queued and revalidated by the worker before connector dispatch. Provider acceptance, delivery acknowledgment and customer confirmation are separate. A timeout after possible submission becomes result_unknown. Reconciliation and definitely-not-submitted retries are internal services, not a permission shortcut.

## Skeleton transition

Pydantic domain generation, implemented OpenAPI, frontend type generation, ownership/CSRF/version tests and drift checks are present. Extend the remaining inventory through source models/routes and regenerate contracts. This document records behavior and planned scope; OpenAPI reflects actual implementation.
