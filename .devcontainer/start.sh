#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Runs every time the codespace starts: EVAC on port 8000 in the background (log: /tmp/evac.log).
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python manage.py migrate --noinput >/tmp/evac-migrate.log 2>&1 || true
setsid nohup .venv/bin/python manage.py runserver 0.0.0.0:8000 >/tmp/evac.log 2>&1 < /dev/null &
echo "EVAC starts on port 8000 (log: /tmp/evac.log). Login: admin@evac.local / evac-demo-admin"
