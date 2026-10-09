# WAHA message synchronization and metadata acceptance

2026-10-09 · branch **Andy_WAHA_message_sync**, based on **ebf9398** (PR #11's existing integration). [Chinese](../zh/role-a-message-sync-acceptance.md). Implementation decisions: [ADR 0005](adr/0005-bounded-waha-observations.md).

## Delivered scope

| Capability | Implemented behavior |
| --- | --- |
| Conversation management | Provider discovery pages of up to 100, offsets through 10000; previously discovered pages retained until expiry. UI search/type/authorized filters apply to loaded choices; load more to reach later pages. Selection remains explicitly saved and bounded to 100 authorized chats. |
| Message timeline | Owned, currently authorized chat; chronological keyset pagination, live revision/tombstone precedence, source timestamps, direction, processing and delivery state. Stable timeline IDs merge live and historical observations without exposing provider IDs. |
| Bounded history | Explicit per-request consent, 1–20 currently authorized chats, a fixed past window within 30 days and 1–1000 scanned records. UI presets 1/3/7/14 days. Stores provider snapshots with revision=null, not invented original messages/revisions. |
| Durable read tasks | One active synchronization per connection, page cursor/progress persisted transactionally; 120-second leases and stale-owner suppression. Read failures have bounded exponential delay and three consecutive attempts per page; restart retries GET-only work. Cancel is durable; failed ranges can be explicitly reissued with current authority. |
| Recovery gaps | User can choose a recovered incident's nonempty time range and selected chat for a bounded check. No automatic incident acknowledgement or guarantee of complete recovery. |
| Missing source | Signed, authorized unresolved edit/revoke/ACK records retain only scoped target/direction metadata. Explicit lookup may find an owned provider snapshot; it does not fabricate prior revisions or make the unresolved event actionable. |
| Groups/replies | Direct/group classification; supplied participant is represented by a stable scoped application UUID. Links resolve only to known messages in that chat; quoted bodies and provider participant IDs are not copied to the client. Participant identity is not account ownership or business approval. |
| Media foundation | Image/audio/document/video/other classification, optional caption, declared MIME/filename, edit/revoke observation and supported ACK metadata. File URLs, raw engine fields and bytes are excluded. Caption updates retain known attachment metadata; aliases must match registered chat/direction and ambiguity is rejected. |
| Local setup | Optional `waha_team.py remember-database` verifies a legacy binding then atomically saves a private workspace-bound local database URL. Later wrapper commands no longer need repeated environment setup. Team profiles keep their existing database management. |

**Explicit media decision:** the owner chose metadata/captions only for this batch. No original files downloaded, displayed, transcribed, OCRed or sent to a GenAI provider. MIME/filename are provider declarations, not validated file contents. Existing Compose disables event/API media download; every history/lookup GET explicitly requests downloadMedia=false. File reading, retention/cost and GenAI use require a later agreed design. Cloud API, external sends and multi-session provisioning are outside this batch.

## Safety and consumer contract

Authenticate and resolve installation/account/chat ownership before each read and write. Recheck active account, enabled reception and captured control_version after network I/O. Pause/removal cancels work and records exclusion intervals; queries skip those recorded intervals even after restoration. Permission/version changes suppress in-flight results. Earlier pre-upgrade authorization intervals are not reconstructed: no claim that all past denials are known.

Live text continues through the existing 0.1 normalized event/revision/worker pipeline. Metadata-only media acceptance uses durable observation receipts with `acceptance_kind=observation`; it creates no normalized Inbox/Job. Normal text/status/ACK responses retain `acceptance_kind=normalized_event`. accepted includes both categories, while pending/timed business jobs exclude synchronization and media-only observations. Consumers must not assume every accepted receipt is an extraction job.

Historical snapshots and media observations never trigger the current extraction/approval/send pipeline. `WahaTimelineMessage.id` is a stable display ID; `source_message_id` plus `revision` identifies a real canonical revision only when evidence=revision. Snapshot-only rows have source_message_id/revision null and cannot be treated as existing SourceRef facts for confirmed critical fields. B can design bounded background context on top of this read seam; promoting observations into sourced proposals needs explicit contract/authority handling. C's approval/context/source checks remain unchanged. Media changes advance conversation context and invalidate proposed changes; ACK does not.

History cannot overwrite live evidence or re-expose revoked text. Repeated observations deduplicate by owned canonical identity; newer history snapshots may refresh earlier history snapshots, without pretending to reconstruct edits. Fetch time guards prevent older queries regressing newer evidence. Cleanup scrubs snapshot text/filename/participant/reply metadata by source time after 30 days, retains identity and removes old terminal sync tasks/observation receipts/source-gap metadata. Full account/backup deletion remains future work.

## Implemented API and migration

Prefix `/api/v1/connectors/{connection_id}`. All resources are owner-scoped; mutations require login/CSRF and commits before success.

| Route | Contract |
| --- | --- |
| POST /operations | Existing control command now accepts discovery offset/limit; result includes next_offset. Defaulted compact requests remain accepted. |
| POST /sync-jobs | WahaSyncCommand plus stable Idempotency-Key; expected_version, chat_ids, since/until, max_records, explicit consent, optional incident/source-gap UUID. Returns 202 intent, not completed import. |
| GET /sync-jobs, /sync-jobs/{id} | Safe progress/state/counters/coverage and scope; no provider URLs/IDs/content. |
| POST /sync-jobs/{id}/cancel | WahaVersionCommand; an old lease cannot finalize after cancellation. |
| GET /chats/{chat_id}/timeline | WahaTimelineMessage page; limit 1–100 and opaque cursor bound to connection/chat/time/ID. |
| GET /source-gaps | Owned currently authorized source-gap metadata, no original target or body. |

Migration **0008_waha_message_sync** follows 0007; adds control pagination parameters and durable snapshot/receipt/exclusion/source-gap/sync tables. Existing migrations are preserved. Regenerate domain/OpenAPI/types from source, never edit generated JSON/types manually.

Each task reads pages of at most 50 and caps at 100 pages. Offsets advance by requested page size even for partial provider pages; an empty page ends that chat. Coverage differentiates in-progress, provider-exhausted, limit-reached and incomplete. **complete_history is always false**; an empty provider page does not prove all WhatsApp history is available. Offset pagination can shift while provider data changes; results are deduplicated but completeness is not guaranteed. This is a local single-installation capability, not a production performance/concurrency guarantee.

## Upgrade and unified manual acceptance

Keep private config, database and session volumes. Team installation: `python scripts/waha_team.py up`, then doctor. Legacy installation: use the same database/internal port/private Compose environment recorded in [previous acceptance](role-a-integration-acceptance.md), migrate head/check and rebuild ingress/worker/monitor before using the new page. Do not reprovision solely to upgrade; it can overwrite browser authorization. For this operator the preserved DB port is 16433, not the old 54329. If a legacy terminal already has the correct DATABASE_URL, explicitly run `python scripts/waha_team.py remember-database`; its ignored database.json contains credentials and must stay private. Never copy it to teammates. This helper does not start the database or adopt a different workspace.

Open the live local workspace (normally 127.0.0.1:5173 with GIGMATE_API_URL pointing at ingress18702). Each teammate uses their own consenting account/chat. Test the whole batch once:

1. Discover/load pages and use search/direct/group/authorized filters. Save the intended test chat; check that selected authorization survives later pages.
2. Open **消息时间线与同步**, choose that authorized chat and load its timeline. Verify a fresh create/edit/delete sequence updates revisions/tombstone after reloading. Existing text checkpoint/verify remains the text-revision check.
3. Confirm historical read consent, choose a small range/limit and start. Inspect state/progress, reload timeline, distinguish historical snapshots from live revisions. Repeat the same range: counts may include duplicates/refreshes, but no duplicate messages or business effects. Cancel a queued/running task; retry a failed range explicitly.
4. During a sufficiently long query, pause reception or remove chat authorization. Confirm cancelled/suppressed results and denied future content; restore explicitly. A new query skips recorded denied intervals. Rebuild/restart the worker during a query and verify cursor/progress resume without duplicate rows.
5. In a consenting group, send text and reply to another known message; verify stable sender separation and in-chat reply links. Do not treat membership as business approval.
6. Send an image with caption, voice/audio and document. Verify declared types/caption/filename or unknown fields, no attachment links/downloads, no GenAI calls. Edit/revoke an applicable media caption/message; verify metadata/tombstone and supported delivery state. These observations do not create business extraction jobs.
7. If a source gap exists, explicitly query its snapshot and verify revision remains unknown and the incident remains for review. For a recovered outage, query its bounded interval; manually evaluate remaining gaps before reviewing it. No deliberate logout/Internet interruption is needed solely to produce screenshots.

Automated tests use synthetic fixtures; real account history/group/media formats and native Apple Silicon pairing remain separate physical gates. E independently reviews permissions, ownership, concurrency/leases, offset shifts, unknown sources and privacy. Reports contain versions, safe counters and outcomes only; never real messages, chat IDs, QR, credentials or files. Current command results are in [implementation status](implementation-status.md).
