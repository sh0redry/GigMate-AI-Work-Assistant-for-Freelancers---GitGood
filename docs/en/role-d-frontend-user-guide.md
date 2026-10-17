# GigMate frontend user guide

2026-10-18 additive frontend batch: [Customer conversations](customer-conversations.md) offers authorised chat selection, bounded live-message polling, the existing manual sending gateway and order-source navigation. It does not upgrade an older backend. Existing valid B drafts can be reviewed and consumed; fresh reply generation/polishing and automatic replies remain separate integration work.

Current candidate: 2026-10-17, based on main `14aa34e`. [中文](../zh/role-d-frontend-user-guide.md). Technical evidence: [BCD delivery](bcd-product-delivery.md).

## Run on your own laptop

The team does not need a shared server for local use: your laptop runs the web page, API, worker and database. While PR34 is unmerged, use its branch (`codex/d-api-cache-glass`), which includes `infra/compose.text.yaml`; an older main checkout does not include that file. Keep your own `.env` private and ignored, never copy another teammate's key or database. Configure optional model credentials/gates/pricing as described in [BCD delivery](bcd-product-delivery.md).

Start Docker Desktop, open a terminal **at the root of that checkout**, then run:

```text
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.text.yaml up --build -d --wait
```

Open http://127.0.0.1:18080. Use the account/password seeded in your own database; changing `.env` later does not reset an existing password. Keep existing WAHA overlays in the same Compose command if your local WhatsApp setup uses them; the text overlay alone does not install or pair WhatsApp. To stop the base/text stack, use the same options followed by `down`, without `-v`, to retain data. `restart` alone does not reload changed `.env` values; use `up -d --wait` again. Do not run two clones against the same Compose project/volume unintentionally.

## Five useful words

An **order** is one job's notebook; a chat can contain several orders. A **proposal** is information awaiting review, not an already changed arrangement. **Customer confirmation** is the customer's agreement; your own sent message cannot replace it. **Merchant approval** records your decision; it does not prove a reply was sent. A **receipt** records an operation; accepted, delivered and unknown have different meanings.

## Sign in, choose language, connect

Use your configured GigMate account, separate from your WhatsApp phone account. The product has no public test password, replay entry or isolated-environment picker. Developers test in disposable environments before submitting changes.

The header offers **中文 / English / 粵語**. Switching keeps login, page and form input. It translates UI labels, not customer messages, saved business text or approved reply bodies. Only the preference is persisted; no business text goes to a translation service.

Open **WhatsApp connection**, scan when needed, discover/select work chats and explicitly save processing permission. Reading/processing and sending are separate permissions. Pause, revoke and reconnect against the current state. If no connection exists, contact the integration maintainer instead of repeatedly scanning.

## Create the first order

Choose **New order**, select an authorised conversation and read customer messages. Enter a summary. Keep unknown time/address missing; a date alone remains tentative. Values require selecting their current customer source messages. Confirm explicitly if another open order already exists in the chat.

Review the order, check the confirmation box, then save. **AI new-order suggestions** appear only when the backend has valid current suggestions. Selecting one fills the summary only. You still review sources, enter critical values and confirm creation. AI never silently creates a formal order. Manual creation works without a suggestion.

## Daily workflow

1. **Workspace:** search orders, inspect current arrangements, source messages and proposed changes. Edited/revoked sources invalidate old evidence.
2. **Business management:** review the summary; assign ambiguous messages, defer missing information, manage materials/commitments/questions, set hours/breaks and review other field proposals.
3. **Reply approvals:** check recipient, exact full text, sources, versions and expiry. Approve or reject with a reason. Editing creates a new revision requiring fresh approval.
4. **Business management → Edit replies & check sending:** choose the approved draft and exact connection, review and submit. Separately authorise that chat for sending first. Submission does not prove delivery; inspect its linked receipt.
5. **Calendar & tasks:** month/agenda views and `.ics` export for current formal confirmed appointments with valid sources. Import into your own calendar. Rescheduling does not continuously sync and repeated import may duplicate entries.
6. **Business management → Handle tasks:** review completion/cancellation. Finish prerequisites first. Task completion does not confirm a customer's time/address.
7. **Delivery checklist:** resolve unfinished items, or explicitly acknowledge closing anyway. Finish/cancel and archive while retaining history.

The question helper supports today's/tomorrow's schedule, waiting customers and decisions. It reads owned records and links to orders; unsupported questions are not guessed.

## Interrupted or uncertain results

Refresh reads status and does not approve/send again. Keep the original ID, body and versions when a submitted response is lost. Read current records, then explicitly check the original operation. No receipt does not prove no execution. Do not create another order or send to test success. Unknown model calls keep their request ID for operator checking; you can still handle work manually from customer sources.

Definite initial checklist/dependency rejection leaves no partial write and permits a reviewed correction. Read disabled-button reasons rather than bypassing permission.

## Refresh and cache

The visible business page checks about every five seconds. Every read still authenticates with the server. Unchanged answers keep the same UI; changed branches update without clearing the page. An offline old view cannot authorise new confirmations. Logout/account changes clear session snapshots.

## Limits

The optional text model needs explicit server configuration and consent. Without it, use the manual workflow. Live speech/image recognition, media-to-order promotion, freely generated Agent auto-replies, continuous external calendar sync and standalone exe/app installers are not delivered. Browser installation is a shortcut and still needs a running backend. Local synthetic tests do not replace real-phone/vendor/deployment acceptance.

See [developer setup](getting-started.md), [Kyrie's beginner guide](kyrie-learning-guide.md) and [file atlas](kyrie-file-atlas.md).
