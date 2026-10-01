# AI Job Assistant

AI-powered job application platform: resumes, job search, AI analysis, tailored documents, Gmail outreach and application tracking.

| Part | Folder | Stack |
|---|---|---|
| Backend | `backend/` | FastAPI · Python 3.12 · uv |
| Frontend | `frontend/ai_job_application_frontend/` | React 19 · Vite 8 · JavaScript · Tailwind |
| Infrastructure | `docker-compose.yml` | PostgreSQL · Redis · MinIO · Gotenberg · nginx |

## Branches

| Branch | Contains |
|---|---|
| `backend` | `backend/**` + backend CI |
| `frontend` | `frontend/**` + frontend CI |
| `main` | both, merged, plus shared files (this README, `docker-compose.yml`, `.env.example`) — run the full stack from here |

## Run everything

```bash
cp .env.example .env
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost | Web app |
| http://localhost/system | System Status |
| http://localhost/api/v1/docs | API documentation |
| http://localhost:9001 | MinIO console (from Phase 6) |

Stop: `docker compose down` (add `-v` to also delete database and storage volumes).

## Develop without Docker

See `backend/README.md` and `frontend/ai_job_application_frontend/README.md`.
