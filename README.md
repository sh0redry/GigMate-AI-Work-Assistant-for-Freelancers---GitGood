# 跟單 · GigMate

**Live demo: [https://gigmate.duckdns.org](https://gigmate.duckdns.org)**

[![Engineering baseline](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/workflows/baseline.yml/badge.svg)](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/workflows/baseline.yml)
[![Replay skeleton](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/workflows/skeleton.yml/badge.svg)](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/workflows/skeleton.yml)
[![Desktop release](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/workflows/desktop-release.yml/badge.svg)](https://github.com/sh0redry/GigMate-AI-Work-Assistant-for-Freelancers---GitGood/actions/workflows/desktop-release.yml)

A WhatsApp business coordination assistant for merchants and freelancers. It turns ongoing conversations into reviewable requirements, work orders, tasks, and personal schedules, while keeping the merchant in control of customer-facing actions.

Customers keep using their existing chat. The merchant uses a mobile-friendly workspace to review changes, resolve missing information, check scheduling conflicts, and approve messages.

## Live demo

A hosted snapshot runs at [https://gigmate.duckdns.org](https://gigmate.duckdns.org) (team domain, Caddy with automatic HTTPS).

- Sign in with the seeded development accounts `merchant` and `other`; sample password `demo-only-change-me`.
- It is a **review demonstration, not a service**: anyone who knows the password can sign in, and no gateway or rate limit protects the login path. **Never enter real customer conversations, credentials or personal data.**
- Availability depends on the team server and the DuckDNS domain, so the link can go offline without notice. The supported way to use GigMate is the local installation below.

## Repository status

**Local application with real WhatsApp reception, reviewed model suggestions and explicitly approved sending.** Each user runs their own backend, worker, PostgreSQL and WAHA on their computer. No team server is required. Model calls require that user's private configuration. Suggestions and drafts never automatically confirm orders or send messages.

Calendar export/import is supported; continuous synchronization with external calendar services has not been implemented.

## Highlights

- **Real reception, controlled sending.** WhatsApp messages arrive through a local WAHA connector; every outbound message needs the sending switch, per-chat permission and explicit approval of the exact payload.
- **Proposal first, never auto-send.** Models only draft; server-side rules own approval, version checks and execution.
- **Three separate facts.** Customer proposal, customer confirmation and merchant approval are distinct records.
- **Source message retained.** Critical fields keep their originating message revisions; unknown values stay missing instead of being guessed.
- **Conflict-aware scheduling.** Requests are shown with proposed time, missing fields and calendar conflicts before confirmation.
- **Durable by construction.** Jobs, state, version checks, unique constraints, leases and a transactional outbox; unknown send outcomes are reconciled, never blindly resent.
- **Private model configuration.** API keys live in the ignored `.env` and reach backend services only through a private file volume.

## Run locally

Install Python 3.12 and Docker Desktop / Docker Engine with Compose. From the repository root on macOS/Linux:

```text
python3.12 -m venv .venv
.venv/bin/python -m pip install -r apps/backend/requirements.lock
cp .env.example .env
.venv/bin/python scripts/start_product.py --init
```

Open [GigMate](http://127.0.0.1:18780). On Windows use `py -3.12`, `.venv/Scripts/python.exe` and `Copy-Item .env.example .env`. Run `--init` only on the first installation. Existing installations run `scripts/start_product.py` without `--init`; this preserves their data and WhatsApp session while rebuilding the matching frontend/backend/worker and checking the backend contract. Do not replace an existing private `.env`.

New installations contain no fictional chats or work orders. Set your private `GIGMATE_USERNAME` / `GIGMATE_PASSWORD` in `.env`, or use the randomly generated login saved in ignored `local-data/waha-a02/login.json`. Existing logins are not reset. Open **WhatsApp connection** to link your phone and authorize the conversations to process. The sending server switch, per-chat sending permission and approval of each exact message remain separate.

Enter your own model API key and the required provider, prices, budget, token limits and timezone in ignored `.env`; see [private configuration](docs/en/adr/0008-vendor-selection-and-private-configuration.md). The launcher passes the model key only to backend services through a private file volume. Without model configuration, manual order management remains available and automatic understanding remains unavailable. API keys, QR codes, WhatsApp sessions and business data must never be uploaded to GitHub.

## Workflow

1. Receive a customer's rescheduling request and retain the source message.
2. Associate it with a work order; show the proposed time, missing address, and conflict.
3. Let the merchant approve a clarification message.
4. Process the customer's reply and request approval for the confirmed update.
5. Update the work order, tasks, calendar, and reminders; show execution results.

A proposal is not a confirmed commitment. AI produces suggestions; server-side rules control approval and execution.

## Repository layout

```text
apps/backend/   FastAPI + Pydantic API, domain contracts, approvals, worker, Alembic migrations
apps/web/       React + TypeScript workspace (Vite), generated API types
apps/desktop/   packaged desktop delivery and preview tooling
infra/          Compose files, images and edge configs for local and cloud runs
contracts/      shared schemas and synthetic examples (machine-generated parts)
docs/           English and Chinese documentation, ADRs, acceptance records
scripts/        launcher, validations, smoke and recovery checks
```

## Verify a change

From the repository root:

```text
python scripts/check_baseline.py                 # documentation + synthetic contracts
python scripts/export_contracts.py --check       # generated schema is up to date
python -m pytest apps/backend/tests -q           # PostgreSQL suite before a PR
```

From `apps/web`: `npm run check:api`, `npm run format:check`, `npm run build`. SQLite runs do not prove PostgreSQL locking behaviour; use `TEST_DATABASE_URL` as described in [the onboarding guide](docs/en/getting-started.md).

## Documentation

- [Documentation index](docs/en/README.md) · [Product scope](docs/en/overview.md) · [Architecture and module boundaries](docs/en/architecture.md)
- [Developer onboarding](docs/en/getting-started.md) · [Contribution and review process](docs/en/contributing.md)
- [Architecture decisions](docs/en/adr/README.md) · [Implementation status and validation](docs/en/implementation-status.md)
- [Shared contracts and synthetic examples](contracts/README.md)

## Foundation and delivery

React and TypeScript for the workspace; FastAPI/Pydantic for the API; PostgreSQL for state and jobs; SQLAlchemy/Alembic for migrations; an independent worker; Docker Compose. Python 3.12.10, Node 24.15.0 and PostgreSQL 17.9 are pinned, with backend and frontend dependency locks.

The user application serves compiled web assets and one same-origin API. It contains no environment switch or replay controls, and product mode refuses fixture ingestion. Automated synthetic fixtures remain developer verification tools, with no service started by the user launcher. Current platform, model, media and delivery limits are recorded in [implementation status](docs/en/implementation-status.md); a packaged exe/app and distribution signing remain separate delivery work. WAHA is unofficial; see the [WAHA disclaimer](https://waha.devlike.pro/docs/overview/introduction/).

## Contributing

Start with the [onboarding guide](docs/en/getting-started.md) and [contribution rules](docs/en/contributing.md). Work from a scoped issue, preserve shared contracts, and include validation evidence in each PR. Use synthetic examples; never commit credentials, session material, or real customer conversations.

No project license has been selected yet. The maintainer must record the licensing decision before inviting redistribution.
