#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Runs once when the codespace is created: dependencies, a .env for the codespace, database and demo data.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    url="http://localhost:8000"
    host=""
    if [ -n "${CODESPACE_NAME:-}" ]; then
        host="${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
        url="https://${host}"
    fi
    cat > .env <<ENV
# Written by .devcontainer/setup.sh for this codespace (development only, never use these values in production).
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
DEBUG=1
ALLOWED_HOSTS=*
CSRF_TRUSTED_ORIGINS=https://*.app.github.dev,http://localhost:8000
EVAC_PUBLIC_URL=${url}
EVAC_WEBAUTHN_RP_ID=${host}
EVAC_TRUST_PROXY_HEADERS=1
REDIS_URL=
EMAIL_URL=consolemail://
ENV
fi

# ffmpeg converts uploaded videos; without it EVAC keeps them as uploaded
if ! command -v ffmpeg >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y -qq --no-install-recommends ffmpeg || true
fi
make dev
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py evac_seed_demo
