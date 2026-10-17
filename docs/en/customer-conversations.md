# Customer conversations — first batch

2026-10-18 · Role A · [中文](../zh/customer-conversations.md).

This additive frontend workspace uses the installation's existing same-origin API. It does not create another WhatsApp session, seed a database, change an allowlist or enable a model. Connection settings, existing order workflows and the original sending panel remain available.

## Start and use

Use your own existing WAHA installation and account. From `apps/web` in PowerShell:

```powershell
$env:GIGMATE_REAL_API_URL = 'http://127.0.0.1:18702'
npm run dev
```

Open the printed root URL (normally http://127.0.0.1:5173), sign in and choose **Customer chats**. The production page has one backend; it has no environment picker. A replay deployment without a connection remains empty here. An old backend is not upgraded by starting the frontend. The previously existing local installation remains the user's responsibility; this batch does not migrate or recreate it.

1. Choose an installation connection and an authorised chat. Search and direct/group filters affect the local catalogue only. Eight chat previews are checked per visible list page, about every 15 seconds. New-message indicators are session-local GigMate observations, not WhatsApp unread counts or read receipts.
2. The current chat automatically reads its latest 50-message page about every three seconds while visible. Earlier pages can be loaded, up to ten pages/500 rows per window. Refresh re-reads the displayed window, including edits, revocations and delivery status. It follows page shifts back to the old anchor within that cap. This is bounded polling of the existing timeline API, **not a new server delta/push service or a complete-history guarantee**. Background document tabs stop polling; private read denial clears content, local text drafts and the selection. Temporary network/status failure retains permitted old content and unsent text while disabling sending.
3. Reading earlier messages does not jump to the bottom when a new message arrives. A new-message button jumps explicitly. Loading earlier history preserves the reading offset. History-origin/snapshot evidence remains labelled; the existing explicit import workflow is still in connection settings.
4. Prepare replies below the messages. Sending permission, reply origin/type, quoted target, fixed policies and records are compact disclosures **only in the new workspace**. Text, media, voice, video and the existing additional sending types use `WahaSend` unchanged at its service boundary. A message quote supplies an owned snapshot ID. No read receipt, file download, OCR or model request starts just because a chat is opened.
5. The separate sending permission, saved draft, exact final review/approval, gateway outbox and unknown-result reconciliation remain required. Do not use a new request to discover whether an unknown send succeeded. Pending identities remain in the existing recovery mechanism. During mutations, navigation/chat changes are blocked. Unsent text and manual/assisted origin are kept in component memory per connection/chat, including when returning from an order; refreshing/logging out discards them. Attachment and quote selections must be checked again after changing chats.
6. Select an order explicitly in the side panel; one chat can have several orders. Click a field's source to locate its exact message revision. Changed/revoked evidence gets a warning, not an assertion of current customer confirmation. Older sources are searched within the same window cap. Missing sources require order review or explicit history import. Clicking **Open order to handle it** retains a return-to-chat entry. Order fields and proposed changes also offer an additive **View source in customer chat** link.
7. Select current incoming revision-backed customer text and choose **Review a new order from selected messages**. Existing order creation receives the conversation and source hints; it still reads the current original messages, requires explicit critical-field sources and confirmation, and does not auto-create or auto-confirm. Editing/revoking a selected source removes the old selection rather than silently selecting a new revision. Arbitrary message-to-existing-order assignment is not introduced; use the existing business review/assignment workflow.
8. Explicit attachment controls reuse the owned media preview/processing/review component. Actual availability still depends on the server, file/source checks, consent, configured modality and provider. Audio transcription is not enabled by this frontend.

## AI integration: implemented versus target

The side panel reads the existing `GET /work-orders/{id}/drafts` API. It offers only unexpired `proposed` rows with a proposal ID, exact selected order/conversation, matching order version and `execution_authority: false`. The backend remains authoritative for all current bindings. Merchant-authored stored text is not presented as newly generated AI output.

The merchant reviews the full suggestion, explicitly accepts replacing the current text, and calls `POST /drafts/{id}/consume` once. Returned identity, text, proposal, context and order bindings are checked. A valid result enters the shared composer as `agent_assisted`; it does not save a send action, approve or dispatch. New message changes invalidate the local suggestion review; refresh it explicitly. Unknown adoption is not automatically consumed again. Old backends returning 404 keep manual chat/reply use available and explain that draft support needs an upgrade.

**Not implemented by this batch:** a fresh conversational reply generator, a model-powered polish operation, automatic triggering or an unrestricted Agent. The existing B draft API stores merchant text or reuses a proposal; it must not be relabelled as fresh generation. These are frontend and handoff deliverables, not completed live-model acceptance.

### B/C handoff for fresh reply generation (design target only)

Agree a separately versioned, generated contract before implementing a new endpoint. A future request needs an owned conversation, explicitly selected order when applicable, exact source message revisions, expected context/order versions, generation intent (reply or polish), merchant input and a durable request identity. A new customer may have no order; ambiguous multi-order context must ask for selection, never choose the first order. Do not reuse the existing order-only draft command with invented fields.

B owns the real provider, bounded contextual input, prompt-injection handling, price/token/call bounds, cancellation/submission and unknown-cost reconciliation. C owns business semantics and what may be proposed. A owns connector identity, media access and the final external sending boundary. D can consume the eventual generated contract in the existing side panel/composer. A generation result must be a proposal with server-owned sources, context/order bindings, expiry and `execution_authority: false`; accepting it never grants sending permission. Unknown requests retain their original identity and are not blindly paid for again. No endpoint or generated schema is claimed for this design target.

## Compatibility and verification

No backend, migration or public wire schema is changed. Missing chat/timeline/mapping/sending capabilities fail clearly; no synthetic fallback is injected into the product. Conversation IDs are mapped explicitly from choices or received timeline records, never equated with chat IDs. The optional composer props and compact rendering retain the existing panel's default behaviour.

Automated evidence for this batch: frontend **195 passed** including 19 new synthetic conversation/API/DOM cases; TypeScript and production build pass. Generated API drift check, formatting, source-contract export, applicable Ruff checks and baseline are recorded in the implementation status. The bundle-size advisory remains. The reused timeline and draft-binding backend suites have **51 passed / 2 skipped** with temporary SQLite; this is not PostgreSQL locking evidence.

Browser checks use a disposable loopback synthetic service with no WAHA/database/model connection and no sending support. Real phone delivery, receipt timing, model accuracy, exact live media support and long-running reconnect remain manual acceptance; no real message or paid model request was sent by the agent.

## Unified manual acceptance on your own installation

After the installation owner upgrades the backend when needed:

- Check that the root URL proxies to the intended real installation; use its own login and authorised test chat. Confirm the connection and freshness before sending.
- From another consenting test account send new text, edit it and revoke it. Check that the open chat updates without manual reload, with one bubble per identity and no revived text. Scroll upwards and test a new message without a forced jump.
- Switch chats and return: text must not cross recipients, and the correct unsent text returns. Restore a pending/unknown send through its original gateway identity; never submit again to test success.
- Manually prepare, review, approve and send test text, an attachment and a quoted reply. Verify actual receipt/content on the phone. Do not confuse accepted with delivered.
- With a valid B proposal-backed draft available, explicitly adopt it, verify it has not sent, edit/review it and approve through the existing gateway. If the old backend lacks drafts, record that item as blocked rather than passed. Fresh generation/polish is outside this delivered interface.
- Select sources for new-order review and locate order fields back in the conversation. Edit a selected source: require fresh selection/review. Confirm multi-order selection and return navigation.
- Test revoke/pause, disconnect/reconnect, account logout, phone layout and three UI languages. Source/customer text is not translated. Retain only sanitised result metadata; never commit real chats, attachments, numbers, QR or credentials.
