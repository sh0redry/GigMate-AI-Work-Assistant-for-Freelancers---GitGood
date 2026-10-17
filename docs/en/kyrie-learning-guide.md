# Kyrie's GigMate learning guide: start from zero

Updated 2026-10-18. [中文](../zh/kyrie-learning-guide.md). Learn the [user workflow](role-d-frontend-user-guide.md) first; you do not need to understand every technical word at once.

## Imagine a small shop

2026-10-18: **updated source files do not update an already-running program**.
The counter can use a new form while the office still follows an old manual,
which produces missing-interface errors. `scripts/start_product.py` now builds
the frontend, backend and worker together, checks the backend contract, and
offers one user entry on port 18780 only after those checks succeed.

A fictional demo deployment is different from the Python `.venv` dependency
folder. The user startup no longer launches the former; the latter contains
libraries needed by the startup tools, not fictional customers or orders.
Automated tests still use synthetic messages internally, without delivering a
second user-login website.

D's frontend is the counter. C's business backend is the office that checks ownership and updates the notebook. B's AI is an assistant that organises messages and suggests, but cannot sign for the merchant or send messages independently. A's connector is the phone line. A worker is a background colleague who can process persisted work even after the page closes.

An API is a service window. Types describe its form; a server capability says whether the window is implemented. Account permission says whether you may use it. A drawn button proves neither.

## Manual, assisted and automatic

Manual creation means you read the chat, enter values and confirm. AI assistance means the assistant prepares a suggestion, then you check and explicitly create the order. Automatic creation would let it write the formal notebook without you; this project does not allow AI to do that.

Selecting a new-order suggestion fills only the summary. You still check and enter critical values. Keep unknown values blank. Customer proposal, customer confirmation and merchant approval are separate signatures.

## A small vocabulary

| Term | Everyday meaning | Why it matters |
| --- | --- | --- |
| React component | A function drawing part of a page | Keeps login/calendar/order code manageable |
| TypeScript type | Instructions for filling a form | Catches mixed-up values and identifiers |
| Request / response | Submit a form / receive the office answer | The UI cannot declare its own save successful |
| Transaction | Finish all related paperwork, or roll it all back | Avoid an updated order with an outdated calendar |
| Source revision | Edition of a customer message | An edited address invalidates old evidence |
| Version | Number of updates to an order | Prevent overwriting someone else's changes |
| Context | Current round of the conversation | New messages can invalidate approval |
| Idempotency key | One operation's receipt number | Check the same receipt after lost responses |
| Receipt | Recorded processing result | No reply does not prove no execution |
| Lease | Temporary assignment of work to one worker | Avoid two workers claiming the same job |
| Lock | Temporarily reserve a database record | Protect checks and writes from races |
| Migration | Add a column to an existing notebook | Upgrade structure without deleting data |
| Commit | A labelled local save point | Explain and recover changes |
| PR | Ask teammates to review commits | Different from merge and deployment |

A chat ID and business conversation ID are like a phone number and a customer-file number. Use the server's mapping; similar-looking IDs are not interchangeable.

## Why the page stops flashing

Keep the notebook open and ask “has it changed?”. An ETag is the answer's fingerprint. 304 means unchanged; 200 supplies a new answer. Every read still checks permission and reads the database. The cache mostly reduces transfer and UI replacement, not all database work.

Session-memory snapshots are cleared on logout/account change. An offline old page cannot authorise a save. Structural sharing replaces changed sticky notes instead of tearing out the whole notebook.

## Why models wait outside database locks

Do not lock the office notebook while the assistant researches. Record the call ID, release locks, wait, then check ownership, consent, sources and versions again. Late/stale answers cannot become business updates.

A 20-second parent deadline ends the local child process. It does not prove the vendor never received the call or charged for it. Keep the ID and do not automatically call again. A loopback fake-vendor test does not prove real-model accuracy.

## Language and appearance

`i18n.ts` stores the current UI language; `locales.ts` holds interface translations. These change counter labels, not customer text or approved bodies. Only a language preference persists; no text goes to translation websites.

CSS variables such as `--accent` are a shared paint box. Glass navigation has a solid fallback; white content cards stay readable. Respect reduced motion/transparency. Appearance never grants permission.

## Reading order

1. `apps/web/src/App.tsx`: login, navigation, language.
2. `WorkOrderWorkspace.tsx` and `OrderCreation.tsx`: display and merchant review.
3. `workspace-api.ts` and `order-command-api.ts`: requests and original receipts.
4. `BusinessLoopWorkspace.tsx` and `ProductTools.tsx`: requirements, schedule, tasks and queries.
5. `apps/backend/src/gigmate/contracts.py`: shared form rules; do not hand-edit generated files.
6. `workorders.py` and `product_commands.py`: business checks and writes.
7. `worker.py` and `extraction/reviewed.py`: background work and optional models. Credentials stay server-side.

See the [file atlas](kyrie-file-atlas.md) and [developer setup](getting-started.md).

## Fifteen minutes a day

Trace one click from review to request to server to receipt. Then inspect why edited source messages invalidate approval. In a disposable environment, interrupt the service and recover the original operation without duplicating it. Switch languages and check input and customer text stay intact.

Use fictional data, never real chats, keys, QR codes or session files in learning artifacts. [Current delivery](bcd-product-delivery.md) separates implemented code from independent acceptance.
