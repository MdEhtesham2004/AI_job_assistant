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

### Local services (Phase 6)

```bash
docker run -d --name ai-job-redis -p 6379:6379 --restart unless-stopped redis:7-alpine
docker run -d --name ai-job-gotenberg -p 3000:3000 --restart unless-stopped gotenberg/gotenberg:8
```

Files are stored on disk in `backend/storage/` (git-ignored). MinIO is not used: its images are no longer published on Docker Hub.

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
# second terminal — background worker (Windows needs --pool=solo)
uv run celery -A app.workers.celery_app worker --pool=solo -Q default,ai,pdf,email -l info
# third terminal — scheduler for saved searches (exactly one beat process)
uv run celery -A app.workers.celery_app beat -l info
```

## Background tasks (Phase 6)

```text
API: TaskService.create() → tasks row (queued) → commit → Celery "tasks.execute"(task_id)
Worker: run_task() → running → handler → succeeded (result) | retry 10s/30s/90s | failed
      → notification for the user
Browser: polls GET /api/v1/tasks/{id}
```

- Handlers live in `app/workers/handlers/` and register with `@handler("type", "Title")`; add the type to `TASK_QUEUES` in `app/services/tasks.py`.
- `RetryableTaskError` / `ExternalServiceError` → retried (max `TASK_MAX_RETRIES`, default 3); other errors fail at once.
- Files produced by tasks are returned as short-lived signed links: `GET /api/v1/files/{token}` (no auth header; the token is the permission).
- AI: `AiService.complete_json(...)` → budget check → `AiClient` (OpenAI-compatible, strict JSON schema, one repair retry, Redis cache) → row in `ai_calls` with tokens, cost (from OpenRouter) and latency.

| Endpoint | Who | Purpose |
|---|---|---|
| `GET /api/v1/tasks`, `GET /api/v1/tasks/{id}` | user | your tasks / poll one |
| `POST /api/v1/tasks/test-pdf` | user | diagnostic PDF |
| `GET /api/v1/notifications`, `/unread-count`, `POST /{id}/read`, `POST /read-all` | user | in-app notifications |
| `GET /api/v1/admin/system` | admin | health of API, DB, Redis, worker, storage, Gotenberg, AI |
| `POST /api/v1/admin/system/test-failure`, `/test-ai` | admin | diagnostics |

AI requests have one overall deadline (`AI_TIMEOUT_SECONDS`, default 120), an output cap (`AI_MAX_OUTPUT_TOKENS`), low reasoning effort and OpenRouter `provider.sort=throughput` (`AI_PROVIDER_SORT`): cheapest-first routing sent some strict-JSON calls to hosts that looped until the token limit.

## Resumes (Phase 7)

```text
Upload → check type by bytes (PDF %PDF / DOCX word/document.xml), ≤ 5 MB → store file
       → extract text (pypdf / python-docx; image-only files rejected) → new version
       → task resume_parse (AI → structured JSON)
Version → resume_ats (score, section scores, strengths, gaps, roles, suggestions)
        → resume_improve (AI rewrite → grounding check → HTML template → Gotenberg PDF → new "improved" version)
        → resume_linkedin (headline ≤ 220 + About, stored on the ATS report)
```

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/resumes` | your resume and all versions (latest ATS score each) |
| `POST /api/v1/resumes/upload` (multipart `file`) | new version; the first one becomes active; queues parsing |
| `GET /api/v1/resumes/versions/{id}` | parsed content, latest ATS report, running tasks, signed file link |
| `POST /api/v1/resumes/versions/{id}/activate` | make it the active resume |
| `POST /api/v1/resumes/versions/{id}/parse` · `/ats` · `/improve` · `/linkedin-summary` | start an AI task (202 → `task_id`; a running task of the same type is returned instead of a duplicate) |

- Nothing is deleted: every upload and every improved resume is a new version (`kind` master / improved; tailored arrives in Phase 10).
- **No invented facts:** `services/resume_improve.ungrounded_facts()` rejects employers, titles, schools, degrees, skills, certifications and numbers that are not in the original; one retry with the problems listed, then the task fails and nothing is saved. Name, headline and contact details are always copied from the original.
- Prompts are versioned in `app/prompts/resumes.py` (`resume_parse.v1`, `resume_ats.v1`, `resume_improve.v2`, `linkedin_summary.v1`); the version is stored on each AI call and report.

## Jobs (Phase 8)

```text
POST /jobs/search → job_search_runs (queued) + task job_search
Worker: JSearch (code, never the AI) → normalize → store in the shared `jobs` catalog
        → dedupe → link to the user (`user_jobs`) → job_search_results (rank) → run succeeded
Beat (every 5 min): saved searches whose cron time passed (user's time zone) → same task
```

- **Shared catalog:** a job is stored once (`jobs`, unique `source + external_id`); each user's state, notes and pasted description live in `user_jobs`.
- **Dedupe:** same source + id → refreshed (`last_seen_at`); same company + title + city as an active job seen within 30 days → stored as `duplicate` and the user is linked to the original.
- **Description quality:** `complete` (≥ 800 chars with responsibilities/requirements), `partial` (200–799), `missing`. Fix with `POST /jobs/{id}/fetch-description` (public page only: robots.txt, 10 s timeout, private addresses refused, JSON-LD `JobPosting` preferred) or by pasting (`PATCH /jobs/{id}` `description`, private to the user).
- **Quota protection:** at most 5 active saved searches per user, at most one run per hour each; JSearch 401/403/429 fail at once (no retries), 5xx/network errors are retried.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/jobs/search` | start a search → `{task_id, run_id}` |
| `GET /api/v1/jobs/searches`, `/searches/{run_id}` | recent searches / one search with its jobs |
| `GET /api/v1/jobs/suggested-roles` | `top_roles` of the active resume's ATS report + profile location |
| `GET /api/v1/jobs?state=&source=&posted_within_days=&q=&location=&remote_only=&sort=&page=` | your jobs (default: new + saved + analyzed) |
| `GET /api/v1/jobs/counts` | number per state |
| `GET /api/v1/jobs/{id}`, `PATCH /api/v1/jobs/{id}` | detail; state (`new`/`saved`/`skipped`/`archived`), notes, pasted description |
| `POST /api/v1/jobs/{id}/fetch-description` | read the public job page in the background |
| `GET/POST /api/v1/saved-searches`, `PATCH/DELETE /{id}`, `POST /{id}/run` | saved searches (cron schedule, pause, run now) |

## Match scores (Phase 9)

**On demand only** (admin decision): nothing is scored after a search. The user clicks "Get match score" (one job), "Score all …" (unscored jobs in the current view, max 50 per click) or uses Scan.

```text
POST /jobs/{id}/analyze → cached? return at once : task job_analyze
Worker: active parsed resume + job description (pasted one wins) → AI component scores
        (skills, experience, technology, education, location) → backend: weighted score
        (user's weights) + decision (user's thresholds) → job_analyses (one per job + resume version)
```

- The AI never computes the total: `domain/scoring.py` does (deterministic). Skill lists are grounded: "matched" must appear in the resume, "missing" in the job text.
- A new active resume version makes old scores `score_stale` (shown, but not used for sort / minimum-score filters) until rescored.
- Jobs without a usable description cannot be scored (`DESCRIPTION_MISSING`); partial descriptions add a red flag.
- Batch scoring stops at the monthly AI budget and keeps what is done. Prompt `job_match.v2` (v1 scored far too low — no scale).
- Cost measured live: ≈ $0.0007 per job, 3–4 s.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/jobs/{id}/analyze` (`{"force": true}` to rescore) | score one job → `{task_id, cached}` |
| `GET /api/v1/jobs/analysis-summary?…filters` | how many jobs in this view still need a score |
| `POST /api/v1/jobs/analyze-batch?…filters` | score the unscored jobs of this view |
| `POST /api/v1/jobs/scan-text` | score a pasted job description (saved as a private job) |
| `GET /api/v1/jobs?sort=score&min_score=65` | sort / filter by score |

The CSV export fills *Match score, Matching skills, Missing skills, Scored*.

## Tailored resumes & cover letters (Phase 10)

```text
POST /jobs/{id}/tailored-resume → task resume_tailor:
  active resume (parsed) + job text + match analysis hints → AI (structured resume)
  → grounding check (no new employers/titles/schools/skills/numbers, one retry)
  → name/headline/contact copied from the original, "missing" skills stripped
  → HTML template → Gotenberg PDF → resume_versions (kind = tailored, job_id)
POST /jobs/{id}/cover-letter {contact_name?} → task cover_letter:
  tailored resume for this job if any, else the active one → AI (3-4 paragraphs)
  → checks: placeholders, numbers, skills the analysis says you lack, company + role named,
    120-450 words (one retry) → "Dear …," + body + "Sincerely" → PDF → cover_letters
```

- User edits are saved even when the checks object; the warnings are returned with the documents (`GET /jobs/{id}/documents`) and shown in the UI.
- Prompts `resume_tailor.v1`, `cover_letter.v2` (v1 claimed "led", CI, agile, APIs — not in the resume).
- Cost measured live: ≈ $0.0003–0.0007 per document, 3–4 s.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/jobs/{id}/documents` | latest tailored resume (+ the master it came from) and cover letter, warnings, running tasks |
| `POST /api/v1/jobs/{id}/tailored-resume` | generate a tailored resume (new version) |
| `POST /api/v1/jobs/{id}/cover-letter` | generate a cover letter (`contact_name` optional) |
| `PUT /api/v1/resumes/versions/{id}/content` | edit a tailored resume (structured) → new PDF |
| `PATCH /api/v1/cover-letters/{id}` | edit text and/or `status` (`draft`/`final`) → new PDF |

## Applications (Phase 11)

One application per job per user (`uq_applications_user_id_job_id`). Every status change goes through `domain/state_machine.check()` and writes one append-only `application_status_history` row in the same transaction.

```text
ready_to_apply → waiting_for_approval → approved → sending → applied      (email, Phase 12)
ready_to_apply → applied                                                   (portal / referral: "Mark as applied")
applied → responded / interview / no_response → offer | rejected;  any open state → withdrawn
```

- People cannot set `sending`/`failed` (the email sender does); approval steps exist only for the email channel and happen in the Outbox (Phase 12), never as a bare status change; email applications become `applied` only when sent.
- Resume, cover letter and channel can change until the application goes out (`APPLICATION_LOCKED` after); the next action can always change.
- Default resume: the job's tailored version, else the active one.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/jobs/{id}/applications` | prepare (channel, resume, cover letter, next action) |
| `GET /api/v1/jobs/{id}/application` | the application for a job, or `null` |
| `GET /api/v1/applications?status=…&status=…&channel=&q=&sort=` | list (board / table) |
| `GET /api/v1/applications/counts` · `/export.csv` | per-status counts · CSV (Excel-safe) |
| `GET/PATCH /api/v1/applications/{id}` | detail with timeline + `allowed_next` · edit |
| `POST /api/v1/applications/{id}/status` · `/mark-applied` | move (409 `INVALID_TRANSITION`) · portal/referral applied |

## Contacts & Gmail outreach (Phase 12)

Needs `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY` (and `APIFY_TOKEN` for LinkedIn) in `.env`, and **Celery Beat running** — it starts scheduled sends every minute (`tasks.dispatch_outbox`).

- **Gmail:** OAuth (scopes `gmail.send` + `gmail.readonly`), tokens Fernet-encrypted in `oauth_accounts`; the `state` is a signed, one-time token (nonce in Redis).
- **Contacts:** LinkedIn hiring posts via Apify (`"Hiring" AND "<role>" AND "gmail.com"`, setting *LinkedIn hiring posts* must be on) — each post with an email becomes a **private job** (`source = linkedin_post`) plus a **pending** contact with the post URL and excerpt as evidence; or added by hand (approved at once). Syntax + MX check; `invalid` can never be approved; the do-not-contact list (emails and whole domains) always wins.
- **Emails:** AI draft (`application_email.v1`, same truth checks as cover letters + "mentions the attachment") → edit → approve → scheduled slot (daily cap, gap + jitter, next day 09:00 when the cap is reached) → pre-send checks → Gmail upload API with resume (+ cover letter) attached → application `applied`.
- **No double send:** one outbound email per (user, application, type) via the unique `idempotency_key`; `queued → sending` is one conditional UPDATE; approving twice is a no-op. A send Gmail did not answer stays `sending` and is reconciled after 5 min by its `Message-ID` (`rfc822msgid:` search).

```text
email: draft → queued (approved) → sending → sent | failed      draft → rejected
application: ready_to_apply → waiting_for_approval → approved → sending → applied | failed
```

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/integrations/gmail` · `POST …/connect` · `GET …/callback` · `DELETE` | status · consent URL · Google redirect · disconnect |
| `GET/POST /api/v1/contacts` · `PATCH/DELETE /contacts/{id}` · `POST /contacts/{id}/verify` | list/add · edit, approve, reject · re-check |
| `POST /api/v1/contacts/discover` | LinkedIn hiring posts (task) |
| `GET/POST /api/v1/do-not-contact` · `DELETE /do-not-contact/{id}` | blocked addresses / domains |
| `POST /api/v1/applications/{id}/email/draft` · `GET …/email` | AI draft (task) · the application's email |
| `GET /api/v1/outbox?status=…` · `/outbox/summary` | drafts, scheduled, sent, failed · counts + limits |
| `PUT /api/v1/emails/{id}` · `POST …/approve` · `/reject` · `/cancel` · `/retry` · `POST /emails/approve-batch` | edit draft · actions |

## Replies & automation (Phase 13)

Celery Beat runs `tasks.poll_replies` every 5 minutes. Automation has **no schedule**: it runs only from the Outbox ("Automate").

- **Replies:** Gmail `history.list` since the stored `gmail_history_id` (first poll / expired id: read the tracked threads once). New messages in threads of sent applications are stored as inbound `emails`; our own mail (it carries `X-App-Idempotency-Key`) and the user's replies to others are skipped.
  - **Bounce** (mailer-daemon / delivery-failure subject) → email `bounced`, contact `invalid`, application `failed` (no AI call).
  - Otherwise AI `reply_classify.v1` → `reply_classifications`. Confidence ≥ 0.80 → status change with source `email_reply` (interview_invite → interview, info_request/other → responded, rejection → rejected, offer → offer, auto_reply → none) and the suggested next action; below → notification + "confirm" prompt (`POST /replies/{id}/confirm`).
  - "Do not contact me" → sender on the do-not-contact list. Any reply cancels a pending follow-up.
- **Follow-ups:** after `follow_up_days` without a reply, one `follow_up_1` draft (AI `follow_up.v1`) waits for approval; it is sent in the same Gmail thread (`threadId` + `In-Reply-To` = Gmail's real Message-ID, saved after each send) and never changes the application status.
- **No response:** email applications still `applied` after `no_response_days` (counted from the last email) → `no_response`.
- **Automation** — started by the user, at most `automation_max_jobs` per run, two modes:
  - `saved` (always available, no Apify): jobs in the user's list (not skipped/archived) with an **approved** contact and no application → match score (reused if one exists for the active resume) → if ≥ `automation_min_score`: tailored resume (when the analysis says *tailor*) + cover letter → email application → AI draft → Outbox *Ready for approval*.
  - `fetch` (Apify): **locked until an admin enables it** (`app_settings.automation_fetch_enabled`, Settings › Platform, audited). LinkedIn hiring posts for each keyword (≤ 5) → private jobs + pending contacts, then the same steps for those and the saved jobs. A pending contact is approved together with its email ("Approve contact & send"), with the post shown as evidence. Keywords that find no post are reported (`empty_keywords`).

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/automation` · `POST /automation/run {mode: saved\|fetch}` | ready saved jobs, fetch lock, last run · start (task `automation_run`) |
| `GET/PATCH /api/v1/admin/platform` | admin: `automation_fetch_enabled` |
| `GET /api/v1/applications/{id}/replies` | replies with their AI reading |
| `POST /api/v1/replies/{id}/confirm` `{accept}` | confirm / dismiss an unsure reading |
| `POST /api/v1/emails/{id}/approve?approve_contact=true` · `approve-batch {approve_contacts}` | approve a pending contact with its email |

## Dashboard, admin insights, account data, import, hardening (Phase 14)

- **Dashboard** `GET /api/v1/dashboard`: stage counts use the Applications board groups (so both pages agree); interviews/offers/rejected count applications that *ever* reached them (timeline); response rate by job source and resume kind; recent activity.
- **Notification centre** `GET /api/v1/notifications?category=email|replies|jobs|tasks|other&unread_only=`.
- **Admin** `GET /api/v1/admin/audit` · `/admin/analytics` · `/admin/errors` · `POST /admin/system/test-error` (monitoring check).
- **Account** `GET /api/v1/users/me/export` (ZIP: JSON per table + stored files, no secrets) · `POST /users/me/delete` `{password, confirm_email}` (last admin refused, Gmail revoked, files removed, audited).
- **Legacy import** `POST /api/v1/imports/legacy` (CSV of the old job list or LinkedIn Leads; headers matched loosely; idempotent; lead contacts *pending*).
- **Hardening**: security headers (CSP on JSON, HSTS in production), `MAX_REQUEST_BYTES` (10 MB), per-IP `API_RATE_LIMIT_PER_MINUTE` (600), optional Sentry (`SENTRY_DSN`; tokens, cookies and bodies scrubbed).
- **Production**: `docker-compose.prod.yml`, `docker-compose.https.yml`, `scripts/backup.sh` / `scripts/restore.sh` — see `../DEPLOYMENT.md`.

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

## Users & admin (Phase 5)

| Endpoint | Who | Purpose |
|---|---|---|
| `PATCH /api/v1/users/me` | approved user | change your name |
| `GET/PUT /api/v1/users/me/profile` | approved user | phone, location, headline, links, time zone |
| `GET/PATCH /api/v1/users/me/settings` | approved user | thresholds, score weights (sum 100), sending limits, automation, AI budget |
| `GET /api/v1/admin/users?status=&q=&page=&page_size=` | admin | accounts, pending first |
| `GET /api/v1/admin/users/counts` | admin | number per status |
| `POST /api/v1/admin/users/{id}/approve` · `/reject` · `/deactivate` · `/reactivate` | admin | account actions |
| `PATCH /api/v1/admin/users/{id}/role` | admin | make / remove admin |

Rules: admins cannot act on themselves; the last active admin cannot be removed; only pending accounts can be rejected; reject/deactivate revoke all sessions; every action is audited.

**Ownership:** user-owned tables use `OwnedRepository(session, owner_id)` — every query is filtered by `user_id`, rows of other users behave as "not found". Every new user-owned endpoint needs a test in `tests/test_isolation.py`.

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
├── domain/              pure rules: job quality/dedupe/query, cron schedules (Phase 8)
├── integrations/        storage, Gotenberg, AI client, JSearch, job page reader
├── models/              SQLAlchemy models: accounts, system, resumes, jobs
├── prompts/             versioned AI prompts + their structured outputs (Phase 7)
├── repositories/        database access (no commits)
├── schemas/             Pydantic request/response models
├── services/            business logic
└── workers/             Celery app, task runner, handlers/
migrations/              Alembic environment + versions/0001_core.py … 0010_applications.py
tests/
```

## Error format

```json
{ "error": { "code": "NOT_FOUND", "message": "…", "details": {}, "request_id": "…" } }
```

Every response carries an `X-Request-ID` header that matches the `request_id` in the logs.
