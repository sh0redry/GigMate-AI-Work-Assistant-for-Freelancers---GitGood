# Engineering documentation

Milestone: **0.2 replay skeleton**. Updated: **2026-10-01**.

The replay skeleton and optional local WAHA durable ingress/monitoring are implemented and tested. The current sending development branch adds opt-in owned multi-type sending and exact preauthorization; real-account/B/PostgreSQL acceptance remains pending. Production onboarding and general live extraction remain separate gates. Start with the current WAHA handoff below; earlier stage documents retain development history.

| Document | Purpose |
| --- | --- |
| [Overview](overview.md) | Scope and exclusions |
| [Architecture](architecture.md) | Modules, ownership, state flow and reliability |
| [WAHA merged integration acceptance](role-a-integration-acceptance.md) | Canonical frontend/backend control, migration and unified team acceptance |
| [WAHA message sync acceptance](role-a-message-sync-acceptance.md) | Bounded history, timeline, gaps, media metadata and complete batch acceptance |
| [Owned media and A/B handoff](role-a-media-ingestion.md) | Explicit download/preview, durable tasks, source review and B processing seam |
| [WAHA multi-type sending](role-a-waha-sending.md) | Separate send permission, immutable approval/outbox, fixed automatic policies, recovery and own-account batch acceptance |
| [Getting started](getting-started.md) | Checks available now and next implementation gate |
| [Contributing](contributing.md) | Task, branch, review and completion rules |
| [Role A responsibilities](role-a-responsibilities.md) | Ingestion, authentication, durable events, monitoring and handoffs |
| [WAHA implementation and team handoff](role-a-waha-handoff.md) | Current capability matrix, limits, role integrations and remaining plan |
| [Team local WAHA development](role-a-team-local-development.md) | Own-account setup, safe verification and concrete B/C/D/E development framework |
| [WAHA setup API acceptance](role-a-setup-api-acceptance.md) | Implemented local connection/QR/chat-control routes, async intent and D/E handoff |
| [WhatsApp connection flow](whatsapp-connection-flow.md) | QR pairing, conversation allowlists, live events and historical sync |
| [Role A development roadmap](role-a-development-roadmap.md) | Coherent development batches, dependencies, failure tests and unified acceptance |
| [Role A recovery acceptance](role-a-recovery-acceptance.md) | Component health, fault recovery, manual gap review and reproducible tests for E |
| [Equal collaboration](team-governance.md) | Equal permission target, peer review and independent onboarding gate |
| [Decisions](adr/README.md) | Accepted choices and change conditions |
| [Contracts](../../contracts/README.md) | Canonical schemas, API agreement and synthetic fixtures |
| [D final web delivery](role-d-final-acceptance.md) | Current product pages, calendar export, blocked dependencies and actual evidence |
| [Role D module roadmap](role-d-development-roadmap.md) | D-01 through D-05, API dependencies and scope |
| [D-02 business workspace acceptance](role-d-stage2-acceptance.md) | Current frontend features, failure guards and actual evidence |
| [Frontend user guide](role-d-frontend-user-guide.md) | Connection, business review and replay operation |
| [Desktop feasibility](role-d-desktop-feasibility.md) | PWA/Tauri/Electron and backend deployment boundaries |
| [Kyrie beginner guide](kyrie-learning-guide.md) | Plain-language story, code lessons, exercises and version context |
| [Kyrie file map](kyrie-file-atlas.md) | Small starting path followed by full reference |
| [Implementation status](implementation-status.md) | Completed work, evidence and outstanding capability |

Accepted ADRs govern architecture; Pydantic models generate domain shapes and implemented OpenAPI; event/AI schemas remain independently maintained. A schema-valid object is not proof of authorization. Update source models, generated contracts/types, samples, tests and bilingual rules together. Module contacts coordinate work without exclusive permissions or approval rights.

The earlier kickoff proposal is retained as planning history and superseded by this baseline for engineering requirements. The supplied v2 product plan remains source context, not proof of implemented features or user results.

- [D-03 reply approval acceptance](role-d-stage3-acceptance.md)
