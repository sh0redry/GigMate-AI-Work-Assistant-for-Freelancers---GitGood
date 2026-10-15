# Role D frontend development roadmap

## Current delivery plan — 2026-10-16

The current candidate follows merged #25/main **53991dc** and implements the remaining web delivery as one batch. [Final acceptance and handoff](role-d-final-acceptance.md) is the current state; the dated notes below are historical.

| Module | Candidate status |
| --- | --- |
| D-01 | Existing connection/consent and independent manual sending retained with accurate permission/capability wording |
| D-02 | Existing order/source/concrete-time confirmation retained; fictional input path removed from runtime |
| D-03 | #25 merged; local approval remains separate from external send; missing-item reasons and legacy unknown-operation safeguards added |
| D-04 | Customer-backed creation form/review and lifecycle review/target commands prepared; server gates keep saves off pending accepted C #26/#27. Missing/address/assignment/defer states and current original review are visible; unsupported commands are not fabricated |
| D-05 | Mobile/keyboard layout, honest availability/help, internal month/agenda/tasks, owned `.ics`, manifest/icon and container compilation prepared; physical/native install/accessibility and complete live acceptance remain E/team gates |
| Final | One business frontend with no test picker/public credential/demo input. Local disposable testing precedes PR; C/B/A pending functions are explicitly disabled, not claimed complete |

C/D must compare accepted source-generated contracts before enabling the prepared creation/status payloads. A/C must implement durable business-to-send association before the UI can execute or display linked send receipts; B/C must define assignment/defer/real-proposal commands. This does not authorize the frontend to implement those business rules itself. Native exe/macOS packaging and external calendar sync remain separate work.

2026-10-12 · Owner: Kyrie. The user asked to formalize the previously unrecorded D modules; these labels are now the working plan, not a claim of a historical agreed task list. [Chinese counterpart](../zh/role-d-development-roadmap.md).

| Module | Scope | Dependency / state |
| --- | --- | --- |
| D-01 Connection and consent | Login, QR, connection health, authorized chat selection, pause/revoke and recovery | Delivered in merged PRs #4/#15/#16; physical pairing and native Windows acceptance remain independent |
| D-02 Business workspace | Search/status list, sourced order details, all linked conversations, change review and internal schedule confirmation, tasks and calendar | Implemented against main `bbb0074`; [acceptance](role-d-stage2-acceptance.md); independent PR review pending |
| D-03 Reply approval and execution results | Exact recipient/body/source/expiry/version review; approve, reject/cancel, history and truthful dispatch/unknown results | C's action APIs (#22 merged into main c5c22ef), then A/C durable send/reconciliation; do not label approved as sent |
| D-04 Order creation and lifecycle | Manual/AI creation proposal review, missing/deferred items, ambiguous assignment, cancel/complete commands | C's planned creation/status contracts and B's reviewed creation proposals; Issue #7. No fake local writes |
| D-05 Mobile, accessibility and distribution | Cross-device acceptance, keyboard/assistive review, deployment and optional installable/desktop shell | Product demo removal and user-facing cleanup started; the full module is not accepted. Builds on previous modules; baseline responsive/keyboard work belongs in each delivery. [Desktop feasibility](role-d-desktop-feasibility.md), not implemented packaging |

Deliver each authorized module as one coherent batch with behavior, failure tests, API type checks and matching English/Chinese evidence. A frontend screen does not authorize a backend capability or model/external execution. Preserve session/CSRF, account ownership, allowlists, source revisions and expected versions. Do not add connector administration/credentials to frontend or silently retry uncertain writes. Proposed APIs stay targets until OpenAPI exposes them.

D-02 deliberately does not call action/creation/status routes absent from main. The user-facing workspace now has only business and connection navigation; the fixed replay code/API remain for isolated developer verification, with no UI entry. A conversation can contain multiple orders, and an order can link multiple conversations. The current ChangeView lacks a conversation ID: resolve its context only from exact, unrevoked canonical source revisions in one linked conversation; ambiguous/missing provenance stays blocked. Server validation remains authoritative.

As of the review on 2026-10-12, #21 media processing cancellation permits reissue while a previous model submission can be uncertain; #22 regenerates reply work for API echoes. Both received changes-requested reviews and were left unmerged. Each original head passed its existing PostgreSQL suite, while one added targeted regression per PR failed. Passing CI does not erase those findings. If both later merge, use an additive Alembic merge revision for their divergent migration heads rather than rewriting either migration.

2026-10-13 D-03 follow-up: the approval UI, local reject/cancel, original-key unknown-request recovery and history are implemented on a stacked candidate with C #22 and D-02 #24. [Acceptance](role-d-stage3-acceptance.md). #22 still requires its repeated-reissue fix; A #23 remains Draft with an upload-consent race and no C sending bridge. Approval UI delivery does not finish the real-send part of D-03. #21 merged as e066b0c with model activation still off.

2026-10-14 update: #24 conflicts resolved against main e066b0c; #25 synchronizes that parent, guards storage getter/read/write/cleanup failures and adds a migration join for the composed candidate. #23’s 99228ca is updated and peer-reviewed, so its earlier upload-race note above is historical; C/A sending bridge and #22 reissue repair still remain pending.

2026-10-14 current dependency update: C #22’s repeated-reissue fix is independently accepted and merged as c5c22ef. #24 now follows main; #25 preserves both published merge revisions with additive 0015_d03_approval_heads. Approval UI remains under review and real sending/C-A integration remains pending. Earlier dated defect reports above are historical.

2026-10-14 current integration: #24 and #23 are merged into main **4177d1a**. #25 is Ready for teammate review/merge and adds **0016_d03_sending_heads** to preserve both published migration histories. A’s separate sending gateway is accepted; the C business approval to A send bridge remains pending. The conservative same-context repeat guard remains. Older dated states above are historical.
