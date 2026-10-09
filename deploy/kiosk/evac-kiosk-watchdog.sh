#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Restarts the kiosk when Chromium is gone or no longer answers on its local DevTools port (a hung browser).
# Run every minute by evac-kiosk-watchdog.timer; three failed checks in a row trigger a restart.
set -u

STATE=/run/evac-kiosk-watchdog.failures
fails=$(cat "$STATE" 2>/dev/null || echo 0)

if systemctl is-active --quiet evac-kiosk.service \
   && curl -fsS --max-time 5 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo 0 > "$STATE"
  exit 0
fi

fails=$((fails + 1))
echo "$fails" > "$STATE"
logger -t evac-kiosk-watchdog "kiosk not responding (${fails}/3)"
if [ "$fails" -ge 3 ]; then
  logger -t evac-kiosk-watchdog "restarting evac-kiosk.service"
  echo 0 > "$STATE"
  systemctl restart evac-kiosk.service
fi
