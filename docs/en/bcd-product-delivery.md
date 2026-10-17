# BCD initial text-product delivery — 2026-10-17

This candidate follows main `14aa34e` (PR31/32/33 merged). It is a reviewable initial **text workflow**, not evidence that a real deployment, paid vendor or phone has passed acceptance. The original plan's broader media/Agent scope remains explicit below. [中文](../zh/bcd-product-delivery.md).

## What the merchant can do

Connect and authorise a work chat; manually create an order from customer sources; review proposed changes; file ambiguous messages or dismiss them; defer a missing time/address; manage requirements/materials/commitments/questions; check hours, breaks, buffers and candidate slots; approve a reply, then explicitly submit its exact approved text through the existing sending gateway; inspect its owned receipt; manage tasks and the delivery checklist; finish/cancel/archive; view the internal calendar and export a current confirmed appointment as `.ics`.

AI-assisted creation is distinct from automatic creation. A new-order suggestion appears only when a valid current owned provider proposal exists. Selecting it fills the summary only. The merchant checks original messages, explicitly enters critical values and confirms creation. One received event can be consumed once through a suggestion; retries retain the original operation identity. Neither the model nor a successful extraction writes confirmed business fields.

The bounded question helper supports today's/tomorrow's schedule, waiting customers and decisions in Chinese, English and Cantonese. It reads existing owned records and links to orders. Unsupported questions get no invented answer. It is a deterministic helper, not unrestricted natural-language intelligence.

Task completion/cancellation checks account, open order, expected order version, expected task state, current authorised sources and completed prerequisites. Linked requirement state, task, order version, audit and receipt commit together. Completing a task does not change customer confirmation. Definite initial checklist/dependency rejection permits a reviewed correction; unknown requests retain their original journal.

The business sending UI resolves `WahaChoice.conversation_id` to the selected chat ID; chat and conversation UUIDs are never assumed interchangeable. The server retains final ownership, permission, body, revision and version checks. Approval, queued, dispatched, accepted, delivered, read and unknown remain different facts.

## Optional reviewed text provider (B)

Existing `deterministic`, `disabled` and historical closed `llm` behaviour remains compatible. The new **`reviewed_llm`** registration is explicitly opt-in and off by default. Use the locked backend runtime and server-only private configuration:

- `GIGMATE_EXTRACTION_PROVIDER=reviewed_llm`; provider/model/endpoint/API key as documented in [B extraction](role-b-extraction.md).
- Both `GIGMATE_LLM_LIVE=1` and `GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`.
- A validated `GIGMATE_WORKSPACE_TIMEZONE` and explicit operator-verified input/output USD-per-1K prices; finite budget and token limits. The historical price table alone does not activate this provider. Prices/token estimates are accounting assumptions, not vendor billing guarantees.
- For Compose, add `-f infra/compose.text.yaml` to the same existing deployment command after the base and any existing WAHA overlays, with the same private `--env-file`. This passes configuration to API and worker without exposing it in frontend assets. Recreate API/worker through the normal upgrade process; do not reset volumes. The overlay's default gates are closed.

Provider selection is validated **before** heartbeat/polling; invalid names fail with a sanitised code and exit 2. Prepare and persist a model request fence in a short transaction, release database locks, invoke the provider, then reacquire ownership/lease/consent/source/context/order checks before promotion. The production text provider uses a child process with a 20-second parent deadline, bounded request/result/response sizes and one HTTP attempt. A timed-out/crashed/abandoned submission keeps its request ID and requires review; it is not automatically paid for again. That ID is correlation, not vendor idempotency. Unknown items can be dismissed or handled manually, but cannot be reassigned to blindly invoke the model again.

Migration **0021_reviewed_product** adds the job submission fence and suggestion decision table after the preserved 0020 merge head. No shared migration is rewritten. Proposal decisions are removed with their source/account/order through explicit cascading foreign keys.

## D interface and cache

Pearl-white cards, mist-blue accent and limited glass navigation replace green styling. Chinese / English / Cantonese controls appear at login and in every workspace. Preference alone may persist in local storage. No translation service receives business text. Static UI dictionaries translate; customer content, saved order text and approved payloads do not. Language changes preserve component/input/session state.

Authenticated reads still reach the server. Session-memory snapshots, conditional ETags and structural sharing retain unchanged UI; 304 is accepted only with a matching local response. Auth/ownership checks precede ETag comparison; mutation, access denial, logout and account changes invalidate appropriate snapshots. No offline business authority, QR caching or chat service worker is added. DB reads are not eliminated. Vite development full-page reloads during source edits are separate from production polling.

## Verification and limits

- Linux with isolated PostgreSQL, locked dependencies: **987 passed, 1 skipped**; some fixtures explicitly use SQLite. The no-lock-during-model test obtains the same account lock from another transaction during the provider call.
- New product tests: **26 passed**; real subprocess + loopback-only fake HTTP vendor, actual sleeping-child termination, current/stale/paused/foreign sources, one-time suggestion consumption, task transactions, unknown-call recovery and sanitised startup failure. No real API key or paid vendor was used.
- Owned PostgreSQL upgraded from 0020 to 0021; Alembic check: no new upgrade operations. Full migration regression is included above. Compose text overlay configuration validates with closed example settings.
- Frontend/API/build/format and browser acceptance are recorded in [D acceptance](role-d-final-acceptance.md).

**Not delivered/accepted:** real OCR/ASR/image recognition and media-to-business promotion; unrestricted Agent drafts/automatic triggers; continuous external calendar sync; standalone exe/macOS installers; independent real-phone/final-provider acceptance; long-term production operations and complete account/backup deletion. Media remains closed. Do not describe these as ready merely because a seam, model shape, page or synthetic test exists.

Recommended handoff: B owns real vendor configuration/quality/media; C owns further business/Agent rules; D owns interface acceptance; A/E retain connector/phone/operations and independent end-to-end acceptance. Issue29 is a cross-role tracking item, not a completion certificate.
