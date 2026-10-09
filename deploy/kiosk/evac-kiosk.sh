#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Starts Chromium in kiosk mode on the EVAC player inside cage (a Wayland kiosk compositor).
# Configuration: /etc/evac-kiosk.env (EVAC_URL, EVAC_EXTRA_FLAGS). Run by evac-kiosk.service.
set -eu

[ -r /etc/evac-kiosk.env ] && . /etc/evac-kiosk.env
: "${EVAC_URL:?set EVAC_URL in /etc/evac-kiosk.env}"
PROFILE="${HOME}/.config/evac-chromium"
mkdir -p "$PROFILE"

# Chromium refuses to start after an unclean shutdown with a "restore pages" bubble: mark the last exit clean.
for f in "$PROFILE/Default/Preferences" "$PROFILE/Local State"; do
  [ -f "$f" ] && sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$f"
done

CHROMIUM="$(command -v chromium-browser || command -v chromium)"

# shellcheck disable=SC2086 # EVAC_EXTRA_FLAGS is a list of flags
exec cage -d -- "$CHROMIUM" \
  --kiosk "$EVAC_URL" \
  --user-data-dir="$PROFILE" \
  --ozone-platform=wayland \
  --noerrdialogs --disable-infobars --no-first-run --disable-session-crashed-bubble \
  --disable-features=Translate,TouchpadOverscrollHistoryNavigation --disable-pinch --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  --auto-accept-this-tab-capture \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --ignore-gpu-blocklist --enable-gpu-rasterization \
  --remote-debugging-port=9222 \
  ${EVAC_EXTRA_FLAGS:-}
