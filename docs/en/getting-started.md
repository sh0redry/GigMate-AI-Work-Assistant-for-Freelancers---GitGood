# Developer onboarding

## Start the replay workspace

Prerequisites: Docker Engine / Docker Desktop with Compose. From the repository root:

```text
docker compose --env-file .env.example -f infra/compose.yaml up --build -d --wait
```

Workspace: http://127.0.0.1:18080. API docs: http://127.0.0.1:18000/docs. PostgreSQL host port: 54329. Ports bind to loopback. The migration service upgrades Alembic and idempotently seeds fictional accounts/appointments, preserving existing data. For custom values copy .env.example to ignored .env and pass --env-file .env.

Sign in as merchant with demo-only-change-me (or the DEMO_PASSWORD used at initial seed). The other account demonstrates isolation. Changing DEMO_PASSWORD later does not rewrite existing password hashes. Replay 15:00 to see a conflict, then 16:30 for a valid proposal. Confirm it to update order/calendar/generated tasks. Fixed event identities make repeated inputs duplicates. There is no real chat, model call or sending.

```text
docker compose --env-file .env.example -f infra/compose.yaml ps
docker compose --env-file .env.example -f infra/compose.yaml logs --tail 50 api worker migrate
docker compose --env-file .env.example -f infra/compose.yaml restart api worker db
docker compose --env-file .env.example -f infra/compose.yaml down
```

down preserves the named database volume. Do not add -v unless intentionally removing development data. API_PORT and WEB_PORT are configurable; adjust TRUSTED_ORIGINS and the Vite proxy when changing ports. The selected 18000/18080 avoid existing services on the validation host.

## Native Windows development

Use Python 3.12.10, Node 24.15.0 and npm 11.12.1. Backend and frontend dependencies are locked. Keep the Compose database running; stop container API/worker before running native equivalents.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r apps/backend/requirements.lock
$env:PYTHONPATH = 'apps/backend/src'
$env:DATABASE_URL = 'postgresql+psycopg://gigmate:local-replay-only@127.0.0.1:54329/gigmate'
.venv/Scripts/python.exe -m alembic -c apps/backend/alembic.ini upgrade head
.venv/Scripts/python.exe -m gigmate.seed
.venv/Scripts/python.exe -m uvicorn gigmate.api:app --host 127.0.0.1 --port 18000
```

In another terminal with the same environment, run:

```text
.venv/Scripts/python.exe -m gigmate.worker
```

From apps/web:

```text
npm ci
npm run dev
```

Vite serves 127.0.0.1:5173 and proxies to 18000. On macOS/Linux use python3.12, .venv/bin/python and export the equivalent PYTHONPATH/DATABASE_URL. Windows native tooling and Linux containers were verified; a separate macOS native run was not performed.

## Required checks

From root, with the environment above:

```text
.venv/Scripts/python.exe -m ruff check apps/backend scripts/export_contracts.py scripts/smoke_replay.py
.venv/Scripts/python.exe -m ruff format --check apps/backend scripts/export_contracts.py scripts/smoke_replay.py
.venv/Scripts/python.exe scripts/export_contracts.py --check
.venv/Scripts/python.exe scripts/check_baseline.py
.venv/Scripts/python.exe -m alembic -c apps/backend/alembic.ini check
```

PostgreSQL tests create isolated random test_gigmate_* schemas, removing only those schemas. The test database user needs schema creation permission.

```powershell
$env:TEST_DATABASE_URL = $env:DATABASE_URL
New-Item -ItemType Directory -Path local-data -Force | Out-Null
.venv/Scripts/python.exe -m pytest apps/backend/tests -q --basetemp=local-data/pytest
```

--basetemp is a disposable test-only directory whose contents pytest replaces. Without TEST_DATABASE_URL, tests use SQLite files and skip the PostgreSQL concurrent-claim test; this does not prove row-lock semantics.

From apps/web:

```text
npm run check:api
npm run format:check
npm run build
```

After model/route changes, run python scripts/export_contracts.py from root and npm run generate:api from apps/web. Commit sources, generated domain/OpenAPI/types and fixtures together. Never edit generated files manually.

Against a running deployment:

```text
.venv/Scripts/python.exe scripts/smoke_replay.py
```

The smoke script changes fictional state on first run, checks persistence on later runs, and never resets the database. Use --password if the seed password differs.

## Limits

The fixed extractor recognizes two fictional text examples; other inputs receive STUB_UNSUPPORTED_INPUT on their durable job. Multiple-order ambiguity records ASSIGNMENT_NEEDS_REVIEW; a dedicated classification UI is pending. Conflict detection covers timed overlaps, not full work hours/travel/buffers. Lists are intended for small demos. External actions, WAHA, media, production authentication, deletion/retention automation and general AI remain pending. See [implementation evidence](implementation-status.md).
