# EVAC Player (Tauri)

A small native app (Tauri 2, Rust; Linux, Windows, macOS) that opens EVAC's web player full screen without browser
chrome. Use it on mini PCs and media players where a kiosk browser is awkward. Raspberry Pis are better served by
the kiosk recipe (`deploy/kiosk/`), info-beamer devices by `deploy/info-beamer/`.

## Use

```sh
evac-player --server=https://evac.example.org   # or EVAC_SERVER=…, or enter it once on the setup page
evac-player --setup                             # change the saved address
evac-player --windowed                          # a normal window instead of full screen
```

The first start without an address shows a local setup page; the address is saved in the app's config directory
(`server.txt`). The player then pairs like any browser player (the code appears on screen; enter it in EVAC under
*Screens → Pair*), caches itself and its content for offline use and reconnects on its own.

Start it automatically with the system (autostart entry, Windows startup folder, a systemd user unit) and switch off
screen blanking in the operating system: the app does not keep the display awake by itself.

## Build

Prerequisites: Rust ≥ 1.77 and the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) of your
platform (on Debian/Ubuntu: `libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev libayatana-appindicator3-dev`).

```sh
cd deploy/tauri/src-tauri
cargo test                      # unit tests
cargo install tauri-cli --version "^2" --locked
cargo tauri build               # packages in target/release/bundle/ (deb, AppImage, msi, dmg)
```

The setup page (`setup/`) is the only local content and the only page allowed to call the app (saving the
address); EVAC's pages run as a normal remote site without access to the app.
