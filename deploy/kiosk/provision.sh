#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Turns a Raspberry Pi (Pi 4/5, Raspberry Pi OS Lite 64-bit, Bookworm or newer) into an EVAC screen.
#
#   sudo sh provision.sh https://evac.example.org/player/ [--hostname foyer-left] [--read-only] [--image]
#
# Installs cage + Chromium, creates the user "kiosk", starts Chromium in kiosk mode on the player at boot,
# restarts it when it hangs (watchdog timer), enables the hardware watchdog, disables screen blanking and
# keeps the system updated. --read-only puts the root file system into an overlay (power cuts cannot corrupt
# it; changes are lost on reboot). --image is for pi-gen: install everything but do not start services.
# Safe to run again (e.g. to change the URL).
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
URL="${1:-}"
HOSTNAME_NEW=""
READ_ONLY=0
IMAGE=0
[ $# -gt 0 ] && shift
while [ $# -gt 0 ]; do
  case "$1" in
    --hostname) HOSTNAME_NEW="$2"; shift 2 ;;
    --read-only) READ_ONLY=1; shift ;;
    --image) IMAGE=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
case "$URL" in
  http://*|https://*) ;;
  *) echo "usage: sudo sh provision.sh https://<your EVAC>/player/ [--hostname NAME] [--read-only]" >&2; exit 2 ;;
esac
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update
CHROMIUM_PKG=chromium-browser
apt-cache show chromium-browser >/dev/null 2>&1 || CHROMIUM_PKG=chromium
apt-get install -y --no-install-recommends cage "$CHROMIUM_PKG" curl unattended-upgrades fonts-dejavu-core \
  ca-certificates

# the kiosk user (no password, no sudo); video/render/input for the GPU and the display
id kiosk >/dev/null 2>&1 || useradd --create-home --shell /usr/sbin/nologin kiosk
usermod -aG video,render,input,audio kiosk

install -d -m 0755 /usr/local/lib/evac-kiosk
install -m 0755 "$HERE/evac-kiosk.sh" "$HERE/evac-kiosk-watchdog.sh" /usr/local/lib/evac-kiosk/
install -m 0644 "$HERE/evac-kiosk.service" "$HERE/evac-kiosk-watchdog.service" "$HERE/evac-kiosk-watchdog.timer" \
  /etc/systemd/system/
umask 022
{
  echo "# written by deploy/kiosk/provision.sh"
  echo "EVAC_URL=$URL"
  grep -s '^EVAC_EXTRA_FLAGS=' /etc/evac-kiosk.env || echo "EVAC_EXTRA_FLAGS="
} > /etc/evac-kiosk.env.new
mv /etc/evac-kiosk.env.new /etc/evac-kiosk.env

# boot to the kiosk instead of a console login
systemctl set-default graphical.target
systemctl disable getty@tty1.service 2>/dev/null || true
systemctl enable evac-kiosk.service evac-kiosk-watchdog.timer

# hardware watchdog: reboot when the whole system hangs
mkdir -p /etc/systemd/system.conf.d
printf '[Manager]\nRuntimeWatchdogSec=15\nRebootWatchdogSec=2min\n' > /etc/systemd/system.conf.d/evac-watchdog.conf

# no console blanking; quiet boot
for cmdline in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  if [ -f "$cmdline" ]; then
    grep -q 'consoleblank=0' "$cmdline" || sed -i 's/$/ consoleblank=0 quiet/' "$cmdline"
    break
  fi
done

dpkg-reconfigure -f noninteractive unattended-upgrades

if [ -n "$HOSTNAME_NEW" ]; then
  echo "$HOSTNAME_NEW" > /etc/hostname
  sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$HOSTNAME_NEW/" /etc/hosts
fi

if [ "$READ_ONLY" -eq 1 ] && command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_overlayfs 0
fi

if [ "$IMAGE" -eq 0 ]; then
  systemctl daemon-reload
  systemctl restart evac-kiosk.service
  systemctl start evac-kiosk-watchdog.timer
  echo "EVAC kiosk running. The screen shows a pairing code; pair it in EVAC under Screens -> Pair a screen."
fi
