// SPDX-License-Identifier: AGPL-3.0-or-later
// Chaos test (ROADMAP 3.12, brief §8.7, ADR-0003/0034). A screen in alarm must stay in alarm when the server dies,
// take signed state from a fallback origin, refuse forged, stale and bridge-issued clears, survive a reload without
// the server, and follow the server again when it is back.
// Run with `make chaos` (scripts/chaos.sh starts the server with demo data and sets the E2E_* variables).
import { execSync, spawn } from "node:child_process";
import { mkdirSync } from "node:fs";

import { chromium } from "playwright-core";

const OUT = process.env.E2E_OUT || "e2e-output";
const ROOT = process.env.E2E_ROOT || "..";
const PY = process.env.E2E_PYTHON || ".venv/bin/python";
const B = process.env.E2E_BASE || "http://localhost:8000";
const PORT = new URL(B).port || "8000";
const FB_PORT = String(Number(PORT) + 1);
const FB = `http://127.0.0.1:${FB_PORT}`;
const exe = process.env.E2E_CHROMIUM;
mkdirSync(OUT, { recursive: true });
const py = (code) => execSync(`${PY} manage.py shell -c '${code}'`, { cwd: ROOT }).toString().split("\n")
  .filter((l) => !l.includes("DEBUG") && !l.includes("objects imported")).join("\n").trim();
const ok = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"} ${msg}`); if (!cond) process.exitCode = 1; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const children = [];
const cleanup = () => children.forEach((c) => { try { c.kill(); } catch { /* gone */ } });
process.on("exit", cleanup);

let serverPid = Number(process.env.E2E_SERVER_PID || 0);
function killServer() {
  if (serverPid) { try { process.kill(serverPid); } catch { /* gone */ } }
  serverPid = 0;
}
async function startServer() {
  const s = spawn(PY, ["manage.py", "runserver", `127.0.0.1:${PORT}`, "--noreload"], { cwd: ROOT, stdio: "ignore" });
  children.push(s);
  serverPid = s.pid;
  for (let i = 0; i < 120; i++) {
    try { if ((await fetch(`${B}/healthz`)).ok) return; } catch { /* starting */ }
    await sleep(500);
  }
  throw new Error("server did not come back");
}
const control = async (what) => (await fetch(`${FB}/control/${what}`, { method: "POST" })).json();

// setup: accepted statement, staged model, the fallback origin, an admin with a two-factor session
const key = py(`
from apps.core import modules, settings_store
from apps.events.models import Event
from apps.accounts.models import User
from apps.evacuation import alarmkey
e=Event.objects.get(slug="demo")
admin=User.objects.get(email="admin@evac.local")
modules.set_instance("evacuation", True); modules.set_event(e, "evacuation", True)
modules.acknowledge(e, "evacuation", user=admin)
settings_store.save("evacuation", "event", str(e.pk), {"model": "staged", "fallback_origins": ["${FB}"]}, event=e)
print(alarmkey.export_private(e, purpose="chaos test"))`).split("\n").pop();
const fb = spawn(PY, ["scripts/chaos_fallback.py", "--port", FB_PORT, "--central", `http://127.0.0.1:${PORT}`,
                      "--event", "demo", "--key", key], { cwd: ROOT, stdio: "ignore" });
children.push(fb);

const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
const admin = await ctx.newPage();
admin.on("dialog", (d) => void d.accept());
await admin.goto(`${B}/accounts/login/`);
await admin.fill("input[name=username], input[name=email]", "admin@evac.local");
await admin.fill("input[name=password]", "evac-demo-admin");
await Promise.all([admin.waitForNavigation(), admin.click("main form button")]);
const sk = (await ctx.cookies()).find((c) => c.name === "sessionid").value;
py(`
from django.contrib.sessions.backends.db import SessionStore
from apps.accounts.twofactor import SESSION_KEY
s=SessionStore(session_key="${sk}"); s[SESSION_KEY]="2026-01-01T00:00:00"; s.save()`);

async function setState(state) {
  await admin.goto(`${B}/e/demo/evacuation/`);
  await admin.selectOption("form.evac-change select[name$=state]", state);
  await admin.focus("form.evac-change button[data-hold]");
  await Promise.all([admin.waitForNavigation(), (async () => {
    await admin.keyboard.down("Space"); await sleep(1800); await admin.keyboard.up("Space");
  })()]);
}

// a screen
const player = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const consoleLines = [];
player.on("console", (m) => consoleLines.push(`${m.type()}: ${m.text()}`.slice(0, 200)));
await player.goto(`${B}/player/`);
await player.waitForSelector(".code");
const code = (await player.textContent(".code")).trim();
await admin.goto(`${B}/e/demo/screens/pair/?code=${code}`);
await admin.fill("#id_name", "Chaos screen");
await Promise.all([admin.waitForNavigation(), admin.click("main form button.btn-primary")]);
await player.waitForSelector(".evac-stage", { timeout: 15000 });
await sleep(2000); // evacuation bundle (keys, fallback origins) and the service worker cache
const layer = async () => player.evaluate(() => {
  const l = document.getElementById("evac-layer");
  return { mode: l?.dataset.mode ?? "", state: l?.dataset.state ?? "", hidden: !!l?.hidden };
});
const waitFor = async (pred, ms = 15000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { const s = await layer(); if (pred(s)) return s; await sleep(250); }
  return layer();
};

// 1. an alarm from the control room
await setState("attention");
let s = await waitFor((x) => x.state === "attention");
ok(s.state === "attention" && s.mode === "banner", "attention shows as a banner");
await sleep(1500); // the fallback origin relays it

// 2. kill web and channels (one process here): the screen stays in alarm
killServer();
await sleep(4000);
s = await layer();
ok(s.state === "attention", "server killed: the screen stays in alarm");

// 3. the fallback origin signs an evacuation itself (a bridge input fired while EVAC is down)
await control("issue");
s = await waitFor((x) => x.state === "evacuate");
ok(s.state === "evacuate" && s.mode === "takeover", "bridge-signed evacuation from the fallback origin takes over");
if (s.state !== "evacuate") {
  console.log("debug: fallback serves", JSON.stringify(await (await fetch(`${FB}/evac/demo/state`)).json()).slice(0, 400));
  console.log("debug: player bundle", await player.evaluate(() => {
    const b = JSON.parse(localStorage.getItem("evac.player.evacbundle") || "{}");
    return JSON.stringify({ origins: b.fallback_origins, keys: (b.keys || []).length, event: b.event, zones: b.zones });
  }));
  console.log("debug: console", consoleLines.slice(-15).join(" | "));
}
await player.screenshot({ path: `${OUT}/chaos-fallback-evacuate.png` });

// 4. forged, stale and bridge-issued clears are refused
for (const what of ["forge", "stale-clear", "bridge-clear"]) {
  await control(what);
  await sleep(4000);
  s = await layer();
  ok(s.state === "evacuate", `${what}: refused, the screen stays in evacuate`);
}

// 5. a reload without the server: still in alarm (service worker + stored state)
await player.reload();
await sleep(3000);
s = await layer();
ok(s.state === "evacuate", "offline reload: still in evacuate");

// 6. the server comes back; only a person ends the alarm, and the screen follows
await control("relay");
await startServer();
await sleep(3000);
s = await layer();
ok(s.state === "evacuate", "server back: the screen keeps the newer alarm until someone acts");
await setState("evacuate");
await setState("all_clear");
s = await waitFor((x) => x.state === "all_clear");
ok(s.state === "all_clear", "the all clear from the control room reaches the screen");
await player.screenshot({ path: `${OUT}/chaos-all-clear.png` });

await browser.close();
cleanup();
