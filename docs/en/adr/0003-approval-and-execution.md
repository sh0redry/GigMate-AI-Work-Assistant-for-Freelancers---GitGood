# ADR 0003 Approval and durable execution

- Status: Accepted baseline; implementation pending
- Date: 2026-10-01
- Owner: Repository maintainer

## Decision

Customer proposal, customer confirmation and merchant approval are distinct. AI drafts never grant permissions. Formal calendar changes and clarification messages require merchant approval; pre-authorized reminders are outside initial P0.

An immutable snapshot binds action revision, recipient/mutation, exact content, work-order version, context version, expiry and approver. Bound changes require new approval. Accepted relevant messages/edits/revocations advance context before AI processing and invalidate queued approvals. API send echoes do not cause reply loops or retroactively cancel dispatched sends.

Check consent, ownership, connection, cancellation and versions immediately before dispatch; serialize with accepted inbound changes. The local guarantee cannot cover connector events not yet delivered.

Persist approved work and outbox together. Workers use leases, stable idempotency keys and attempt records. Ambiguous outcomes enter result_unknown and reconciliation. Only definitely-not-submitted failures may retry automatically under a bounded policy with fresh checks. Completed jobs are never retried.

## Validation requirements

Cover stale work-order/context/action versions, edited content, revoked consent, disconnect, forged approval, unknown outcomes, duplicate events, API echoes and inbound/dispatch races. Fixtures are preparatory; application tests must later exercise services and persistence. Externally sent messages cannot be rolled back as database mutations.
