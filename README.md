# 跟單 · GigMate

A WhatsApp business coordination assistant for merchants and freelancers. It turns ongoing conversations into reviewable requirements, work orders, tasks, and personal schedules, while keeping the merchant in control of customer-facing actions.

Customers keep using their existing chat. The merchant uses a mobile-friendly workspace to review changes, resolve missing information, check scheduling conflicts, and approve messages.

## Repository status

**Engineering skeleton v0.2 — runnable synthetic replay.** The workspace, API, PostgreSQL migration, independent worker, development authentication, proposal confirmation and persistence are implemented. Live WhatsApp integration, general AI extraction and external sending have not been implemented. This is a development skeleton, not a production deployment.

## Run locally

With Docker Engine / Docker Desktop and Compose running, execute from the repository root:

```text
docker compose --env-file .env.example -f infra/compose.yaml up --build -d --wait
```

Open [the replay workspace](http://127.0.0.1:18080). Development accounts: merchant and other. Sample password: demo-only-change-me. Replay the conflicting 15:00 request, then the available 16:30 request; confirm the latter to persist order/calendar/task changes. No real account credentials are needed. See onboarding for overrides and checks.

## Target P0 workflow

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
- [Implementation status and validation](docs/en/implementation-status.md)
- [Shared contracts and synthetic examples](contracts/README.md)

## Planned foundation

React and TypeScript for the workspace; FastAPI/Pydantic for the API; PostgreSQL for state and jobs; SQLAlchemy/Alembic for migrations; an independent worker; Docker Compose. Python 3.12.10, Node 24.15.0 and PostgreSQL 17.9 are pinned, with backend and frontend dependency locks.

The prototype connector is planned as a WAHA adapter alongside a replay adapter. WAHA is unofficial and does not guarantee protection from account blocking. Live integration must be verified separately from replay; commercial integration is a separate decision. See the [WAHA disclaimer](https://waha.devlike.pro/docs/overview/introduction/).

## Contributing

Start with the [onboarding guide](docs/en/getting-started.md) and [contribution rules](docs/en/contributing.md). Work from a scoped issue, preserve shared contracts, and include validation evidence in each PR. Use synthetic examples; never commit credentials, session material, or real customer conversations.

No project license has been selected yet. The maintainer must record the licensing decision before inviting redistribution.
