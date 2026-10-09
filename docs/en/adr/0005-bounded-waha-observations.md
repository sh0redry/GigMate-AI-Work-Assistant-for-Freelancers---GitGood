# ADR 0005 Bounded WAHA observations and deferred media reading

- Status: Implemented in the authorized local message-sync batch; live format acceptance remains independent.
- Date: 2026-10-09
- Scope: Role A owned synchronization, not new extraction/execution authority.

## Decision

Provider history is a current snapshot, not an authoritative editing/revocation log. Persist it separately from canonical message_revisions and normalized Inbox/Jobs. Never fabricate revision 1 or intermediate revisions to repair a missing live source. Preserve live revisions/tombstones, scoped canonical identity and query-time ordering. An explicit source lookup can produce snapshot_found while the original revision gap remains unresolved.

History requires current account/chat authorization, explicit range consent, captured control_version, fixed UTC bounds within 30 days and bounded pages/records. Page-level read leases commit before network I/O; finalization checks permission/version/token again. Read-only uncertain outcomes can be retried under a three-attempt budget and exponential delay; external writes retain the existing no-blind-resend rule. Pause/revocation cancels active work and records intervals excluded by later queries. Pre-upgrade intervals are not invented.

Media reading was explicitly deferred by the owner: this batch accepts only provider-declared type/MIME/filename/caption/provenance and supported ACK metadata, with no file URL/bytes, OCR, transcription or GenAI invocation. Metadata-only receipts are distinguished from normalized event receipts. Media changes invalidate proposed context; delivery ACK never establishes customer confirmation. Quoted bodies are not copied and participant identity is not trusted ownership/approval.

Historical/media snapshots are context-only evidence. Stable timeline IDs are display identities; source_message_id/revision identify canonical SourceRef evidence only when actual revisions exist. B/C must explicitly define any future observation-to-proposal source contract and execution authority rather than treating a snapshot as an existing critical-field source. Production identity, rate limits, external sending, multi-session provisioning and full history guarantees remain separate milestones.

## Validation

Ownership/CSRF, permission revocation during a provider read, deduplication, lease recovery/concurrent claims, bounded queries/retry, source lookup without fake revisions, tombstone precedence and content retention have automated coverage. Real history/group/media schemas and engine/API behavior require consenting own-account tests. Empty provider pages and successful jobs are not proofs of complete WhatsApp history. See [batch acceptance](../role-a-message-sync-acceptance.md).
