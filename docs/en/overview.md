# Product scope

跟單 / GigMate helps merchants and freelancers maintain existing business commitments formed through WhatsApp conversations. It tracks ongoing changes; customers do not need a new application.

## Shared P0 scenario

Receive both parties' text messages, identify a work order, propose sourced changes, detect a missing address and calendar conflict, approve clarification, process the reply, approve a formal update, replace affected tasks/calendar/reminders, and expose execution results.

The synthetic scenario starts with an appointment on 2026-10-07 at 15:00–16:00 Asia/Hong_Kong and a conflict on 2026-10-08 at 15:00–16:00. Suggested alternatives must come from computed availability. “可以” to a time question does not supply an address.

| Level | Capability | Gate |
| --- | --- | --- |
| P0 | Two-way real text ingestion and connection state | Independent test-account evidence |
| P0 | Work orders, provenance, proposed changes and ambiguous assignment | Proposed and confirmed facts remain separate |
| P0 | Merchant review, tasks, internal calendar and conflicts | Server-side ownership, approval and version checks |
| P0 | Approved text sending and reconciliation | Unknown outcomes never cause blind resend |
| P1 | One media type, summary, explicit reminder authorization | P0 acceptance first |
| Later | External calendar, templates, recurring work, payment records, group chat | Separate decisions and cases |

Excluded: customer matching, commissions, fund custody, AI pricing/negotiation, refunds, legal claims, rostering, inventory and safety-critical scheduling.

## Assumptions and delivery layers

One merchant manages personal work, but accounts are isolated from day one. Developer collaboration does not add employee-management features. Only authorized conversations enter business processing. Initial input is text. Default business display timezone is Asia/Hong_Kong; message time and explicit account settings govern relative dates.

The documentation milestone defines rules and fixtures. The skeleton milestone proves a persisted replay flow with an extraction stub. Full P0 additionally requires real connector evidence, model evaluation and business exception tests. User benefits remain hypotheses until measured.
