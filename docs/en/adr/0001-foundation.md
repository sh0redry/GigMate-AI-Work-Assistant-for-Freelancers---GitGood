# ADR 0001 Foundation architecture

- Status: Accepted baseline; implementation pending
- Date: 2026-10-01
- Owner: Repository maintainer

## Decision

Use one repository, a modular backend API, and a separate worker sharing domain code. Select React + TypeScript + Vite, Python + FastAPI + Pydantic, PostgreSQL, SQLAlchemy + Alembic, and Docker Compose. Start with PostgreSQL inbox/outbox/job tables. Pin actual supported runtimes and dependencies at the skeleton milestone; the validation host's Python version is not an application decision.

WAHA and replay are adapters. Replay is the default synthetic development path; live verification and formal commercial access are independent gates.

## Reasons and consequences

One developer can prepare module boundaries without multiple deployments. Coupled business updates use database transactions. Jobs need leases, recovery and reconciliation tests. Add Redis/queues only for measured needs. A TypeScript backend remains an alternative if team expertise changes; replacing this choice requires an ADR and contract continuity.

Review when contributors' expertise, sustained workload or official connector requirements materially change. FastAPI supports OpenAPI and Pydantic-based data handling; see [official features](https://fastapi.tiangolo.com/features/).
