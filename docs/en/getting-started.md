# Developer onboarding

## Current capabilities

The repository contains documents, schemas, synthetic fixtures, contribution templates and a baseline checker. There is no application server, database migration or Compose file yet. No WhatsApp or model credential is needed for baseline validation.

Read [scope](overview.md), [architecture](architecture.md), [contributing](contributing.md) and [contracts](../../contracts/README.md) first.

## Run the baseline checks

Use Python 3.11 or newer for validation tooling, from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r scripts/requirements-baseline.txt
.venv\Scripts\python.exe scripts/check_baseline.py
```

On macOS/Linux, use `.venv/bin/python` for the last two commands. The validator pin is not the application's dependency lock.

The checker validates local Markdown links/anchors, JSON/schema references, fixture inventory, positive and negative examples, scenario invariants, English-only root navigation, and required baseline files. It does not execute domain behavior or verify live integration.

## Next skeleton milestone

Add and verify `apps/web/` (React/TypeScript/Vite), `apps/backend/` (FastAPI/Pydantic/SQLAlchemy/Alembic), pinned runtimes and lockfiles, `infra/compose.yaml`, fake `.env.example`, first migration, health checks, account-scoped APIs, persistent worker jobs, and a replay/stub review-confirm-persist flow. Add actual application lint/type/migration/business-test commands to CI.

When implemented, replace this section with tested commands, supported versions, local URLs and a clean-checkout verification record. Do not publish guessed startup commands.

At skeleton acceptance, another contributor or a clean checkout must start replay mode, inspect a source, confirm a change and observe persistence after restart. Aim for 30 minutes after prerequisites; report measured time.
