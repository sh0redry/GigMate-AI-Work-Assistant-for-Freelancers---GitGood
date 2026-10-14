# WAHA sending batch 1: interfaces and unified acceptance

## PR #22/main compatibility update — 2026-10-14

The sending branch now includes main `c5c22ef` and C's approval actions, including repeated-expiry reissue recovery. Both Replay and live extraction can create C review drafts; these remain business proposals, not `WahaSendAction` or sending consent. No automatic approval-to-send bridge is enabled. Own WAHA API echoes still advance context and supersede pending reviews without another model call, question or send. The shared worker now uses main's `OWN_SEND_ECHO` diagnostic instead of the earlier sending-branch `API_SEND_ECHO`; the suppression behavior remains intact.

Additive **0014_merge_approval_send** joins unchanged `0013_merge_approval_media` and `0013_merge_media_send`. This is the new single head; upgrade to `head` and run Alembic `check` before rebuilding API/worker. Existing approved C records, sending permission versions/cancellation fences, media-stop markers and audit history must remain intact. Migration regressions cover both previously published merge heads. No original installation or permission was changed. The dated #21/#23 notes below retain their historical verification scope. Real models, C/A execution bridging, physical sending and independent acceptance remain pending.

## PR #21 compatibility update — 2026-10-13

This branch now includes main `e066b0c`, including PR #21's final media processor seam, PDF resource isolation and persistent content-stop decision. Processing/reconciliation and sending outbox requests remain separate identities: no stopped model output becomes sending approval, and a send acceptance is not model extraction success. All eleven sending adapters and explicit approval/fixed-policy paths remain in scope; the real B model stays disabled.

Additive **0013_merge_media_send** joins the unchanged shared `0011_waha_multitype_sending` and `0012_waha_media_stop` revisions. Upgrade to `head` and run Alembic `check` before rebuilding API/worker; either previously installed branch can advance to the merged head. Migration regressions preserve replay rows, send permission versions/cancellation fences and legacy media stop evidence. No permissions are granted and no private installation/session/database was upgraded by this batch.

The previously disclosed upload revocation race is fixed. Ownership/allowlist are checked before streaming and again under account/connection serialization before writing a file/row. The original control/send-permission versions must also match, so pause/regrant or send-revoke/regrant cannot silently resume an upload. `SEND_UPLOAD_AUTHORIZATION_CHANGED` (403) requires a fresh explicit upload after checking authorization. Tests verify revoked chat, pause, send revocation and both regrant paths leave zero upload rows/blobs. Existing no-resend, original late receipt, API echo and media-stop regressions are retained. Real phone/codec/Agent/C-bridge acceptance is still separate.

2026-10-10 · `Andy_WAHA_multitype_sending`, based on media PR #21's `a5aa0a1`. The owner authorized multi-type sending with manual, Agent-assisted and Agent-automatic entry points. This development branch adds A's sending gateway; it has not enabled or deployed sending in the original installation. [Chinese instructions](../zh/role-a-waha-sending.md) and [ADR 0007](adr/0007-owned-waha-sending.md).

## Implemented scope

| Kind | First-batch behavior |
| --- | --- |
| text | Text and links, up to 4,096 characters; remote link previews disabled |
| image | JPEG/PNG/WebP, optional caption |
| file | PDF, UTF-8 TXT/CSV, DOCX/XLSX/PPTX; other accepted uploads can also be delivered as documents |
| audio | Ogg/MP3/WAV/M4A delivered as a normal attachment, separate from a voice bubble |
| voice | Ogg with an Opus header; no automatic conversion |
| video | MP4 with container signature; WEBJS requires Google Chrome; no automatic conversion |
| sticker | WebP; no automatic conversion |
| location | Explicit coordinates and title; empty coordinates are not replaced with zero |
| contact | Up to ten explicit names and international numbers |
| poll | Question, 2–12 distinct options and an explicit multiple-answer choice |
| reaction | Add/remove a reaction to a selected owned, non-revoked snapshot; removal uses an empty string |

Every non-reaction kind can quote an owned, non-revoked message. Uploads are at most 20 MiB; TXT/CSV have a 1 MiB UTF-8 gate. MIME and extension must agree, and signatures are checked. Office files are opaque delivery: they are not extracted/executed. These gates and synthetic header fixtures are **not full media decoding, codec verification or malware scanning**. Physical preview and WhatsApp rendering remain acceptance items. One action sends one message/file; albums, multi-file atomic batches, forwarding, editing, message deletion, status/channel publication, buttons/lists and transcoding are not implemented here. An accepted reaction is not a new-message identity or a delivery/read receipt.

Paths and payload fields were checked against the [pinned 2026.9.1 controller](https://github.com/devlikeapro/waha/blob/2026.9.1/src/api/chatting.controller.ts) and [provider documentation](https://waha.devlike.pro/docs/how-to/send-messages/). In particular, reaction uses PUT. Execution requires that exact server version and WEBJS engine, a working session, the expected signed business webhook and `webjs.tagsEventsOn=true`; mismatch fails before submission, without automatically repairing provider configuration. Capability discovery declares implemented adapters, not successful live engine/phone certification.

Pinned WEBJS returns original SDK ID objects for sends; the gateway resolves only their `_serialized` ID (or an already serialized ID), still checking the authorized peer. Its reaction method returns void; a successful empty HTTP response records API acceptance only. The SDK can silently skip a missing reaction target, so verify the phone rather than interpreting this as applied/delivered. The engine explicitly rejects video on Chromium: a matching Google Chrome browser is checked before dispatch, producing `WAHA_SEND_VIDEO_REQUIRES_CHROME` without a send. See [engine](https://github.com/devlikeapro/waha/blob/2026.9.1/src/core/engines/webjs/session.webjs.core.ts) and [pinned SDK](https://github.com/devlikeapro/whatsapp-web.js/blob/fork-main-2026-06-26/src/Client.js).

## Three entry points and roles

**Manual:** save an immutable draft, inspect its final payload/recipient/attachment hash, then approve. Saving a manual draft does not send. Editing the input creates a new draft; it never mutates an already approved snapshot.

**Agent-assisted:** B supplies a proposed `WahaSendPayload`; the merchant can edit it and must approve the final draft. The page accepts a pasted suggestion and explicitly says no real polishing model is configured. The `mode` label is not evidence of a completed model call. No B model/generation endpoint is invented by A.

**Agent-automatic:** the merchant first approves an exact payload policy for one chat, an expiry (at most seven days) and a use budget (at most 100). A trusted B/Agent server orchestrator can submit `mode=agent_auto`, that policy ID and the identical payload. The server resolves account/recipient, binds current context and optional work-order versions, reserves one policy use, and queues the authorized immutable action atomically. No per-message click is needed. Changing text, recipients, attachments/hash or quoted source fails; ambiguity or variable generated content must go through manual review. The UI's policy submission button tests this gateway but **does not start a background Agent**. Real generation, automatic trigger selection and scheduling remain B/orchestrator work. Never pass merchant cookies, CSRF tokens, connector keys, URLs or storage paths to a model; the server broker owns authenticated tool calls and durable request keys.

- A owns upload/storage, supported WAHA adapters, permission checks, durable dispatch, outcome/receipt evidence and recovery APIs.
- B owns real polishing/generation, source/unknown handling and deciding whether a candidate fits an approved policy. Persist the exact command/key; a lost response never justifies a new key.
- C supplies business association/version/source decisions. Commands can bind `work_order_id` and `expected_work_order_version`; A verifies ownership, conversation linkage and that version before dispatch. Unbound messages are ordinary merchant communications, not work-order confirmations. No conversation-to-single-order guess, calendar write or customer confirmation is created by a send/read receipt. Generic legacy `ApprovalAction` definitions remain distinct from the implemented `WahaSendAction` gateway.
- The server also freezes **all linked work-order versions**, without guessing a target, so a C-only business change/link change invalidates stale generic sends or fixed policies even if message context did not advance. Quoted canonical text additionally pins its actual latest revision and rejects a canonical tombstone, not just a snapshot flag.
- A business-associated automatic policy can explicitly bind `work_order_id`/`expected_work_order_version` at merchant authorization. Automatic submissions must retain that target/version (or stay unbound when the policy is unbound); B cannot silently relabel an approved message to another order.
- D uses generated contracts, final-snapshot review and explicit unknown-result handling. E independently reviews races, authorization and real-account acceptance.

## Reliability and API agreement

All routes are under `/api/v1/connectors/{connection_id}/sending`, owned server-side. Every POST requires login, trusted origin/CSRF. Reading authorization never automatically grants sending authorization. Sending is disabled unless `WAHA_SEND_ENABLED=true`; attachments additionally require the existing private media storage setup.

Upload uses an `application/octet-stream` body, `X-File-Name` (percent-encoded UTF-8 filename) and `X-File-Mimetype` headers. Private filenames are not placed in access-log URLs. Authenticate before streaming, bound it to 30 seconds/20 MiB, then reauthenticate/recheck permission and quota under serialization before storage. Upload reception and provider receipt GETs do not hold the account's business mutation lock during I/O; default mutation authentication locking elsewhere remains intact.

| Route | Purpose |
| --- | --- |
| GET capabilities / permission / context/{chat_id} | Interface availability, separate permission and current version bindings |
| POST permission | Grant selected allowlisted chats with expiry; version-checked revoke works without provider settings/feature availability |
| POST uploads; GET uploads/{id}/content | Bounded raw upload and protected hash-verified preview/download; no user-supplied remote URL |
| POST drafts | Idempotency-Key required; immutable manual/assisted draft or exact-policy automatic queue entry |
| GET requests/{key}; POST requests/{key}/cancel | Recover original intention by opaque key; cancellation of a not-yet-created request persists a fence against late arrival |
| GET actions / actions/{id} | Bounded cursor pages (optional chat filter), final snapshots and outcome evidence |
| POST actions/{id}/approve / cancel | Revision-checked approval or cancellation before dispatch |
| POST actions/{id}/reconcile | Read-only receipt lookup by an already returned exact provider ID; never send again |
| POST actions/{id}/review-unknown | Explicit possible-delivery acknowledgement and review note; release later independent actions, preserve this action as unknown |
| POST policies; GET policies; POST policies/{id}/revoke | Exact content/recipient/source-bound preauthorization, expiry/use budget and revocation |

The action row is both the immutable approval snapshot and transactional outbox entry. It binds recipient, payload/attachment metadata/hash, quoted source fingerprints, action revision, control/permission/context versions, optional work-order version and expiry. Approval identity/time are separate from AI proposals. Account/connection serialization matches mutation authentication and inbound handling; revalidate immediately before committing the dispatch fence.

The worker commits `preparing` before GET preflight outside business locks; then commits `dispatching` before a **single** provider POST/PUT outside those locks. The committed dispatch fence is the local start of external execution. Input/revocation committed before it blocks dispatch; later changes cannot roll back a request already entering execution, and unseen remote events cannot be protected against locally. Expired preparing leases can recover; expired dispatching leases become `result_unknown`, never another POST. An immutable dispatch token retains a late successful response from the original attempt even after lease recovery; it does not authorize a second submission. Unexpected post-fence failures are conservatively unknown, including failures where non-submission cannot be proved. Preflight failure has no external send. This is not external exactly-once delivery.

New relevant text/media/edits/revocations invalidate drafts/queued/preparing snapshots. Signed API text echoes advance context without invoking extraction again; structured API echoes without text become observations. Already-dispatched actions retain their outcomes. Later actions require current context. Exact returned IDs correlate receipts; ACK rank is monotonic. Without a returned ID, an identical chat message is not safe attribution and absence is not proof of non-submission. Human review never converts unknown into delivered/confirmed or refunds an automatic-policy use.

The pinned provider declares `source` inside the message payload. Ingress/normalization explicitly handle that real shape as well as the earlier top-level synthetic profile, rejecting conflicting declarations or an incoming message claiming API origin. Missing/default app tags keep old duplicate identity; source is authenticated provider evidence, not a frontend flag. See [provider event fields](https://waha.devlike.pro/docs/how-to/events/).

Limits: 100 outstanding drafts/queued actions per connection, 100 dispatches per UTC day, at least five seconds between connection-wide dispatch starts and 100 MiB of retained uploads per connection. An unresolved unknown blocks its chat until explicit review. Uploads expire after 24 hours; maintenance deletes owned expired files and old unreferenced outbound blobs. Snapshot/request-fence/review records remain for audit; full authored-content/account/backup deletion is not implemented by this batch. Provider-owned media copies are outside A's cache deletion. Browser recovery storage contains only scoped opaque request keys, never text/files/credentials, and survives remounts; a missing lookup remains unresolved until explicit cancellation establishes a server fence.

Additive migration **0011_waha_multitype_sending** follows unchanged 0010. It adds five sending tables without granting/backfilling consent or rewriting media/ingress data. Source contracts generate domain/OpenAPI/frontend types. Do not edit generated files or remove WhatsApp session volumes to upgrade.

## Cleanup and unknown-outcome recovery runbook

Expired uploads remain unusable even if cleanup fails. For an expired tracked upload, an `OSError` during deletion leaves its blob reference intact for a later maintenance pass. Restore storage access, then allow maintenance to retry; do not extend expiry or restore sending permission to expose the file. Orphan-file deletion errors propagate and roll back this purge transaction; worker maintenance records `MEDIA_STORAGE_UNAVAILABLE`. Database errors are recorded as `DATABASE_UNAVAILABLE`. Neither implies a provider send.

Filesystem deletion and database commit are not atomic. If deletion succeeds but the transaction rolls back, an expired upload row may still reference a missing file. After restoring database/storage health, the next successful maintenance pass uses `unlink(missing_ok=True)` and clears that reference. Preserve upload hashes, action snapshots and receipt identities; do not recreate the missing bytes, delete audit records or reset actions to queued. Worker maintenance normally runs hourly; check its health and logs before expecting recovery. Synthetic regressions cover deletion failure followed by retry and deletion followed by database rollback. They do not prove real disk/database crash durability or PostgreSQL locking.

`run_once` performs one action/recovery operation per call; the worker loop calls it repeatedly. An expired `preparing` lease can return to queued because no provider submission has started. An expired `dispatching` lease becomes `result_unknown`, preserving the dispatch fence and blocking later sends to that chat. It must never return to queued for automatic resend. With an exact returned provider ID, use the explicit receipt lookup on the original action; an original late response or matching signed receipt can also establish evidence. With no ID, or an inconclusive lookup, inspect the original request/action and consenting test phone, then use `review-unknown` only to acknowledge possible delivery and release later independent work. The original outcome remains unknown; no new key, automatic retry or delivery claim is justified. The sending page exposes receipt lookup and unknown review; the separate C/D business-approval bridge remains pending.

## Unified own-account acceptance

Do this once after automatic checks, in a deliberately authorized own-account test chat. No actual sends were performed during development.

1. Restore Docker Desktop. Existing team installations can opt in and upgrade via `waha_team.py up`; do not repeat `init`, provision, or seed merely to upgrade. Keep the recorded private profile/database/session volumes. On Windows:

   ```powershell
   $env:WAHA_SEND_ENABLED = 'true'
   $env:WAHA_MEDIA_ENABLED = 'true'
   .venv\Scripts\python.exe scripts/waha_team.py up
   ```

   On macOS/Linux:

   ```bash
   WAHA_SEND_ENABLED=true WAHA_MEDIA_ENABLED=true .venv/bin/python scripts/waha_team.py up
   ```

   The owner's legacy `waha-a02` installation instead follows its [existing database upgrade example](role-a-media-ingestion.md), upgrades to head/check and adds `infra/waha-send.compose.yaml` after the ingress/media files when rebuilding only ingress/worker. Preserve its private restart override; do not start a second team installation just for this test. Sending remains unauthorized until the merchant explicitly grants it in the page.

   **Video opt-in only:** the ordinary native ARM/Chromium setup is preserved. If video is required, first pause/revoke sending and choose `WAHA_SEND_CHROME=true` together with the send/media flags before `waha_team.py up`. This appends `infra/waha-send-chrome.compose.yaml` after ARM overlays, selecting the pinned Chrome 2026.9.1 linux/amd64 manifest. Intel runs it natively; Apple Silicon uses emulation. Its public manifest was checked read-only; the container was not pulled/run and ARM emulation/phone behavior remains unverified. Existing legacy operators append that Chrome file last and explicitly recreate WAHA while retaining its session volume; inspect status and re-pair only if required. No automatic image or browser switch occurs.

2. Point the real frontend at ingress (not Replay): in `apps/web`, Windows `$env:GIGMATE_API_URL='http://127.0.0.1:18702'; npm run dev`; macOS/Linux `GIGMATE_API_URL=http://127.0.0.1:18702 npm run dev`. Open the Vite URL, login, confirm WhatsApp status and select a consenting allowlisted chat in the message workspace. Save its separate 24-hour sending permission.
3. Text/link: save a draft, verify the phone receives nothing yet, inspect the final snapshot, approve once, then compare the phone and action receipt. Refresh/remount without another send. Quote one loaded message and check the quote on the phone. Saving a changed draft requires a new review.
4. Upload one real small file of each chosen supported format. Inspect exact-file preview/hash/filename, save and approve each action separately. Check image/sticker rendering, audio attachment vs voice bubble, MP4 playback, captions and document names. Fixture signatures alone did not prove this. Wait for the previous echo and refresh current context before approving the next action.
5. Location/contact/poll/reaction: use fictional coordinates/contact details and a simple poll in your own test chat. Verify question/options, multi-select, location, contact card and reaction addition/removal on the phone. A reaction's accepted status does not imply another delivered message.
6. Agent-assisted: paste a fictional proposed reply, edit it and confirm the page sends only the approved snapshot. Actual B generation is a separate pending gate. Automatic: approve a short fixed-payload policy, explicitly submit it once, verify use count/record/phone; changed payload, exhausted/revoked policy and stale versions must not send. This does not validate a real autonomous Agent.
7. Save a manual draft, then send/edit/revoke a relevant incoming message before approving; the old draft must cancel/fail fresh checks. Pause/remove chat access or revoke sending; pending work must not dispatch. Restore explicitly. After dispatch starts, the page must not pretend cancellation rolled back an external send.
8. Use synthetic fault tests for lost responses/crashes/timeouts. In a real network failure, inspect the original record/key and phone; never create another attempt merely because lookup is empty. If the provider outcome is unknown, record a possible-delivery review only after checking. Keep its result unknown; permit only later independent work. Do not intentionally disrupt real send traffic just to force duplicates.
9. E repeats isolated PostgreSQL concurrency, HTTP/worker and Windows/Apple Silicon/physical-browser checks. Current development used synthetic transports and DOM/SQLite; no phone, live B model, PostgreSQL locking, deployment or independent production acceptance is implied. See [actual verification](implementation-status.md).
