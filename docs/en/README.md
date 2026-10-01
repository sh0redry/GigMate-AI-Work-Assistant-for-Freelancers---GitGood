# Engineering documentation

Baseline: **0.1**. Updated: **2026-10-01**.

These agreements prepare a single-maintainer repository for later contributors. The documentation and contracts are established; application implementation and live connector verification remain pending.

| Document | Purpose |
| --- | --- |
| [Overview](overview.md) | Scope and exclusions |
| [Architecture](architecture.md) | Modules, ownership, state flow and reliability |
| [Getting started](getting-started.md) | Checks available now and next implementation gate |
| [Contributing](contributing.md) | Task, branch, review and completion rules |
| [Decisions](adr/README.md) | Accepted choices and change conditions |
| [Contracts](../../contracts/README.md) | Canonical schemas, API agreement and synthetic fixtures |

Accepted ADRs govern architecture; schemas govern shapes and enums; the API agreement governs endpoint behavior. A schema-valid object is not proof of authorization or business correctness. Update related contracts, examples, tests and documentation together. The current repository maintainer owns the baseline until module owners are assigned.

The earlier kickoff proposal is retained as planning history and superseded by this baseline for engineering requirements. The supplied v2 product plan remains source context, not proof of implemented features or user results.
