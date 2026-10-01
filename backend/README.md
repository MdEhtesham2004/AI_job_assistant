# Backend — AI Job Application Platform

FastAPI service. Architecture: `assets/phase-1/system_architecture.md`. Database design: `assets/phase-0/database_design.md`.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 16 with two databases: `jobs` (development) and `jobs_test` (automated tests)

## First-time setup (fresh install)

```bash
cd backend
cp .env.example .env          # then fill in the database password
uv sync                       # install dependencies
uv run alembic upgrade head   # create all tables in the `jobs` database
uv run python -m app.cli create-admin --email you@example.com --full-name "Your Name"
```

`create-admin` asks for the password (min. 12 characters) or reads `ADMIN_PASSWORD`. Running it again for the same email promotes/approves the account without changing its password.

### PostgreSQL in Docker (development)

```bash
docker run -d --name ai-job-postgres -e POSTGRES_USER=app -e POSTGRES_PASSWORD=<password> \
  -e POSTGRES_DB=jobs -p 5432:5432 -v ai_job_pgdata:/var/lib/postgresql/data \
  --restart unless-stopped postgres:16-alpine
docker exec -it ai-job-postgres psql -U app -d jobs -c "CREATE DATABASE jobs_test;"
```

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

- Health (API + database + migration revision): http://localhost:8000/api/v1/health
- API docs: http://localhost:8000/api/v1/docs

## Authentication (Phase 4)

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/register` | create account (status **pending** until an admin approves) → session |
| `POST /api/v1/auth/login` | sign in → `{access_token, expires_in, user}` + refresh cookie |
| `POST /api/v1/auth/refresh` | new access token from the refresh cookie (cookie is rotated) |
| `POST /api/v1/auth/logout` | revoke the session, clear the cookie |
| `POST /api/v1/auth/change-password` | requires current password; signs out other devices |
| `POST /api/v1/auth/forgot-password` / `reset-password` | reset-token flow (email delivery arrives in Phase 12; in development the token is written to the server log) |
| `GET /api/v1/users/me` | the signed-in user (also for pending accounts) |

- Access token: JWT (HS256, `SECRET_KEY`), 15 minutes, sent as `Authorization: Bearer …`, kept in browser memory only.
- Refresh token: random, 14 days, **httpOnly + SameSite=Strict** cookie on `/api/v1/auth`, stored only as SHA-256. Every refresh rotates it; reusing an old token signs out that whole session (theft detection). Reuse within 10 s answers `REFRESH_RACE` (parallel tabs) and the client retries.
- Pending accounts can sign in and call `/users/me`; feature routes (`ApprovedUser` dependency) answer `403 ACCOUNT_PENDING`. Rejected/deactivated accounts cannot sign in (`ACCOUNT_REJECTED`, `ACCOUNT_DEACTIVATED`).
- Auth endpoints are rate limited per IP (in-process; Redis later).

## Migrations (Alembic)

| Command | Purpose |
|---|---|
| `uv run alembic upgrade head` | apply all migrations |
| `uv run alembic current` | show the applied revision |
| `uv run alembic check` | fail if models and database differ |
| `uv run alembic revision --autogenerate --rev-id 0002 -m "…"` | new migration (review by hand!) |
| `uv run alembic downgrade -1` | undo the last migration |

Rules: one migration per phase; only the tables that phase needs; never edit an applied migration.

## Checks

```bash
uv run pytest            # tests — uses TEST_DATABASE_URL (*_test only), rebuilds it via migrations
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy app          # types
```

## Structure

```text
app/
├── main.py              create_app(): middleware, error handlers, routers, DB engine
├── cli.py               command-line tasks (create-admin)
├── api/
│   ├── deps.py          settings, engine, per-request DB session
│   └── v1/routes/       one module per resource
├── core/                config, logging, middleware (request id), errors, security (Argon2)
├── db/                  declarative base (naming convention, enum helper), engine/session
├── models/              SQLAlchemy models: accounts (users), system (tasks, audit_logs)
├── repositories/        database access (no commits)
├── schemas/             Pydantic request/response models
└── services/            business logic (health checks, admin seed)
migrations/              Alembic environment + versions/0001_core.py
tests/
```

Further folders (`domain/`, `integrations/`, `workers/`) are added in the phases that need them.

## Error format

```json
{ "error": { "code": "NOT_FOUND", "message": "…", "details": {}, "request_id": "…" } }
```

Every response carries an `X-Request-ID` header that matches the `request_id` in the logs.
