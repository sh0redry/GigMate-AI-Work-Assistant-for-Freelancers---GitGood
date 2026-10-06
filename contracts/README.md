# Shared contracts

Wire version: **0.1.0**; implemented milestone: **v0.2 replay skeleton with opt-in A-03 WAHA ingress/monitoring**. JSON Schema dialect: **2020-12**.

The transition in [ADR 0002](../docs/en/adr/0002-contract-authority.md) is complete: Pydantic models generate the domain schema, implemented routes generate [OpenAPI](openapi.json), and frontend types are generated from that file. Do not edit generated files. Event/AI schemas remain independent. [API agreement](api-v1.md) distinguishes implemented routes from future targets. A model definition does not imply a service exists.

| File | Purpose |
| --- | --- |
| [Domain models](domain/models.schema.json) | Work orders, provenance, calendar values, actions and commands |
| [Event envelope](events/message-event.schema.json) | Adapter-normalized inbound events |
| [AI proposal](ai/change-proposal.schema.json) | Suggestions only, without permission or execution fields |
| [Example manifest](examples/manifest.json) | Every positive and intentionally invalid fixture |
| [Acceptance scenarios](examples/scenarios.json) | Synthetic inputs and expected business behavior |

Fixtures are fictional. Provider IDs use a `synthetic:` namespace. A valid event still requires allowlist and ownership checks; a valid AI proposal still requires provenance and semantic checks; a valid approval command is not proof of authorization.

Use strict objects with additionalProperties=false. JSON timestamps are UTC RFC3339 with a trailing Z, accompanied by IANA timezone where applicable. IDs owned by the application are UUIDs; provider IDs are opaque strings. Enum values are English snake_case. Preserve unknown values explicitly, never infer an address or confirmed amount.

Calendar intervals use ScheduleValue (timed interval or date-only event). Task deadlines use DeadlineValue (one instant or a date), so a task deadline is not forced into an artificial meeting interval. WorkOrder is an initial minimal wire shape; expand requirements through a reviewed contract change rather than adding undeclared fields.

Run the [baseline checker](../docs/en/getting-started.md). Positive fixtures must validate; negative fixtures must fail. Scenario expectations are not executed test results. Application tests must implement the cases independently, including race conditions and persistence.

Breaking field/state changes require a major version/API transition with migration notes. Coordinate optional additions with strict clients. Change schema, manifest, fixtures and affected documentation together. Resolve schema disagreements before implementation.
