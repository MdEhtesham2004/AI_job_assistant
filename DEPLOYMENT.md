# Deployment & operations (Phase 14)

The production stack is `docker-compose.prod.yml`: **web** (Nginx + React build, the only
published port), **api** (FastAPI), **worker** + **beat** (Celery), **migrate** (one-shot
`alembic upgrade head`), **postgres**, **redis**, **gotenberg** and **backup**. Files
(resumes, PDFs) live in the `storage_data` volume and are part of every backup.

## 1. First deployment

Requirements: a Linux server (Ubuntu 22.04+, 2 vCPU / 4 GB RAM is plenty), Docker Engine with
the compose plugin, a domain pointing at the server (A record).

```bash
git clone https://github.com/MdEhtesham2004/AI_job_assistant.git && cd AI_job_assistant
cp .env.prod.example .env.prod        # fill in every <…> value (see the comments)
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec api \
    python -m app.cli create-admin --email you@example.com      # asks for a password
```

Check: `http://<server>/` shows the sign-in page, `http://<server>/api/v1/health` is `ok`,
`docker compose … ps` shows every service healthy, `migrate` *exited (0)*.

## 2. HTTPS (Let's Encrypt)

1. Set `SERVER_NAME=jobs.example.com` and `PUBLIC_URL`, `CORS_ORIGINS`, `FRONTEND_URL`,
   `GOOGLE_REDIRECT_URI` to the `https://` address in `.env.prod`.
2. Get the first certificate while the HTTP stack is running (the web server already serves
   `/.well-known/acme-challenge/`):
   ```bash
   docker run --rm -v /etc/letsencrypt:/etc/letsencrypt \
     -v ai-job-platform-prod_certbot_www:/var/www/certbot certbot/certbot certonly \
     --webroot -w /var/www/certbot -d jobs.example.com --email you@example.com --agree-tos -n
   ```
3. Switch to HTTPS (port 80 then only redirects; `certbot` renews automatically):
   ```bash
   docker compose -f docker-compose.prod.yml -f docker-compose.https.yml --env-file .env.prod up -d
   ```

Security headers (HSTS, CSP for the API, nosniff, frame-deny), the API rate limit
(Nginx `limit_req` + an in-app per-IP budget) and the 6 MB upload limit are on by default.

## 3. Gmail in production

- Google Cloud › Credentials › your OAuth client: add the production redirect URI
  `https://jobs.example.com/api/v1/integrations/gmail/callback`.
- While the consent screen is in **Testing**, only the listed *test users* (max 100) can
  connect Gmail, and Google expires their grant after 7 days (users must reconnect).
- `gmail.send` and `gmail.readonly` are **restricted scopes**. To open the app to anyone
  you need Google's **app verification** (privacy policy URL, domain verification, a demo
  video) and, for `gmail.readonly`, a yearly third-party security assessment (CASA). For a
  small group, staying in Testing mode is the practical choice.
- Keep `TOKEN_ENCRYPTION_KEY` forever: changing it makes every stored Gmail token unreadable.

## 4. Backups and restore

The `backup` service writes, once a day, to `BACKUP_DIR` (default `./backups`):
`db_<time>.dump` (PostgreSQL custom format) and `files_<time>.tar.gz` (the storage volume),
and deletes copies older than `BACKUP_KEEP_DAYS` (14). **Copy `BACKUP_DIR` off the server**
(e.g. a nightly `rclone`/`rsync` to another machine or bucket) — a backup on the same disk
does not survive a lost server.

```bash
# backup now
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backup /bin/sh /scripts/backup.sh once
# restore TEST: into a separate database jobs_restore_test (live data untouched)
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backup \
    /bin/sh /scripts/restore.sh /backups/db_<time>.dump jobs_restore_test /backups/files_<time>.tar.gz
```

Real restore (disaster recovery): stop `api worker beat`, run `restore.sh <dump> jobs`, unpack
the files archive into the `storage_data` volume, start the services again. Test a restore at
least once a month.

## 5. Monitoring

- **Sentry** (optional): set `SENTRY_DSN` (free plan at sentry.io) — API and worker errors are
  sent with tokens, cookies and request bodies removed. Check it with Admin › Analytics ›
  *Send test error*.
- **In the app**: Admin › System (health of every service, scheduler heartbeat), Admin ›
  Analytics (usage, AI cost, recent failed tasks), Admin › Audit log.
- Logs: `docker compose -f docker-compose.prod.yml logs -f api worker beat` (JSON lines).

## 6. Upgrades

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```
`migrate` runs the new database migrations before the API starts. Take a backup first.

## 7. Cut-over from the old n8n / Discord system

- [ ] Each user downloads the old Google Sheets as CSV (*File › Download › CSV*): the job list
      and *LinkedIn Leads*, and imports them in **Jobs › Import** (contacts arrive *pending*,
      leads the old system already emailed are marked).
- [ ] Each user uploads their resume again in **Resumes**.
- [ ] n8n: open the workflow **Job-application-tracker** (and the LinkedIn outreach workflow)
      and switch it **inactive**, then stop the n8n container (`docker stop n8n-latest`).
- [ ] **Rotate the JSearch (RapidAPI) key** that was stored in the old workflow: RapidAPI ›
      Apps › your app › Security › *Rotate*, then put the new key in `.env.prod`.
- [ ] Tell users the web address; the Discord bot is retired.
