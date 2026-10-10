// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase 6 acceptance gate (ROADMAP §11.3/§11.4): "Room full" appears automatically at the threshold.
// Door staff count with the clicker in the staff app (two devices, one of them offline for a while); when the foyer
// reaches its capacity the screen in the foyer shows "full" with the suggested alternative, the control room gets an
// alert and an ops log line; below the release threshold the banner goes away. Incidents reported from the staff
// app (offline too) appear in the control room. Run with `make e2e` (scripts/e2e.sh: server with demo data).
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

const control = await login("control@evac.local");
// door staff: the control room role counts too (crowd.*); two phones
const door1 = await login("control@evac.local", { width: 412, height: 860 });
const door2 = await login("control@evac.local", { width: 412, height: 860 });

// 1. the foyer as an area: capacity 10, full at 100 %, open again below 80 %, send people to Hall B
await control.goto(`${B}/e/demo/crowd/`);
await control.fill("#id_name", "Foyer");
await control.selectOption("#id_room", { label: "Foyer" });
await control.fill("#id_capacity", "10");
await control.fill("#id_release_percent", "80");
await control.selectOption("#id_alternative", { label: "Hall B" });
await control.locator('label:has-text("Control room") input[name=notify_roles]').check();
await Promise.all([control.waitForNavigation(), control.click('main form button:has-text("Add area")')]);
const area = py(`
from apps.crowd.models import Area
print(Area.objects.get(event__slug="demo", name="Foyer").pk)`);
ok(area.length === 36, "area Foyer created (capacity 10, alternative Hall B)");

// 2. a screen in the foyer
const player = await browser.newPage({ viewport: { width: 1280, height: 720 } });
player.on("pageerror", (e) => logs.push(`player pageerror: ${e.message}`));
await player.goto(`${B}/player/`);
await player.waitForSelector(".code");
const code = (await player.textContent(".code")).trim();
await control.goto(`${B}/e/demo/screens/pair/?code=${code}`);
await control.fill("#id_name", "Foyer screen");
await Promise.all([control.waitForNavigation(), control.click("main form button.btn-primary")]);
py(`
from apps.screens.models import Screen
from apps.venues.models import Room
s=Screen.objects.get(name="Foyer screen"); s.room=Room.objects.get(name="Foyer", venue__slug="demo-hall"); s.save()`);
await player.waitForSelector(".evac-stage", { timeout: 15000 });
ok(true, `screen paired in the foyer (${code})`);

// 3. two door counters; door 2 goes offline and keeps counting
for (const [p, door] of [[door1, "Door A"], [door2, "Door B"]]) {
  await p.goto(`${B}/e/demo/crowd/count/${area}/`);
  await p.fill("[data-counter-device]", door);
  await p.dispatchEvent("[data-counter-device]", "change");
}
await door1.screenshot({ path: `${OUT}/crowd-counter.png` });
const click = async (p, n, sel = '[data-count="1"]') => { for (let i = 0; i < n; i++) await p.click(sel); };
await click(door1, 4);
await door2.context().setOffline(true);
await click(door2, 3);
await door2.waitForTimeout(300);
const pendingText = await door2.textContent("[data-counter-sync]");
ok(/3 clicks waiting|Offline/.test(pendingText), `offline door keeps its clicks: "${pendingText.trim()}"`);
await door2.screenshot({ path: `${OUT}/crowd-counter-offline.png` });
await click(door1, 2);  // 6 counted on the server
await door1.waitForTimeout(500);
const foyerBanner = () => player.evaluate(() => !!document.querySelector(".ann-banner")?.textContent?.includes("Foyer"));
ok(!(await foyerBanner()), "no Foyer banner below the limit");

// 4. door 2 comes back: its 3 clicks arrive, plus one more = 10 → full
await door2.context().setOffline(false);
await door2.evaluate(() => window.dispatchEvent(new Event("online")));
await door2.waitForFunction(() => document.querySelector("[data-counter-sync]")?.dataset.state === "synced", null,
                            { timeout: 10000 });
const reached = Date.now();
await click(door1, 1);
await player.waitForFunction(() => document.querySelector(".ann-banner")?.textContent?.includes("Foyer"), null,
                             { timeout: 10000 }).catch(() => null);
const banner = (await player.textContent(".ann-banner").catch(() => "")) || "";
const took = Date.now() - reached;
const value = py(`
from apps.crowd.models import Area
a=Area.objects.get(pk="${area}"); print(a.value, a.state)`);
ok(value === "10 full", `server count from both doors: ${value}`);
ok(banner.includes("Foyer is full") && banner.includes("Hall B"), `screen shows "${banner.trim()}" ${took} ms after the 10th person`);
await player.waitForTimeout(600);
await player.screenshot({ path: `${OUT}/player-room-full.png` });
await door1.waitForFunction(() => document.querySelector("[data-counter-state]")?.textContent?.includes("Full"), null,
                            { timeout: 8000 }).catch(() => null);
ok((await door1.textContent("[data-counter-state]")).includes("Full"), "the counter shows Full");
await door1.screenshot({ path: `${OUT}/crowd-counter-full.png` });

// 5. alerts: notification for the control room, ops log line, dashboard
const notified = py(`
from apps.core.models import Notification
print(Notification.objects.filter(user__email="control@evac.local", title__contains="Foyer is full").count())`);
ok(Number(notified) >= 1, "the control room got an alert");
await control.goto(`${B}/e/demo/ops/log/`);
ok((await control.content()).includes("Occupancy Foyer: full"), "ops log has the line");
await control.goto(`${B}/e/demo/ops/control/`);
await control.waitForTimeout(800);
ok((await control.textContent("#panel-crowdoccupancy")).includes("Foyer"), "control room shows the foyer");
await control.screenshot({ path: `${OUT}/control-room.png`, fullPage: true });

// 6. hysteresis: 9 (90 %) keeps "full", 7 (70 %) opens again
await click(door1, 1, '[data-count="-1"]');
await door1.waitForTimeout(1500);
ok(await foyerBanner(), "at 9 of 10 the banner stays (opens again below 80 %)");
await click(door1, 2, '[data-count="-1"]');
await player.waitForFunction(() => !document.querySelector(".ann-banner")?.textContent?.includes("Foyer"), null,
                             { timeout: 10000 }).catch(() => null);
ok(!(await foyerBanner()), "at 7 of 10 the Foyer banner is gone");

// 7. an incident reported from the staff app while offline
const crew = await login("security@evac.local", { width: 412, height: 860 });
await crew.goto(`${B}/e/demo/staff/`);
await crew.context().setOffline(true);
await crew.click('summary:has-text("Report an incident")');
await crew.fill("#sr-title", "Smoke smell in the foyer");
await crew.fill("#sr-where", "Foyer, cloakroom");
await crew.selectOption("#sr-sev", "high");
await crew.click('form[action$="/ops/staff/report/"] button');
await crew.waitForTimeout(300);
await crew.screenshot({ path: `${OUT}/staff-incident-offline.png`, fullPage: true });
await crew.context().setOffline(false);
await crew.evaluate(() => window.dispatchEvent(new Event("online")));
await crew.waitForTimeout(2500);
const incidents = py(`
from apps.ops.models import Incident
print(Incident.objects.filter(event__slug="demo", title="Smoke smell in the foyer").count())`);
ok(incidents === "1", `the offline report arrived once (${incidents})`);
await control.goto(`${B}/e/demo/ops/control/`);
await control.waitForTimeout(500);
ok((await control.textContent("#panel-opsincidents")).includes("Smoke smell"), "control room lists the new incident");
await control.screenshot({ path: `${OUT}/control-room-incident.png`, fullPage: true });
const pk = py(`
from apps.ops.models import Incident
print(Incident.objects.get(event__slug="demo", title="Smoke smell in the foyer").pk)`);
await control.goto(`${B}/e/demo/ops/${pk}/`);
await Promise.all([control.waitForNavigation(), control.click('button[name=status][value=acknowledged]')]);
ok((await control.content()).includes("Acknowledged"), "incident acknowledged from its page");
await control.screenshot({ path: `${OUT}/incident.png`, fullPage: true });
await control.goto(`${B}/e/demo/crowd/${area}/`);
await control.screenshot({ path: `${OUT}/crowd-area.png`, fullPage: true });
await control.goto(`${B}/e/demo/ops/`);
await control.screenshot({ path: `${OUT}/incidents.png`, fullPage: true });

await browser.close();
const unexpected = logs.filter((l) => !l.includes("ERR_CONNECTION_REFUSED") && !l.includes("ERR_INTERNET_DISCONNECTED"));
ok(unexpected.length === 0, `no unexpected page errors${unexpected.length ? `: ${unexpected.join(" | ")}` : ""}`);
