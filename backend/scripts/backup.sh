#!/bin/sh
# Daily backup (Phase 14): database dump + stored files, kept BACKUP_KEEP_DAYS days.
# Runs in the `backup` service of docker-compose.prod.yml (postgres image):
#   /backups/db_<time>.dump      pg_dump custom format (restore with restore.sh)
#   /backups/files_<time>.tar.gz the storage volume (resumes, PDFs)
# One-off:  docker compose -f docker-compose.prod.yml exec backup /scripts/backup.sh once
set -eu

KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
export PGPASSWORD="$POSTGRES_PASSWORD"

backup_once() {
    stamp="$(date -u +%Y-%m-%d_%H%M%S)"
    pg_dump -Fc -h "${POSTGRES_HOST:-postgres}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -f "/backups/db_${stamp}.dump.part"
    mv "/backups/db_${stamp}.dump.part" "/backups/db_${stamp}.dump"
    tar -czf "/backups/files_${stamp}.tar.gz" -C /storage .
    find /backups -maxdepth 1 -type f \( -name 'db_*.dump' -o -name 'files_*.tar.gz' \) \
        -mtime "+${KEEP_DAYS}" -delete
    files="$(tar -tzf "/backups/files_${stamp}.tar.gz" | grep -vc '/$' || true)"
    echo "backup ${stamp}: database $(du -h "/backups/db_${stamp}.dump" | cut -f1)," \
        "${files} stored files"
}

if [ "${1:-loop}" = "once" ]; then
    backup_once
    exit 0
fi

# Wait for the database, then back up every INTERVAL seconds.
until pg_isready -h "${POSTGRES_HOST:-postgres}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do
    sleep 5
done
while true; do
    backup_once || echo "backup FAILED"
    sleep "$INTERVAL"
done
