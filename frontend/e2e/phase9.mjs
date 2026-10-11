// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase 9 acceptance (ROADMAP: "SDK example plugin adds a widget + data source + extension page without core
// changes"; the 1,000-screen half of the gate is scripts/load_screens.py). With the example plugin installed
// (pip install ./examples/evac-weather): a reading entered on the plugin's extension page reaches a paired screen
// through the plugin's widget and data source. Also: the template gallery, and the staff app logging a found item
// offline with the sync badge. Run with `make e2e` (CI installs the example plugin for this job).
import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";

import { chromium } from "playwright-core";

const OUT = process.env.E2E_OUT || "e2e-output";
const ROOT = process.env.E2E_ROOT || "..";
const PY = process.env.E2E_PYTHON || ".venv/bin/python";
const B = process.env.E2E_BASE || "http://localhost:8000";
const exe = process.env.E2E_CHROMIUM;
mkdirSync(OUT, { recursive: true });
const py = (code) => execSync(`${PY} manage.py shell -c '${code}'`, { cwd: ROOT }).toString().split("\n")
  .filter((l) => !l.includes("DEBUG") && !l.includes("objects imported")).join("\n").trim();
const logs = [];
const ok = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"} ${msg}`); if (!cond) process.exitCode = 1; };
const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const PHONE = { width: 412, height: 860 };

async function login(email, viewport = { width: 1500, height: 950 }) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => logs.push(`${email} pageerror: ${e.message}`));
  page.on("dialog", (d) => void d.accept());
  await page.goto(`${B}/accounts/login/`);
  await page.fill("input[name=username], input[name=email]", email);
  await page.fill("input[name=password]", "evac-demo-admin");
  await Promise.all([page.waitForNavigation(), page.click("main form button")]);
  const sk = (await ctx.cookies()).find((c) => c.name === "sessionid").value;
  py(`
from django.contrib.sessions.backends.db import SessionStore
from apps.accounts.twofactor import SESSION_KEY
s=SessionStore(session_key="${sk}"); s[SESSION_KEY]="2026-01-01T00:00:00"; s.save()`);
  return page;
}

const orga = await login("admin@evac.local");
const installed = py(`
from apps.core.registry import registry
print("weather" in registry.ensure_loaded().plugins)`) === "True";

// 1. the example plugin: extension page, reading, widget on a screen
if (!installed) {
  ok(false, "example plugin not installed: pip install ./examples/evac-weather");
} else {
  py(`
from apps.core.registry import registry
from apps.events.models import Event
from apps.extensions import services as ext
e=Event.objects.get(slug="demo")
cfg=ext.get_or_new(registry.get_extension("weather"), e)
ext.save_config(cfg, settings_values={"place": "Meadow"}, secret_values={}, features={"widget": True}, enabled=True)`);
  await orga.goto(`${B}/e/demo/settings/extensions/weather/x/`);
  await orga.fill("#id_temperature_c", "18.5");
  await orga.fill("#id_condition", "Light rain");
  await orga.fill("#id_wind_kmh", "12");
  await Promise.all([orga.waitForNavigation(), orga.click('main form button.btn-primary')]);
  ok((await orga.textContent("main table")).includes("Light rain"), "reading entered on the plugin's extension page");
  await orga.screenshot({ path: `${OUT}/plugin-extension-page.png`, fullPage: true });

  // a layout with the plugin widget, shown on every screen
  py(`
from apps.accounts.models import User
from apps.content import gallery, services as content
from apps.events.models import Event
from apps.playlists import services as playback
from apps.playlists.models import Override
e=Event.objects.get(slug="demo"); admin=User.objects.get(email="admin@evac.local")
data=gallery.info_board()
data["elements"]=[el for el in data["elements"] if el["id"] not in ("info",)]
data["elements"].append({"id": "weather", "type": "plugin", "name": "Weather",
    "frame": {"x": 5, "y": 24, "w": 58, "h": 66}, "style": {"background": "token:surface", "radius": 2},
    "props": {"widget": "weather.current", "settings": {"title": "Weather", "unit": "C", "wind": True}}})
lay=content.create_layout(e, name="Weather board", key="weather-board", actor=admin, data=data)
content.publish_layout(lay, actor=admin)
playback.push_override(Override(event=e, title="Weather board", layout=lay, all_screens=True), actor=admin)`);

  const player = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  player.on("pageerror", (e) => logs.push(`player pageerror: ${e.message}`));
  await player.goto(`${B}/player/`);
  await player.waitForSelector(".code");
  const code = (await player.textContent(".code")).trim();
  await orga.goto(`${B}/e/demo/screens/pair/?code=${code}`);
  await orga.fill("#id_name", "Weather screen");
  await Promise.all([orga.waitForNavigation(), orga.click("main form button.btn-primary")]);
  await player.waitForSelector("evac-x-weather", { timeout: 20000 });
  await player.waitForFunction(() => {
    const el = document.querySelector("evac-x-weather");
    return el?.shadowRoot?.textContent?.includes("Light rain");
  }, null, { timeout: 20000 });
  const shown = await player.evaluate(() => document.querySelector("evac-x-weather").shadowRoot.textContent);
  ok(shown.includes("19°C") && shown.includes("Meadow") && shown.includes("Wind 12 km/h"),
     `the plugin widget shows the reading on the screen: ${shown.replace(/\s+/g, " ")}`);
  await player.waitForTimeout(500);
  await player.screenshot({ path: `${OUT}/player-plugin-widget.png` });

  // the editor offers the widget with its settings form
  const lid = py(`
from apps.content.models import Layout
print(Layout.objects.get(event__slug="demo", key="weather-board").pk)`);
  await orga.goto(`${B}/e/demo/content/layouts/${lid}/edit/`);
  await orga.waitForSelector("evac-layout-editor .ed-host evac-x-weather", { timeout: 15000 });
  await orga.click("evac-layout-editor .ed-host [data-id='weather'], evac-layout-editor .ed-host #weather")
    .catch(() => undefined);
  await orga.screenshot({ path: `${OUT}/editor-plugin-widget.png` });
  ok(true, "the layout editor renders the plugin widget");
}

// 2. template gallery
await orga.goto(`${B}/e/demo/content/templates/`);
await orga.waitForFunction(() => document.querySelectorAll("[data-preview-layout] .evac-el").length > 10, null,
                           { timeout: 15000 });
const cards = await orga.locator(".template-card").count();
ok(cards >= 9, `template gallery shows ${cards} templates rendered in the event's theme`);
await orga.screenshot({ path: `${OUT}/template-gallery.png`, fullPage: true });
const card = orga.locator(".template-card", { hasText: "Wayfinding" });
await card.locator("input[name=name]").fill("Wayfinding foyer");
await Promise.all([orga.waitForNavigation(), card.locator("button").click()]);
ok(orga.url().includes("/edit/"), "\"Use template\" opens the new layout in the editor");
await orga.waitForTimeout(800);
await orga.screenshot({ path: `${OUT}/template-in-editor.png` });

// 3. staff app: a found item logged offline, the sync badge, the scan button
const phone = await login("admin@evac.local", PHONE);
await phone.goto(`${B}/e/demo/staff/`);
await phone.screenshot({ path: `${OUT}/staff-app.png`, fullPage: true });
await phone.context().setOffline(true);
await phone.click(".staff-quick summary");
await phone.fill("#lf-what", "Blue umbrella");
await phone.fill("#lf-where", "Gate 2");
await phone.click('.staff-quick button.btn-primary');
await phone.waitForSelector("[data-sync-global]:not([hidden])", { timeout: 5000 });
const badge = (await phone.textContent("[data-sync-global] [data-sync-count]")).trim();
ok(badge === "1", `offline: the top bar shows ${badge} action waiting`);
await phone.screenshot({ path: `${OUT}/staff-offline-waiting.png`, fullPage: true });
await phone.context().setOffline(false);
await phone.evaluate(() => window.dispatchEvent(new Event("online")));
await phone.waitForSelector("[data-sync-global][hidden]", { state: "attached", timeout: 15000 });
const items = py(`
from apps.helpdesk.models import LostFound
print(LostFound.objects.filter(event__slug="demo", what="Blue umbrella").count())`);
ok(items === "1", "back online: the found item was sent once");

ok(logs.length === 0, `no page errors${logs.length ? ": " + logs.join("; ") : ""}`);
await browser.close();
