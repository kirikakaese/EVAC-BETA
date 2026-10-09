# EVAC kiosk for Raspberry Pi

Turns a Raspberry Pi 4 or 5 with an HDMI display into an EVAC screen that starts by itself, recovers by itself
and needs no keyboard. Any other device that runs Chromium in kiosk mode works too; this recipe is the tested
way.

## What you need

- Raspberry Pi 4 (2 GB+) or Raspberry Pi 5, official power supply, a good microSD card (A1/A2) or an SSD
- Raspberry Pi OS **Lite** (64-bit), Bookworm or newer, written with Raspberry Pi Imager (set up a user, SSH
  and, if needed, Wi-Fi in the Imager's settings)
- network access to your EVAC server (wired is best for screens)

## Set up one Pi

```sh
# on your computer: copy the recipe to the Pi
scp -r deploy/kiosk pi@<pi>:/tmp/evac-kiosk
# on the Pi
sudo sh /tmp/evac-kiosk/provision.sh https://evac.example.org/player/ --hostname foyer-left
```

The Pi shows a six-character code. Pair it in EVAC under **Screens → Pair a screen** (or in the setup wizard).
Run the script again at any time to change the URL; options:

| Option | Effect |
|---|---|
| `--hostname NAME` | sets the host name (useful to tell many Pis apart on the network) |
| `--read-only` | root file system in an overlay: power cuts cannot corrupt the card; every change (also updates) is lost on reboot, so use it once a screen is finished |
| `--image` | for image builds (pi-gen): installs and enables, does not start |

## What it does

- installs **cage** (a minimal Wayland kiosk compositor) and **Chromium**; creates the user `kiosk` (no
  password, no sudo) and starts `evac-kiosk.service` on the first display at boot, instead of a login prompt;
- Chromium flags (`evac-kiosk.sh`): kiosk mode, no error dialogs or "restore pages" bubble, video and audio
  autoplay allowed, GPU rasterisation, **`--auto-accept-this-tab-capture`** (lets staff take real
  screenshots under *Screen → Remote management*), DevTools on `127.0.0.1:9222` only (for the watchdog);
- `evac-kiosk-watchdog.timer` checks every minute that Chromium runs and answers; after three failed checks it
  restarts the kiosk. The **hardware watchdog** reboots the Pi if the whole system hangs (15 s);
- disables console blanking and enables unattended security updates.

The player itself adds more: it keeps playing offline, reloads itself at most three times in ten minutes
(no reload loops), reloads daily at the time set in the display settings (default 04:00) and when memory runs
short, and reports unclean restarts in its heartbeat.

## Display settings

Rotation, overscan, scale, keystone, dimming and "screen off" times, audio and the daily reload are set in
EVAC per event, screen group or screen (**Screen → Display settings**), not on the Pi. Prefer the display's own
menu for overscan and rotation if it has the option; EVAC's settings are for displays that cannot.

## Video decoding

Use H.264 (EVAC creates MP4/H.264 for every video). The Chromium of Raspberry Pi OS decodes H.264 in hardware on
the Pi 4 and HEVC on the Pi 5; check `chrome://gpu` (attach a keyboard, or set `EVAC_EXTRA_FLAGS` temporarily)
if videos stutter. Keep videos at 1080p or below on a Pi 4. Extra flags go into `/etc/evac-kiosk.env`
(`EVAC_EXTRA_FLAGS=...`), then `sudo systemctl restart evac-kiosk`.

## Build an image for many screens

With [pi-gen](https://github.com/RPi-Distro/pi-gen) (on a Debian/Ubuntu machine or in its Docker build):

```sh
git clone https://github.com/RPi-Distro/pi-gen && cd pi-gen
cat > config <<CONF
IMG_NAME=evac-kiosk
RELEASE=bookworm
TARGET_HOSTNAME=evac-screen
FIRST_USER_NAME=admin
ENABLE_SSH=1
EVAC_URL=https://evac.example.org/player/
STAGE_LIST="stage0 stage1 stage2 /path/to/EVAC/deploy/kiosk/pi-gen/stage-evac"
CONF
sudo ./build.sh            # or ./build-docker.sh
```

Every Pi flashed with the image boots straight into the pairing code. Set a unique host name per Pi with
`sudo sh /opt/evac-kiosk/provision.sh <url> --hostname <name>` if you need one.

## Troubleshooting

| Symptom | Check |
|---|---|
| black screen after boot | `journalctl -u evac-kiosk -b`; is the URL right (`/etc/evac-kiosk.env`)? |
| "EVAC server not reachable" | network, DNS, firewall, the early-access gate does not block `/player/` |
| restarts every few minutes | `journalctl -t evac-kiosk-watchdog`; the Pi may be too slow for very heavy layouts |
| no sound | display settings → *Play sound*; HDMI audio needs the display's speakers on |
| screenshots fail | only kiosks started with this recipe (or Chromium with `--auto-accept-this-tab-capture`) can take them |
