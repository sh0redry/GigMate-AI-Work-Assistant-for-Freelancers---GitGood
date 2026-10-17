# Frontend API audit (2026-10-17)

## Current integration — 2026-10-17

PR32 is merged in main `14aa34e`; the separate preview snapshot/generator/types are removed. All business clients now use canonical implemented OpenAPI. This candidate adds owned new-order suggestions, explicit suggestion consumption, task status and bounded read-only workspace queries; the reviewed text provider is opt-in. Chat choices now expose the owned conversation mapping. See [current delivery](bcd-product-delivery.md). The inventory below records the earlier preparation stage; its pending-route wording is historical.


Audited main `e912977` and pending PR32 `d696735623b52e4d5135c40a62e6b0744cc31af2`. This is a route inventory, not proof of live-provider acceptance. A owns connections, synchronization, attachments and the sending gateway; C owns business commands, planning and approvals. B/E processing uses worker/provider contracts and has no independent product HTTP controls on this main. A defined schema alone does not establish a working feature.

## Implemented main

| Operation | Frontend use or deliberate exclusion |
| --- | --- |
| `GET /api/v1/actions` | Reply approvals: ApprovalsWorkspace / approvals-api |
| `GET /api/v1/actions/{action_id}` | Reply approvals: ApprovalsWorkspace / approvals-api |
| `POST /api/v1/actions/{action_id}/approve` | Reply approvals: ApprovalsWorkspace / approvals-api |
| `POST /api/v1/actions/{action_id}/cancel` | Reply approvals: ApprovalsWorkspace / approvals-api |
| `POST /api/v1/actions/{action_id}/reissue` | Reply approvals: ApprovalsWorkspace / approvals-api |
| `POST /api/v1/actions/{action_id}/reject` | Reply approvals: ApprovalsWorkspace / approvals-api |
| `POST /api/v1/auth/login` | App: login, logout, server capability gate |
| `POST /api/v1/auth/logout` | App: login, logout, server capability gate |
| `GET /api/v1/calendar-events` | CalendarWorkspace / WorkOrderWorkspace |
| `GET /api/v1/calendar-events/{event_id}.ics` | CalendarWorkspace / WorkOrderWorkspace |
| `GET /api/v1/connection-status` | Legacy read alias; workspace uses /connectors |
| `GET /api/v1/connectors` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `POST /api/v1/connectors/waha/{connection_id}/events` | Signed provider callback; server only |
| `GET /api/v1/connectors/{connection_id}/chats` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `PUT /api/v1/connectors/{connection_id}/chats` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `GET /api/v1/connectors/{connection_id}/chats/{chat_id}/timeline` | History and sync: WahaMessages / waha-sync-api |
| `GET /api/v1/connectors/{connection_id}/media/attachments` | Attachment preview/review: WahaMedia / waha-media-api |
| `GET /api/v1/connectors/{connection_id}/media/attachments/{attachment_id}` | Attachment preview/review: WahaMedia / waha-media-api |
| `GET /api/v1/connectors/{connection_id}/media/attachments/{attachment_id}/content` | Attachment preview/review: WahaMedia / waha-media-api |
| `GET /api/v1/connectors/{connection_id}/media/attachments/{attachment_id}/evidence` | Attachment preview/review: WahaMedia / waha-media-api |
| `POST /api/v1/connectors/{connection_id}/media/attachments/{attachment_id}/review` | Attachment preview/review: WahaMedia / waha-media-api |
| `GET /api/v1/connectors/{connection_id}/media/capabilities` | Attachment preview/review: WahaMedia / waha-media-api |
| `POST /api/v1/connectors/{connection_id}/media/jobs` | Attachment preview/review: WahaMedia / waha-media-api |
| `GET /api/v1/connectors/{connection_id}/media/jobs/{job_id}` | Attachment preview/review: WahaMedia / waha-media-api |
| `POST /api/v1/connectors/{connection_id}/media/jobs/{job_id}/cancel` | Attachment preview/review: WahaMedia / waha-media-api |
| `POST /api/v1/connectors/{connection_id}/media/jobs/{job_id}/reconcile` | Attachment preview/review: WahaMedia / waha-media-api |
| `POST /api/v1/connectors/{connection_id}/operations` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `GET /api/v1/connectors/{connection_id}/operations/{operation_id}` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `POST /api/v1/connectors/{connection_id}/operations/{operation_id}/reconcile` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `POST /api/v1/connectors/{connection_id}/pause` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `GET /api/v1/connectors/{connection_id}/qr` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `GET /api/v1/connectors/{connection_id}/recovery-issues` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `POST /api/v1/connectors/{connection_id}/recovery-issues/review` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `POST /api/v1/connectors/{connection_id}/resume` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `GET /api/v1/connectors/{connection_id}/sending/actions` | WhatsApp sending: WahaSend / waha-send-api |
| `GET /api/v1/connectors/{connection_id}/sending/actions/{action_id}` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/actions/{action_id}/approve` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/actions/{action_id}/cancel` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/actions/{action_id}/reconcile` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/actions/{action_id}/review-unknown` | WhatsApp sending: WahaSend / waha-send-api |
| `GET /api/v1/connectors/{connection_id}/sending/capabilities` | WhatsApp sending: WahaSend / waha-send-api |
| `GET /api/v1/connectors/{connection_id}/sending/context/{chat_id}` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/drafts` | WhatsApp sending: WahaSend / waha-send-api |
| `GET /api/v1/connectors/{connection_id}/sending/permission` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/permission` | WhatsApp sending: WahaSend / waha-send-api |
| `GET /api/v1/connectors/{connection_id}/sending/policies` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/policies` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/policies/{policy_id}/revoke` | WhatsApp sending: WahaSend / waha-send-api |
| `GET /api/v1/connectors/{connection_id}/sending/requests/{request_key}` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/requests/{request_key}/cancel` | WhatsApp sending: WahaSend / waha-send-api |
| `POST /api/v1/connectors/{connection_id}/sending/uploads` | WhatsApp sending: WahaSend / waha-send-api |
| `GET /api/v1/connectors/{connection_id}/sending/uploads/{upload_id}/content` | WhatsApp sending: WahaSend / waha-send-api |
| `GET /api/v1/connectors/{connection_id}/setup` | Connection and consent: ConnectionWorkspace / waha-live-api |
| `GET /api/v1/connectors/{connection_id}/source-gaps` | History and sync: WahaMessages / waha-sync-api |
| `GET /api/v1/connectors/{connection_id}/sync-jobs` | History and sync: WahaMessages / waha-sync-api |
| `POST /api/v1/connectors/{connection_id}/sync-jobs` | History and sync: WahaMessages / waha-sync-api |
| `GET /api/v1/connectors/{connection_id}/sync-jobs/{job_id}` | History and sync: WahaMessages / waha-sync-api |
| `POST /api/v1/connectors/{connection_id}/sync-jobs/{job_id}/cancel` | History and sync: WahaMessages / waha-sync-api |
| `GET /api/v1/conversations` | Original sources: OrderCreation / business workspace / review |
| `GET /api/v1/conversations/{conversation_id}` | Original sources: OrderCreation / business workspace / review |
| `GET /api/v1/conversations/{conversation_id}/messages` | Original sources: OrderCreation / business workspace / review |
| `POST /api/v1/replay` | Developer synthetic replay only; excluded from delivery UI |
| `POST /api/v1/replay/events` | Developer synthetic replay only; excluded from delivery UI |
| `GET /api/v1/review-items` | ReviewWorkspace; reviewed PR32 adds assignment |
| `GET /api/v1/tasks` | CalendarWorkspace / WorkOrderWorkspace |
| `POST /api/v1/work-order-command-results/{key}/inspect` | InspectOrderAttempt: original-result verification |
| `GET /api/v1/work-orders` | OrderCreation / WorkOrderWorkspace; extended detail in reviewed business management |
| `POST /api/v1/work-orders` | OrderCreation / WorkOrderWorkspace; extended detail in reviewed business management |
| `GET /api/v1/work-orders/{order_id}` | OrderCreation / WorkOrderWorkspace; extended detail in reviewed business management |
| `GET /api/v1/work-orders/{order_id}/changes` | OrderCreation / WorkOrderWorkspace; extended detail in reviewed business management |
| `POST /api/v1/work-orders/{order_id}/changes/{change_id}/confirm` | OrderCreation / WorkOrderWorkspace; extended detail in reviewed business management |
| `POST /api/v1/work-orders/{order_id}/status` | OrderCreation / WorkOrderWorkspace; extended detail in reviewed business management |
| `GET /api/v1/workspace-capabilities` | App: login, logout, server capability gate |
| `GET /health` | Service monitoring; no business control |

## Prepared PR32, disabled by default

The historical preview snapshot (removed after PR32 merged) contains 14 pending paths, recursively copied schema dependencies and the pinned source commit. It is not implemented OpenAPI and is never registered by the running backend. Main generated types still come solely from canonical main Pydantic models. Run `npm run generate:api` for both independently generated type files; `check:api` checks both.

Business management prepares daily summary, working hours/breaks/buffers, schedule checks, materials/commitments/questions and their tasks, deferrals, rejection and additional change fields, completion checklist/acknowledgement, archive, assignment/dismissal and reply edit/send. Mutations show a separate explicit review with source/version and preserve an account-scoped original request journal on uncertain outcomes. Schedule PUT recovery only reads back the exact next-version settings; it never blindly repeats PUT. Associated A receipts are read using the current owned connector route and checked against chat/order/body before display. Gateway cancellation/reconciliation remains in the existing sending page.

`business_loop_reviewed` is false on main and on older servers that omit it. There is no frontend switch to enable it. Release owners must first merge a compatible C implementation, apply migrations, resolve PR32 cross-account linking/cancellation and paused-conversation writes, verify isolation/idempotency/ownership/source and permission revocation in independent acceptance, then intentionally advertise this capability. Assignment additionally needs `manual_assignment`; business sending additionally needs `business_sending`, an available connector, current separate permission and explicit review. PR32's own older capability response cannot accidentally activate these pages. Do not set the flag merely because routes exist.

Health, callbacks, replay and compatibility aliases intentionally have no duplicate product buttons. Unsupported creation/status/assignment controls are omitted, with status explained in the feature guide. No fake generation endpoint or automatic AI understanding is introduced.
