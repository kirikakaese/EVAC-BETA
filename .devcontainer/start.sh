#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Runs every time the codespace starts, and by hand to (re)start EVAC: bash .devcontainer/start.sh
# Brings dependencies and the database up to date (after a git pull), restarts EVAC on port 8000 in the
# background (log: /tmp/evac.log) and waits until it answers; if it does not, it shows why.
set -uo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ] || [ ! -f .venv/.deps-stamp ] || [ pyproject.toml -nt .venv/.deps-stamp ]; then
    echo "Installing dependencies (pyproject.toml changed)…"
    make dev >/tmp/evac-deps.log 2>&1 && touch .venv/.deps-stamp || {
        echo "Installing the dependencies failed:"; tail -n 20 /tmp/evac-deps.log; exit 1; }
fi
if ! .venv/bin/python manage.py migrate --noinput >/tmp/evac-migrate.log 2>&1; then
    echo "Migrating the database failed:"; tail -n 20 /tmp/evac-migrate.log; exit 1
fi

pkill -f "manage.py runserver" 2>/dev/null && sleep 1
setsid nohup .venv/bin/python manage.py runserver 0.0.0.0:8000 >/tmp/evac.log 2>&1 < /dev/null &

for _ in $(seq 1 60); do
    if curl -fs -o /dev/null http://127.0.0.1:8000/healthz; then
        echo "EVAC runs on port 8000 (log: /tmp/evac.log). Login: admin@evac.local / evac-demo-admin"
        exit 0
    fi
    sleep 1
done
echo "EVAC did not start within a minute. The end of /tmp/evac.log:"
tail -n 30 /tmp/evac.log
exit 1
