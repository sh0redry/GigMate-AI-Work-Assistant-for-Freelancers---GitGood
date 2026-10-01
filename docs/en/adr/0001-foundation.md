# ADR 0001 Foundation architecture

- Status: Accepted; replay foundation implemented in v0.2
- Date: 2026-10-01
- Owner: Repository maintainer

## Decision

Use one repository, a modular backend API, and a separate worker sharing domain code. Select React + TypeScript + Vite, Python + FastAPI + Pydantic, PostgreSQL, SQLAlchemy + Alembic, and Docker Compose. Start with PostgreSQL inbox/outbox/job tables. Pin actual supported runtimes and dependencies at the skeleton milestone; the validation host's Python version is not an application decision.

WAHA and replay are adapters. Replay is the default synthetic development path; live verification and formal commercial access are independent gates.

## Reasons and consequences

One developer can prepare module boundaries without multiple deployments. Coupled business updates use database transactions. Jobs need leases, recovery and reconciliation tests. Add Redis/queues only for measured needs. A TypeScript backend remains an alternative if team expertise changes; replacing this choice requires an ADR and contract continuity.

Review when contributors' expertise, sustained workload or official connector requirements materially change. FastAPI supports OpenAPI and Pydantic-based data handling; see [official features](https://fastapi.tiangolo.com/features/).

## Implementation record 2026-10-01

Python 3.12.10, Node 24.15.0 and PostgreSQL 17.9 are pinned. Native npm 11.12.1 and Linux containers were verified. Locks, migration 0001, Compose and separate worker are implemented. JSON-backed projections keep the initial schema compact; future query scale may require normalized tables. PostgreSQL account locks serialize mutations; jobs use SKIP LOCKED, leases and bounded retries. SQLite is test-only. Authentication is a seeded development session flow; production authentication is pending.
