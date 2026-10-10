# Owned attachment ingestion and A/B handoff

## Batch 2: original time, source review and business handoff

Implemented A's part on top of the PR #16 compatible media branch. Real OCR/ASR/PDF parsing/GenAI remains B's dependency, and external sending remains outside this batch. PR #18 has not been merged and is not a media processor.

- Additive migration **0010_waha_media_evidence** follows unchanged 0009. `waha_snapshots.message_sent_at` is captured only from a newly observed original message/history payload's bounded numeric Unix-seconds `timestamp`. Edits/revocations never replace it; old snapshots stay null. Malformed, missing, millisecond-shaped and non-finite values stay unknown. The separate event `occurred_at` and observation time are never substituted. Receipt digests/fingerprints remain unchanged, so the timestamp addition does not break existing duplicate identity. [Provider event examples](https://waha.devlike.pro/docs/how-to/events/) show the message payload timestamp separately from mutation references; engine/physical evidence still needs own-account verification.
- `WahaMediaCommand.timezone` optionally takes a validated IANA zone explicitly chosen by the merchant **for this request**, not an inferred account/customer timezone. The browser does not default it from device or phone prefix. `waha_media_jobs.input_context` freezes message_sent_at, timezone, timezone_source=merchant_choice/unknown, source_occurred_at and source_observed_at when queued. B receives these alongside bounded bytes. Old jobs have no fabricated time context; changing the timezone cannot reuse the original idempotency key. Results retain the original processing context even if a newer task is queued. Missing sending time or relevant timezone requires unresolved questions before business interpretation of relative dates.
- Suggestions link to their returned source segment. Review now additionally binds the exact result job, attachment version and SHA. Old reviews without these bindings must be explicitly reviewed again for the new handoff; this does not require rereading or repeating a model request.
- **GET /api/v1/connectors/{id}/media/attachments/{attachment_id}/evidence** is an implemented read-only endpoint. Required query values: expected_attachment_version, expected_context_version, expected_result_job_id. It requires the current result to have an exact source review, rechecks ownership/allowlist/enabled reception/source/expiry and byte integrity, and returns no-store `WahaMediaEvidence` 0.1.0. The bundle contains scoped application UUIDs, source fingerprint/hash, frozen time context, versioned result/segments/suggestions, review and expiry. No provider URLs/keys/paths or execution authority. The page's **查看业务交接资料（不写入工单）** reads this only after review; pause, permission/read failures or refreshed result/context changes clear the view.
- **C integration remains a future consumer**: reread/revalidate evidence within the actual business command, resolve one work order or request review for ambiguity, retain attachment/result/hash/segment provenance distinct from canonical text SourceRef, and bind the target work-order/context versions. An already copied bundle is not ongoing authorization. Reading evidence and merchant source review are not customer confirmation, merchant business approval or work-order creation. This batch does not implement promotion/writes or approve external actions.

### One acceptance batch

1. Restore Docker Desktop first. Preserve original WhatsApp sessions, private configuration and databases; do not provision/seed them. With your existing database URL/PYTHONPATH, run Alembic `upgrade head` and `check`, then rebuild API/worker with the same media Compose files. **The recorded local deployment is still on 0009; this batch has not deployed 0010.** New code must run against 0010. The old upgrade example above remains usable; never repeat setup solely to upgrade.
2. In an owned authorized test chat send image/voice/PDF/TXT, with a fictional relative-date caption. Open the real workspace, explicitly enter the applicable zone (e.g. Asia/Hong_Kong) or leave it unknown, consent and read. Verify preview/reload/task recovery. Compare the original timestamp with the phone, independently from the event/observation clock; edit the caption and ensure original sending time is retained. Existing records without evidence must show unknown.
3. With B unset, do not expect OCR or enable model consent. Missing B remains explicit. Once B supplies process/reconcile, verify its captured request time/source/hash, page/audio locations, coverage and unresolved questions. Choose a different timezone only as a new explicit task, never reuse an uncertain request or blindly resubmit.
4. Click source links, check the file/result and mark source reviewed; only then read business handoff. Verify its source/version/hash/result ID and that no work order/calendar/send was created. Old unbound reviews require a fresh review.
5. Pause/remove authorization/revoke or edit the source/change conversation context; handoff/result access must fail or disappear. Test old result IDs and damaged files with synthetic fixtures. Restore only explicitly. Already copied/downloaded bytes cannot be recalled.
6. Repeat isolated PostgreSQL/HTTP, actual browser and Windows/Apple Silicon checks when Docker is available; E performs independent review. Automated DOM fixtures and SQLite are not real provider/model or PostgreSQL locking evidence. Unified automatic evidence is recorded in implementation status.

2026-10-10 · Andy_WAHA_media_ingestion, based on message-sync 56e482e. The owner authorized original-file reading and confirmed that **B has not connected a real model: finish A and the integration contract first**. [Chinese](../zh/role-a-media-ingestion.md). This supersedes ADR 0005's deferred reading boundary only for explicitly consented requests; see [ADR 0006](adr/0006-owned-media-handoff.md).

## What A implements

Allowlisted media observation → explicit per-attachment download consent → durable read job → private blob and hash → protected preview/download → optionally invoke B's configured processor → separately record merchant source review. There is no automatic download when a webhook arrives, no automatic model call, no work-order confirmation and no external send. Original files and content go into private local storage/volume, never tracked fixtures.

Accepted declared types: PNG/JPEG/WebP, Ogg/MP3/WAV/M4A audio, PDF and UTF-8 TXT. Base MIME parameters such as audio/ogg; codecs=opus are normalized; unsupported or mismatching declarations fail. Maximum file size is 20 MiB, TXT 1 MiB. Signature/UTF-8 checks are a bounded format gate, **not a complete decoder, malware scan, PDF parser or audio-duration proof**. B must enforce parser/page/duration/token limits before model use. SVG/HTML/archive/Office/video files are outside this batch.

The pinned WAHA Core 2026.9.1/WEBJS source was inspected: the owned single-message GET supports explicit downloadMedia=true, overriding its API default. Event/API defaults remain false. The backend resolves one already accepted snapshot/chat/direction, validates the returned message, then accepts only trusted provider origins and /api/files paths; it rebases the file GET onto the configured provider client, rejects redirects/traversal/query credentials and bounds streaming. It never fetches an event URL or user-supplied URL. [WAHA media reference](https://waha.devlike.pro/docs/how-to/receive-messages/#media-files). Physical API/file formats remain a separate gate.

Blobs have random server keys, bounded size and SHA-256 integrity checks; frontend/models never receive keys, storage paths or provider URLs/credentials. Cached same-source reads reuse bytes. Attachment versions advance for changed captured source or changed bytes. Ownership/account activity, enabled reception, current allowlist, source fingerprint, context, authorization version and lease token are checked before and after I/O. Pause/revocation suppresses results; preview is checked on every GET and client previews clear on access failures. Already delivered/downloaded bytes cannot be recalled.

Downloads have three bounded attempts/backoff and reclaimable 180-second leases. Model processing does not automatically retry: uncertain submission/expired processing leases become result_unknown and block that attachment's reissue. An explicit reconcile queues only B's read-only lookup, never process again. Uncertain jobs do not block other attachments. Missing B configuration fails clearly while the downloaded file remains available.

## B's implementation contract

A provides `gigmate.media_processing.MediaInput` and `MediaProcessor`. B supplies a server-installed factory configured by `GIGMATE_MEDIA_PROCESSOR_FACTORY=your.module:factory`. No real provider, OCR, ASR or PDF parser is shipped by A; there is no synthetic runtime fallback. Test processors are injected only into isolated automated fixtures.

- `process(input) -> WahaMediaResult`: input includes bounded bytes, normalized MIME, caption, origin=live, account/conversation/snapshot/attachment UUIDs, attachment/context versions, fingerprint, SHA and recorded source_occurred_at. No credentials/URLs/paths. message_sent_at/timezone are nullable evidence populated by batch 2; **do not treat observation time or server clock as the original sending time for relative dates**. Coordinate actual sent-time/timezone evidence before converting ambiguous dates; otherwise return unresolved questions.
- B performs OCR, speech transcription, PDF/text parsing and optional GenAI business suggestions. It uses request_id for durable idempotency/reconciliation and persists the immutable account/source/hash association. The request runs after lease commit, outside database business locks.
- `WahaMediaResult`: provider/model/prompt versions, coverage=complete/partial/unknown, bounded text segments (page OR audio interval), summary, suggestions with zero-based source_indices, and unresolved questions. Maximum 200 segments / 100,000 extracted characters; references must point to returned segments. Unknowns stay unknown. No field status confirmed, work-order mutation, tool permissions or sending. Strict extra-field rejection applies.
- `ProcessingUnavailable`: B guarantees nothing submitted. `ProcessingUncertain`: something may have submitted; do not retry. Other unexpected model errors are treated conservatively. B must not leak error bodies/keys in output/logs.
- `reconcile(request_id) -> result | None`: look up the original scoped request without resubmission. None means still unknown. Validate the original account/attachment/fingerprint/hash association before returning a result.
- Results/reviews bind current source and context. Edits/revokes/other context changes hide stale suggestions/reviews. Merchant review only records that they checked the source, with a note; it does not rewrite the original result, confirm business fields or grant execution. Critical-field promotion needs B/C's future attachment-evidence agreement; a snapshot UUID is not a canonical message revision.

## APIs and migration

Owned prefix `/api/v1/connectors/{id}/media`. Browser login/CSRF and server ownership apply; credentials are private server configuration.

| Route | Behavior |
| --- | --- |
| GET /capabilities | Enabled/storage/processor availability, bounded types/size |
| POST /jobs | WahaMediaCommand + Idempotency-Key; explicit download consent, separate model consent, expected_version and owned snapshot UUID; 202 after commit |
| GET /jobs/{id} | Safe stage/state/retry/error; no content or provider IDs |
| POST /jobs/{id}/cancel | WahaVersionCommand; cancellation cannot recall an already submitted model call |
| POST /jobs/{id}/reconcile | Explicit versioned read-only model lookup for result_unknown |
| GET /attachments?snapshot_id=UUID | Current source-scoped attachment and durable latest_job_id for page reload |
| GET /attachments/{id} | Version/hash/current result/review, no blob key/path |
| GET /attachments/{id}/content | Authenticated bounded bytes; no-store/nosniff/sandbox/same-origin; download=true forces attachment disposition |
| POST /attachments/{id}/review | Explicit review, attachment/context versions, expected_result_job_id and bounded note; never work-order confirmation |

Additive **0009_waha_media_ingestion** after 0008: waha_attachments and waha_media_jobs. Shared migrations remain untouched. Source-generated contracts/types. Disabled media does not require these tables for the existing pause path; upgrade head before enabling media. Results/notes/files expire 30 days from captured source time; worker cleanup also removes old unreferenced blobs, preserving unrelated files. No full account/backup deletion. WAHA's own media cache is a separate provider retention concern; turning off/stopping storage maintenance does not purge existing volumes.

The backend image initializes the media mount as appuser-owned mode 0700. API and worker share the volume as non-root users; verify writability for previously created volumes. Cached intact-file processing does not require WAHA credentials; a damaged/missing cache is fetched again only under the explicit request and valid provider settings. Review also checks the original blob's integrity and the exact result job, preventing a newly produced result from inheriting an old review.

## Local startup and one acceptance batch

Keep original session/binding/database volumes and authorization. **Never provision or seed a WAHA installation solely to upgrade.** A newly cloned team installation may use `WAHA_MEDIA_ENABLED=true` with `waha_team.py up`; it automatically adds [media Compose](../../infra/waha-media.compose.yaml). B factory and credentials are a separate private operator configuration. Leave factory unset until B delivers it.

For this operator's legacy installation (database already on 16433), root PowerShell:

```powershell
$env:PYTHONPATH = 'apps/backend/src'
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:16433/gigmate_waha_a03'
.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini check
$env:WAHA_DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@host.docker.internal:16433/gigmate_waha_a03'
$env:WAHA_MEDIA_ENABLED = 'true'
docker compose --env-file local-data/waha-a02/.env -f infra/waha.compose.yaml -f infra/waha-ingress.compose.yaml -f infra/waha-media.compose.yaml -f local-data/waha-a02/restart-policy.override.yaml up --build -d --no-deps --wait ingress ingress-worker
```

The last private restart override exists on this operator's machine only. Other installations use their own recorded database/private setup and `unless-stopped` choice. Native API/worker share an absolute private `WAHA_MEDIA_ROOT`, with WAHA_MEDIA_ENABLED=true. Original event/API automatic media download settings remain false.

1. Open the real own-account workspace; select an authorized consenting chat and send image, voice, PDF and TXT test attachments. Reload its timeline. Each teammate uses their own account/files; do not track them.
2. Open **附件读取与核对**, consent to download only, click read, wait, then preview/download. Reload the page and reopen: latest task/file remain available without automatic reread. Test TXT UTF-8 limits; native audio/PDF decoding is a manual format gate.
3. B unset: its checkbox stays unavailable; no false OCR/GenAI success. An explicit backend processing request fails MEDIA_PROCESSOR_NOT_CONFIGURED but preserves downloaded bytes. B's adapter is a later dependency.
4. Pause/remove consent or revoke/edit the media during a sufficiently long download. Results must be suppressed; cached previews must become unavailable. Restore explicitly; no automatic reauthorization/retry.
5. Restart worker while reading; verify lease recovery and one published file. Verify wrong-account/no-CSRF/size/type/invalidURL failures with automated fixtures, not real credential exposure.
6. After B installs its real adapter, explicitly grant model consent: inspect original file, extracted segments/coverage, suggestions and unresolved questions, then mark source reviewed. Changed source/context prevents stale review. Test uncertain outcomes through read-only lookup, never blind resubmission. This is not external sending or work-order creation.

Automatic synthetic checks validate A plumbing and injected B result schemas, not real OCR/ASR/model accuracy. Full evidence, actual counts and remaining physical/B gates are in [implementation status](implementation-status.md).

This operator's installation is already migrated to 0009 with media API/worker/storage enabled and processor unset; no real file has been read automatically. The browser automation helper failed to start its Node runtime on both attempts, so page visual/real audio/PDF behavior remains manual. Automatic audio/PDF HTTP fixtures verify transport/signature handling only, not valid decoding/parsing. For batch 2, upgrade to 0010 as described above before rebuilding the API/worker; never provision solely for acceptance.

## Processor factory review correction

The trusted factory must return an object with callable `process` and `reconcile` methods. A missing or non-callable method is rejected as `ProcessingUnavailable` before submission. Invalid configuration, unavailable imports and missing/non-callable factory symbols are configuration failures. Exceptions raised by the factory constructor propagate unchanged from `processor()` so B can diagnose implementation defects; the worker still records unexpected processing exceptions conservatively and never blindly resubmits. Validation does not call either method.
