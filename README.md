# AI Job Assistant

AI-powered job application platform: resumes, job search, AI analysis, tailored documents, Gmail outreach and application tracking.

| Part | Folder | Stack |
|---|---|---|
| Backend | `backend/` | FastAPI · Python 3.12 · uv · Celery |
| Frontend | `frontend/ai_job_application_frontend/` | React 19 · Vite 8 · JavaScript · Tailwind |
| Infrastructure | `docker-compose.yml` (local) · `docker-compose.prod.yml` | PostgreSQL · Redis · Gotenberg · nginx |

## Branches

| Branch | Contains |
|---|---|
| `backend` | `backend/**` + backend CI |
| `frontend` | `frontend/**` + frontend CI |
| `main` | both, merged, plus shared files (this README, compose files, `.env.example`) — run the full stack from here |

## Run everything locally

```bash
cp .env.example .env          # optional: ports and database password
docker compose up -d --build
docker compose exec api python -m app.cli create-admin
```

Services: `web` (nginx + React), `api`, `worker` and `beat` (Celery), `migrate` (runs once),
`postgres`, `redis`, `gotenberg`. Files are stored in the `storage_data` volume. API keys are
read from `backend/.env` when it exists.

| URL | What |
|---|---|
| http://localhost:8081 | Web app |
| http://localhost:8081/system | System Status |
| http://localhost:8081/api/v1/docs | API documentation |

Stop: `docker compose down` (add `-v` to also delete the database and file volumes).

Gmail sign-in from this stack needs `GOOGLE_REDIRECT_URI` (in `backend/.env`) and the Google
Cloud OAuth client set to `http://localhost:8081/api/v1/integrations/gmail/callback`.

## Production

See `DEPLOYMENT.md` (`docker-compose.prod.yml`, HTTPS, backups and restore).

## Develop without Docker

See `backend/README.md` and `frontend/ai_job_application_frontend/README.md`.
