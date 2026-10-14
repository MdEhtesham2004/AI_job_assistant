#!/bin/sh
# Restore a backup (Phase 14). Runs in the `backup` service.
#
#   restore.sh <db_file.dump> [target_db] [files.tar.gz]
#
# target_db defaults to "<POSTGRES_DB>_restore_test": a SEPARATE database, so a restore
# can be tested without touching the live data. Restoring over the live database is a
# deliberate act: pass its name explicitly and stop api/worker/beat first.
# The files archive (optional) is unpacked to /restore/files for inspection.
set -eu

DUMP="${1:?usage: restore.sh <db_file.dump> [target_db] [files.tar.gz]}"
TARGET="${2:-${POSTGRES_DB}_restore_test}"
FILES="${3:-}"
HOST="${POSTGRES_HOST:-postgres}"
export PGPASSWORD="$POSTGRES_PASSWORD"

echo "restoring $DUMP into database $TARGET"
dropdb --if-exists -h "$HOST" -U "$POSTGRES_USER" "$TARGET"
createdb -h "$HOST" -U "$POSTGRES_USER" "$TARGET"
pg_restore --no-owner --exit-on-error -h "$HOST" -U "$POSTGRES_USER" -d "$TARGET" "$DUMP"

# Proof: same tables and row counts as the dump's source.
psql -h "$HOST" -U "$POSTGRES_USER" -d "$TARGET" -At -c \
    "SELECT 'alembic ' || version_num FROM alembic_version;
     SELECT 'users ' || count(*) FROM users;
     SELECT 'jobs ' || count(*) FROM jobs;
     SELECT 'applications ' || count(*) FROM applications;
     SELECT 'emails ' || count(*) FROM emails;"

if [ -n "$FILES" ]; then
    rm -rf /restore/files && mkdir -p /restore/files
    tar -xzf "$FILES" -C /restore/files
    echo "files: $(find /restore/files -type f | wc -l) restored to /restore/files"
fi
echo "restore OK"
