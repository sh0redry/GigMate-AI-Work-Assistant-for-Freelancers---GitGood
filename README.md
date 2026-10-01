# 跟單 · GigMate

A WhatsApp business coordination assistant for merchants and freelancers. It turns ongoing conversations into reviewable requirements, work orders, tasks, and personal schedules, while keeping the merchant in control of customer-facing actions.

Customers keep using their existing chat. The merchant uses a mobile-friendly workspace to review changes, resolve missing information, check scheduling conflicts, and approve messages.

## Repository status

**Engineering baseline v0.1 — documentation and contracts.** Application services, database migrations, live WhatsApp integration, and business tests have not been implemented yet. This repository does not currently provide a running product. The next milestone is a reproducible environment and a minimal replay-driven workflow.

## First workflow

1. Receive a customer's rescheduling request and retain the source message.
2. Associate it with a work order; show the proposed time, missing address, and conflict.
3. Let the merchant approve a clarification message.
4. Process the customer's reply and request approval for the confirmed update.
5. Update the work order, tasks, calendar, and reminders; show execution results.

A proposal is not a confirmed commitment. AI produces suggestions; server-side rules control approval and execution.

## Documentation

- [Documentation index](docs/en/README.md)
- [Product scope](docs/en/overview.md)
- [Architecture and module boundaries](docs/en/architecture.md)
- [Developer onboarding](docs/en/getting-started.md)
- [Contribution and review process](docs/en/contributing.md)
- [Architecture decisions](docs/en/adr/README.md)
- [Shared contracts and synthetic examples](contracts/README.md)

## Planned foundation

React and TypeScript for the workspace; FastAPI and Pydantic for the API; PostgreSQL for durable business state and jobs; SQLAlchemy and Alembic for migrations; an independent worker sharing backend code; Docker Compose for local development. Exact runtime and dependency versions will be pinned during the skeleton milestone.

The prototype connector is planned as a WAHA adapter alongside a replay adapter. WAHA is unofficial and does not guarantee protection from account blocking. Live integration must be verified separately from replay; commercial integration is a separate decision. See the [WAHA disclaimer](https://waha.devlike.pro/docs/overview/introduction/).

## Contributing

Start with the [onboarding guide](docs/en/getting-started.md) and [contribution rules](docs/en/contributing.md). Work from a scoped issue, preserve shared contracts, and include validation evidence in each PR. Use synthetic examples; never commit credentials, session material, or real customer conversations.

No project license has been selected yet. The maintainer must record the licensing decision before inviting redistribution.
