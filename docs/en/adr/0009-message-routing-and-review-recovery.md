# ADR 0009: Per-message proposals and explicit review recovery

- Status: accepted for the requested local bug-fix batch
- Related: [architecture](../architecture.md), [approval boundaries](0003-approval-and-execution.md)

A chat is a communication channel, not a work order. The text request includes owned open-order snapshots and a bounded recent transcript. The provider must distinguish a supplement from a separate job, including a new job when this chat already has orders. Multiple candidates are valid when one can be identified; the selected candidate's own version is checked before persistence. Nothing automatically creates or confirms an order.

After envelope and provenance validation, validate recognised fields independently. A malformed field is omitted with a typed trace note; other valid information and a new-job summary survive. Do not stringify unknown objects, invent addresses, manufacture an end time or relax ownership. If there is no usable information, retain the original refusal. Optional missing specification, quantity and deadline are not mandatory questions.

Messages queued before another message arrives may each be interpreted against a fresh context, provided their revision is still current and no consent-denial interval has intervened. During-call changes still invalidate results. A previous failed or uncertain request is never replayed merely because a different message arrives.

`POST /review-items/{job_id}/reanalyze` is a separate, explicit merchant decision. It validates active ownership, current authorisation, source availability and the expected current context. It retains the original event identity in internal inbox metadata, queues at most one analysis per original event/context/revision, and never retries unknown or unfinished calls. The account lock serialises requests; deterministic inbox identity is a second fence. Request receipts retain the original command identity. New-order consumption remains unique against the original event, including a reanalysis lineage. No confirmed business mutation or external send occurs on this endpoint.

An old proposal remains unconfirmable after consent withdrawal/regrant. Reanalysis produces a new proposal with current bindings; it does not restore the old one. Per-order message views include only explicit creation sources, field/requirement/change/draft sources and merchant assignments. The full conversation remains a distinct view. Clarification drafts cannot borrow another order's newest message.

Owned chat names are cached on `waha_chats` through additive migration `0024_chat_display_names`, independent of ten-minute discovery-choice expiry. Direct numeric provider addresses display as phone numbers. A provider-only opaque identity cannot be truthfully converted into a phone number; use its known name or an explicit unavailable label.

The existing contract emits one new-order suggestion per model result. Several independent requests in separate messages are handled separately. Several distinct jobs inside one single message may still require the merchant to create additional orders explicitly; this batch does not pretend that the contract is a multi-suggestion array. Model quality is evaluated separately from JSON validity.
