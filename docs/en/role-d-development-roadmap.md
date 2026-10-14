# Role D frontend development roadmap

2026-10-12 · Owner: Kyrie. The user asked to formalize the previously unrecorded D modules; these labels are now the working plan, not a claim of a historical agreed task list. [Chinese counterpart](../zh/role-d-development-roadmap.md).

| Module | Scope | Dependency / state |
| --- | --- | --- |
| D-01 Connection and consent | Login, QR, connection health, authorized chat selection, pause/revoke and recovery | Delivered in merged PRs #4/#15/#16; physical pairing and native Windows acceptance remain independent |
| D-02 Business workspace | Search/status list, sourced order details, all linked conversations, change review and internal schedule confirmation, tasks and calendar | Implemented against main `bbb0074`; [acceptance](role-d-stage2-acceptance.md); independent PR review pending |
| D-03 Reply approval and execution results | Exact recipient/body/source/expiry/version review; approve, reject/cancel, history and truthful dispatch/unknown results | C's action APIs (PR #22 under requested changes), then A/C durable send/reconciliation; do not label approved as sent |
| D-04 Order creation and lifecycle | Manual/AI creation proposal review, missing/deferred items, ambiguous assignment, cancel/complete commands | C's planned creation/status contracts and B's reviewed creation proposals; Issue #7. No fake local writes |
| D-05 Mobile, accessibility and distribution | Cross-device acceptance, keyboard/assistive review, deployment and optional installable/desktop shell | Product demo removal and user-facing cleanup started; the full module is not accepted. Builds on previous modules; baseline responsive/keyboard work belongs in each delivery. [Desktop feasibility](role-d-desktop-feasibility.md), not implemented packaging |

Deliver each authorized module as one coherent batch with behavior, failure tests, API type checks and matching English/Chinese evidence. A frontend screen does not authorize a backend capability or model/external execution. Preserve session/CSRF, account ownership, allowlists, source revisions and expected versions. Do not add connector administration/credentials to frontend or silently retry uncertain writes. Proposed APIs stay targets until OpenAPI exposes them.

D-02 deliberately does not call action/creation/status routes absent from main. The user-facing workspace now has only business and connection navigation; the fixed replay code/API remain for isolated developer verification, with no UI entry. A conversation can contain multiple orders, and an order can link multiple conversations. The current ChangeView lacks a conversation ID: resolve its context only from exact, unrevoked canonical source revisions in one linked conversation; ambiguous/missing provenance stays blocked. Server validation remains authoritative.

As of the review on 2026-10-12, #21 media processing cancellation permits reissue while a previous model submission can be uncertain; #22 regenerates reply work for API echoes. Both received changes-requested reviews and were left unmerged. Each original head passed its existing PostgreSQL suite, while one added targeted regression per PR failed. Passing CI does not erase those findings. If both later merge, use an additive Alembic merge revision for their divergent migration heads rather than rewriting either migration.
