# Engineering documentation

Milestone: **0.2 replay skeleton**. Updated: **2026-10-01**.

These agreements prepare the repository for later contributors. A runnable synthetic replay skeleton is implemented. Live connector verification, general extraction and external sending remain pending.

| Document | Purpose |
| --- | --- |
| [Overview](overview.md) | Scope and exclusions |
| [Architecture](architecture.md) | Modules, ownership, state flow and reliability |
| [Getting started](getting-started.md) | Checks available now and next implementation gate |
| [Contributing](contributing.md) | Task, branch, review and completion rules |
| [Role A responsibilities](role-a-responsibilities.md) | Ingestion, authentication, durable events, monitoring and handoffs |
| [WhatsApp connection flow](whatsapp-connection-flow.md) | QR pairing, conversation allowlists, live events and historical sync |
| [Role A development roadmap](role-a-development-roadmap.md) | Coherent development batches, dependencies, failure tests and unified acceptance |
| [Equal collaboration](team-governance.md) | Equal permission target, peer review and independent onboarding gate |
| [Decisions](adr/README.md) | Accepted choices and change conditions |
| [Contracts](../../contracts/README.md) | Canonical schemas, API agreement and synthetic fixtures |
| [Implementation status](implementation-status.md) | Completed work, evidence and outstanding capability |

Accepted ADRs govern architecture; Pydantic models generate domain shapes and implemented OpenAPI; event/AI schemas remain independently maintained. A schema-valid object is not proof of authorization. Update source models, generated contracts/types, samples, tests and bilingual rules together. Module contacts coordinate work without exclusive permissions or approval rights.

The earlier kickoff proposal is retained as planning history and superseded by this baseline for engineering requirements. The supplied v2 product plan remains source context, not proof of implemented features or user results.
