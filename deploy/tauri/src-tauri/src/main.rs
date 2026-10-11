// SPDX-License-Identifier: AGPL-3.0-or-later
//! EVAC Player: opens `<server>/player/` of an EVAC server full screen, without browser chrome.
//!
//! The server comes from `--server=https://…`, the `EVAC_SERVER` environment variable or the address saved by the
//! setup page (`server.txt` in the app's config directory). Without one, or with `--setup`, the local setup page
//! asks for it. `--windowed` opens a normal window (testing). Everything else, pairing included, is EVAC's web
//! player: it caches itself and its content for offline use like in any browser.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{fs, path::PathBuf};

use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};

fn config_file(app: &AppHandle) -> Option<PathBuf> {
    app.path().app_config_dir().ok().map(|dir| dir.join("server.txt"))
}

fn arg(name: &str) -> Option<String> {
    let prefix = format!("--{name}=");
    std::env::args().skip(1).find_map(|a| a.strip_prefix(&prefix).map(str::to_owned))
}

fn flag(name: &str) -> bool {
    let wanted = format!("--{name}");
    std::env::args().skip(1).any(|a| a == wanted)
}

fn saved_server(app: &AppHandle) -> Option<String> {
    arg("server")
        .or_else(|| std::env::var("EVAC_SERVER").ok())
        .or_else(|| config_file(app).and_then(|path| fs::read_to_string(path).ok()))
        .map(|s| s.trim().to_owned())
        .filter(|s| !s.is_empty())
}

/// `<server>/player/` for an http(s) server address.
fn player_url(server: &str) -> Result<url::Url, String> {
    let base = url::Url::parse(server.trim()).map_err(|e| format!("Not an address: {e}"))?;
    if base.scheme() != "https" && base.scheme() != "http" {
        return Err("The address must start with https:// (or http:// on a local network).".into());
    }
    base.join("/player/").map_err(|e| e.to_string())
}

/// Called by the setup page: check and save the address, then open the player.
#[tauri::command]
fn set_server(app: AppHandle, server: String) -> Result<(), String> {
    let url = player_url(&server)?;
    if let Some(path) = config_file(&app) {
        if let Some(dir) = path.parent() {
            fs::create_dir_all(dir).map_err(|e| e.to_string())?;
        }
        fs::write(&path, server.trim()).map_err(|e| e.to_string())?;
    }
    if let Some(window) = app.get_webview_window("main") {
        window.navigate(url).map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// The saved address, for the setup page's input.
#[tauri::command]
fn current_server(app: AppHandle) -> String {
    saved_server(&app).unwrap_or_default()
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![set_server, current_server])
        .setup(|app| {
            let handle = app.handle().clone();
            let target = match saved_server(&handle).filter(|_| !flag("setup")).and_then(|s| player_url(&s).ok()) {
                Some(url) => WebviewUrl::External(url),
                None => WebviewUrl::App("index.html".into()),
            };
            let kiosk = !flag("windowed");
            WebviewWindowBuilder::new(app, "main", target)
                .title("EVAC Player")
                .fullscreen(kiosk)
                .decorations(!kiosk)
                .inner_size(1280.0, 720.0)
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("EVAC Player could not start");
}

#[cfg(test)]
mod tests {
    use super::player_url;

    #[test]
    fn player_url_of_a_server() {
        assert_eq!(player_url("https://evac.example.org").unwrap().as_str(), "https://evac.example.org/player/");
        assert_eq!(player_url(" https://evac.example.org/e/x ").unwrap().as_str(),
                   "https://evac.example.org/player/");
        assert!(player_url("file:///etc/passwd").is_err());
        assert!(player_url("evac.example.org").is_err());
    }
}
