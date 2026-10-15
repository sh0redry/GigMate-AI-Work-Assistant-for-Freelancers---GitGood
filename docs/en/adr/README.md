# Architecture decisions

| ID | Decision | Status |
| --- | --- | --- |
| [0001](0001-foundation.md) | Foundation architecture and stack | Accepted baseline |
| [0002](0002-contract-authority.md) | Documentation and contract authority | Accepted baseline |
| [0003](0003-approval-and-execution.md) | Approval and durable execution | Accepted baseline |
| [0004](0004-equal-collaboration.md) | Equal permissions and peer review | Accepted policy; platform setup pending |
| [0005](0005-bounded-waha-observations.md) | Bounded history snapshots, context-only provenance and deferred media reading | Local batch implemented; independent live acceptance pending |
| [0006](0006-owned-media-handoff.md) | Explicit owned media storage and A/B processing boundary | A implementation; B real model and physical acceptance pending |
| [0007](0007-owned-waha-sending.md) | Owned multi-type sending and exact merchant preauthorization | Authorized development batch; physical/B/PostgreSQL/independent acceptance pending |

Accepted means agreed; each ADR separately records implementation status. v0.2 implements replay, generated contracts and internal confirmation; the current opt-in WAHA sending branch implements a separate sending gateway, while generic business action execution and live acceptance remain pending. Changes require a superseding ADR or amendment with impact and migration notes. Module contacts coordinate review without exclusive approval rights.
