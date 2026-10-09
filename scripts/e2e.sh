#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Browser end-to-end tests (frontend/e2e/*.mjs) against a throw-away EVAC with demo data.
#   make e2e                       (needs `npm ci` in frontend/ and a Chromium; no browser is downloaded)
#   E2E_CHROMIUM=/path/to/chrome make e2e
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
PORT="${E2E_PORT:-8765}"
export DATABASE_URL="sqlite:///$WORK/e2e.sqlite3" REDIS_URL="" DEBUG=1 MEDIA_ROOT="$WORK/media" EVAC_PUBLIC_URL=""
export E2E_ROOT="$ROOT" E2E_PYTHON="${E2E_PYTHON:-$ROOT/.venv/bin/python}" E2E_BASE="http://localhost:$PORT"
export E2E_OUT="${E2E_OUT:-$ROOT/e2e-output}"
mkdir -p "$E2E_OUT" && rm -f "$E2E_OUT"/*.png
if [ -z "${E2E_CHROMIUM:-}" ]; then
  for c in /opt/pw-browsers/chromium/chrome-linux/chrome /opt/pw-browsers/chromium-*/chrome-linux/chrome \
           "$(command -v chromium || true)" "$(command -v chromium-browser || true)" "$(command -v google-chrome || true)"; do
    if [ -n "$c" ] && [ -x "$c" ]; then E2E_CHROMIUM="$c"; break; fi
  done
fi
export E2E_CHROMIUM="${E2E_CHROMIUM:-}"

cd "$ROOT"
"$E2E_PYTHON" manage.py migrate -v0
"$E2E_PYTHON" manage.py evac_seed_demo >/dev/null
start_server() {
  "$E2E_PYTHON" manage.py runserver "127.0.0.1:$PORT" --noreload >>"$WORK/server.log" 2>&1 &
  E2E_SERVER_PID=$!
  export E2E_SERVER_PID
  i=0
  until curl -fs -o /dev/null "http://127.0.0.1:$PORT/healthz"; do
    i=$((i + 1)); [ "$i" -gt 60 ] && { cat "$WORK/server.log"; exit 1; }; sleep 1
  done
}
E2E_SERVER_PID=""
trap 'kill "$E2E_SERVER_PID" 2>/dev/null || true; rm -rf "$WORK"' EXIT
status=0
for test in frontend/e2e/*.mjs; do
  echo "== $test"
  # every test gets a running server (phase 1 stops it to test offline playback); the database is shared
  curl -fs -o /dev/null "http://127.0.0.1:$PORT/healthz" || start_server
  (cd frontend && node "../$test") || status=1
done
exit $status
