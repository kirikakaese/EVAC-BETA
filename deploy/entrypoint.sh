#!/bin/sh
# EVAC container entrypoint: web | channels | worker | beat | <any command>
set -e

wait_for_db() {
  python - <<'PY'
import os, sys, time
import django
django.setup()
from django.db import connection
for i in range(60):
    try:
        connection.ensure_connection()
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"waiting for database ({exc})", flush=True)
        time.sleep(2)
sys.exit("database not reachable")
PY
}

case "$1" in
  web)
    wait_for_db
    python manage.py migrate --noinput
    if [ "${EVAC_SEED_DEMO:-0}" = "1" ]; then python manage.py evac_seed_demo; fi
    if [ -n "${EVAC_SETUP_TOKEN}" ]; then echo "First-run wizard setup token is set (EVAC_SETUP_TOKEN)."; fi
    # ASGI workers: HTTP, Server-Sent Events and (when no separate channels service is routed) WebSockets
    exec gunicorn evac.asgi:application -k uvicorn_worker.UvicornWorker --bind 0.0.0.0:8000 \
      --workers "${WEB_WORKERS:-3}" --timeout 90 --access-logfile - \
      --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
    ;;
  channels)
    wait_for_db
    # Dedicated realtime service: WebSockets (/ws/) of screens, dashboards and the staff PWA
    exec daphne -b 0.0.0.0 -p 8001 --proxy-headers evac.asgi:application
    ;;
  worker)
    wait_for_db
    exec celery -A evac worker -l "${LOG_LEVEL:-info}" --concurrency "${WORKER_CONCURRENCY:-4}"
    ;;
  mqtt)
    wait_for_db
    # Optional: MQTT subscriber for hardware bridges (extensions/mqtt); idles until the extension is configured
    exec python manage.py evac_mqtt
    ;;
  beat)
    wait_for_db
    exec celery -A evac beat -l "${LOG_LEVEL:-info}" --schedule /tmp/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
