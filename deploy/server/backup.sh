#!/bin/sh
# Nightly backup of EVAC and DIAL: database dumps, media volumes and .env files (which hold the keys).
# Installed by evac-dial-backup.timer; keeps 14 days locally. Copy /var/backups/evac-dial off the server
# (e.g. restic/rsync to another machine) - a backup on the same disk is not a backup.
set -eu
DEST=/var/backups/evac-dial
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p "$DEST"
umask 077

for app in evac dial; do
  dir=/opt/$app
  [ -d "$dir" ] || continue
  cd "$dir"
  docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$DEST/$app-db-$STAMP.dump"
  docker compose exec -T web tar -C /app -czf - media > "$DEST/$app-media-$STAMP.tar.gz" || true
  cp .env "$DEST/$app-env-$STAMP"
done

find "$DEST" -type f -mtime +14 -delete
echo "backup $STAMP done"
