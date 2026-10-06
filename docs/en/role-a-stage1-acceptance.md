# A-01 first-stage delivery and unified acceptance

Date: 2026-10-02. Baseline: v0.2 replay skeleton. Delivery: independent offline normalization and failure verification from the [roadmap](role-a-development-roadmap.md). See the [Chinese record](../zh/role-a-stage1-acceptance.md).

The user restricted edits to new files and previously created Role A documents. This batch adds implementation/tests/fixtures/demo/acceptance files and updates only those Role A responsibility/roadmap documents. Existing ingestion, API, worker, schemas, migrations, dependencies, CI, root README and global status records remain unchanged. This document records evidence instead of editing shared progress files. No commit/push.

## Delivered files

| File | Purpose |
| --- | --- |
| [waha_adapter.py](../../apps/backend/src/gigmate/waha_adapter.py) | Pure normalization, trusted mapping checks, existing wire validation and semantic digest |
| [waha_replay.py](../../apps/backend/src/gigmate/waha_replay.py) | Synthetic corpus expansion and in-memory dedup/revision acceptance ledger |
| [waha_a01.json](../../apps/backend/tests/fixtures/waha_a01.json) | Versioned synthetic manifest: 6 positive and 17 negative cases |
| [test_waha_adapter.py](../../apps/backend/tests/test_waha_adapter.py) | 87 tests covering normalization, failures, isolation, revisions, identity, safe errors and CLI |
| [replay_waha.py](../../scripts/replay_waha.py) | All cases, individual normalized output and seven-step demonstration without server/account |

Fixture profile is synthetic_waha_a01_v1, manifest version 1.0.0; output uses existing event wire 0.1.0. No shared schema changes. Module fixtures have their own manifest outside contracts/examples, preserving its existing manifest.

## Capabilities and boundaries

| Provider notification | Offline behavior | Existing WAHA ingestion / live verification |
| --- | --- | --- |
| message / message.any | message.created, text and explicitly resolved API outgoing source | Not connected / not tested |
| message.edited | Resolve editedMessageId to canonical original | Not connected / not tested |
| message.revoked | Resolve revokedMessageId, allow null before, omit revoked text | Not connected / not tested |
| message.ack | Independent identity, no content-revision advancement | Not connected / not tested |
| session.status | Listed states map into four wire states; discard QR/authentication material | Not connected / not tested |
| Media/reactions/unknown kinds | Explicit rejection | Unsupported |

Existing messaging.ingest still accepts Replay only. Do not relabel waha output as replay to bypass that restriction. No webhook/QR/model/send endpoint was added. WORKING-to-connected conversion does not establish freshness or tested connectivity.

## Input and trusted resolution

Provider fields were checked against [WAHA events](https://waha.devlike.pro/docs/how-to/events/) and [message documentation](https://waha.devlike.pro/docs/how-to/receive-messages/). No actual engine/version was pinned. This explicit synthetic profile is not a universal live adapter.

| Input | Policy |
| --- | --- |
| Envelope id | Nonempty event identity; missing yields EVENT_ID_REQUIRED, never random fallback |
| Envelope timestamp | Integer milliseconds to UTC Z; never infer units or substitute receipt time |
| event / session | Supported kind and trusted session match |
| payload.id | Creation/ACK target reference; opaque, no phone-number parsing |
| editedMessageId / revokedMessageId | Original target reference, never substitute action identity |
| fromMe / from / to | Strict boolean direction and matching peer; minimum outgoing ACK may use peer in from |
| hasMedia / body | Explicit false and nonempty text for create/edit; no inferred missing type |
| Raw account/metadata/revision | Cannot override trusted account or revision |

NormalizationContext supplies canonical account UUID, instance/session and source-verification/consent facts. ResolvedMessage supplies internal conversation/message UUIDs, canonical original provider ID, raw target reference, peer ID, allowlist fact, revision and app/api source.

These objects are trusted server-caller contracts, not authentication. Synthetic true flags do not verify a real webhook. Future public request bodies must not construct them directly. Authenticated session/account lookup, allowlist and durable message resolution must happen before normalization. HMAC and database resolvers are not implemented here.

Revisions come from the trusted resolver, never arrival order. Creation needs revision 1; edits/revokes at least 2; the ledger requires contiguous revisions and rejects gaps. Missing originals/unknown revisions require future reconciliation or review. API source requires an explicit resolved fact and outgoing direction; conflicting raw source is rejected. Outgoing alone does not imply API origin. Session source=app is a convention of this offline profile.

## Identity, digest and ACK semantics

event_id is UUIDv5 from a fixed namespace and JSON sequence of instance/account/session/provider event ID. Redelivery stays stable and scopes are isolated. Live provider redelivery identity stability still needs testing.

semantic_digest validates the event then hashes sorted compact UTF-8 JSON excluding received_at. Changed receipt does not conflict; changed content/target/direction/version/type/occurrence does. This does not replace the existing whole-event Inbox digest; coordinate live compatibility later.

ReplayLedger demonstrates event redelivery, message/message.any aliases with differing event IDs, content conflicts at the same revision, edit/revoke progression, ACK independence and cross-account/conversation internal-ID rejection. Only content mutations advance its context; ACKs do not. It stores in-memory acceptance state, lost on process exit, with no durable queue, transaction or exactly-once guarantee.

ACK mapping: PENDING(0)→unknown, SERVER(1)→sent, DEVICE(2)→delivered, READ(3)/PLAYED(4)→read. ERROR(-1) yields ACK_ERROR_NEEDS_RECONCILIATION; unknown or contradictory ack/ackName fails. No ACK grants customer confirmation or PENDING submission success. PLAYED collapses into read because of the current wire enum.

## Local usage

Use the locked .venv from repository root; no database, WAHA container or public server needed:

```powershell
.venv/Scripts/python.exe scripts/replay_waha.py
.venv/Scripts/python.exe scripts/replay_waha.py --list
.venv/Scripts/python.exe scripts/replay_waha.py --case text-edited --show-events
.venv/Scripts/python.exe scripts/replay_waha.py --sequence
$env:PYTHONPATH = 'apps/backend/src'
.venv/Scripts/python.exe -m pytest apps/backend/tests/test_waha_adapter.py -q --basetemp=local-data/pytest-waha-a01
```

Expected rejections count as passing corpus cases. Default output shows names/results/IDs/types/digests or safe codes; --show-events prints only built-in synthetic normalized messages. The tool has no account/token/arbitrary-chat-file input. Unknown cases exit nonzero. Missing dependencies produce a lock installation instruction without private text/tracebacks. basetemp is disposable test-only storage.

Seven-step sequence: create context=1, duplicate stays 1, ACK stays 1, early revision-3 revoke rejected, revision-2 edit context=2, revoke context=3, revoke duplicate stays 3. This demonstrates unpoisoned in-memory state after failure, not database recovery.

## Actual evidence

| Check | Result |
| --- | --- |
| Ruff check, backend + export_contracts/smoke_replay/replay_waha | Passed |
| Ruff format --check, same scope | 24 Python files formatted |
| export_contracts.py --check | Domain/implemented OpenAPI synchronized |
| pytest apps/backend/tests, SQLite fallback | 112 passed, 1 skipped, including 87 new tests; one known Starlette/httpx deprecation warning |
| All replay_waha cases | 23 cases, 0 failures, 6 valid/17 expected rejections |
| --sequence | 7 steps, 0 failures |
| text-edited --show-events | Canonical original ID, revision 2, UTC times and schema-valid output |

Final baseline/diff evidence is appended below. TEST_DATABASE_URL was unset; PostgreSQL concurrent claiming skipped. No row-lock or persistence claims. No frontend, migration or deployment changes, so no frontend build/migration/deployment HTTP smoke run. No live WAHA or human E acceptance.

## Unified E acceptance and next dependencies

E can run the corpus, sequence and tests together, inspect authorization/mapping failures, original targets, identity conflicts, revision progression, API provenance, ACK meanings and safe errors, then record defects/retests. Automated passes do not imply E participation or live validation.

This completes the independent/new-file A-01 delivery. Shared atomic ingress, model-call prevention assertions, durable resolution, database failures and stale-proposal integration still use existing Replay behavior without new WAHA proof. Integrating existing code requires user consent and coordination with C. A-02 adds real engine/version probes, authentication, QR and adapter wiring; A-03 proves durable recovery. Never use the in-memory ledger as a live webhook service.

## Final checks

- `.venv/Scripts/python.exe scripts/check_baseline.py`: 40 Markdown files, 152 local links, 3 schemas, 11 valid/6 rejected shared fixtures and 12 synthetic scenarios passed. The module's 23 cases are covered by pytest/demo, not counted as baseline fixtures.
- `git diff --check`: passed. Scope review confirms only four permitted tracked Role A responsibility/roadmap documents changed; other deliveries are new files.
- Solo self-review covered wire compatibility, source/permission boundaries, bilingual evidence, in-memory versus durable limits, synthetic classification and absence of private data. Independent peer review, human E acceptance and live ingress were not performed.
