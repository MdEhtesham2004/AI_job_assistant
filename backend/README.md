# Backend — AI Job Application Platform

FastAPI service. Architecture: `assets/phase-1/system_architecture.md`.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## Run locally

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

- Health: http://localhost:8000/api/v1/health
- API docs: http://localhost:8000/api/v1/docs

## Checks

```bash
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy app          # types
```

## Structure

```text
app/
├── main.py              create_app(): middleware, error handlers, routers
├── api/
│   ├── deps.py          shared dependencies
│   └── v1/
│       ├── router.py
│       └── routes/      one module per resource
├── core/                config, logging, middleware (request id), errors
└── schemas/             Pydantic request/response models
tests/
```

Further folders (`models/`, `repositories/`, `services/`, `domain/`, `integrations/`, `workers/`, `migrations/`) are added in the phases that need them.

## Error format

```json
{ "error": { "code": "NOT_FOUND", "message": "…", "details": {}, "request_id": "…" } }
```

Every response carries an `X-Request-ID` header that matches the `request_id` in the logs.
