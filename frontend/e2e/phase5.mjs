// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase 5 acceptance gate (ROADMAP §11.1): an imported schedule shows now/next on screens; a live change reaches
// the screen in under 5 s. A frab schedule.xml is served locally, imported through the frab extension, a layout with
// a program element plays on a screen in Hall A (its stage is picked automatically), then a session is delayed.
// Run with `make e2e` (scripts/e2e.sh starts the server with demo data and sets the E2E_* variables).
import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { createServer } from "node:http";

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

// ------------------------------------------------------------------ the conference tool: a frab schedule.xml
const MIN = 60_000;
const t0 = Math.floor(Date.now() / MIN) * MIN;
const talks = [  // [id, minutes from now, duration, room, title, speaker]
  [1, -20, 45, "Main stage", "Keeping the lights on: venue power", "Ada Byron"],
  [2, 30, 45, "Main stage", "Screens that keep working offline", "Grace Hopper"],
  [3, 80, 30, "Main stage", "Lightning talks", "Several speakers"],
  [4, -10, 60, "Stage B", "Radio, DECT and the control room", "Linus Signal"],
  [5, 55, 45, "Stage B", "Volunteers' stories", "Vic Viewer"],
  [6, 15, 90, "Workshop room", "Soldering for beginners", "Margaret Hamilton"],
];
const hhmm = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const xml = () => `<?xml version="1.0" encoding="utf-8"?>
<schedule><version>e2e</version><conference><acronym>demo</acronym><title>Demo Festival</title>
<time_zone_name>UTC</time_zone_name></conference>
<day index="1" date="${new Date(t0).toISOString().slice(0, 10)}">${[...new Set(talks.map((t) => t[3]))].map((room) => `
<room name="${room}">${talks.filter((t) => t[3] === room).map(([id, from, dur, , title, who]) => `
<event guid="e2e-${id}" id="${id}"><date>${new Date(t0 + from * MIN).toISOString()}</date><duration>${hhmm(dur)}</duration>
<room>${room}</room><title>${title.replace("'", "&apos;")}</title><track>Talks</track><type>lecture</type>
<persons><person id="${id}">${who}</person></persons></event>`).join("")}
</room>`).join("")}
</day></schedule>`;
let fetched = 0;
const frab = createServer((req, res) => {
  fetched++;
  res.writeHead(200, { "Content-Type": "application/xml" });
  res.end(xml());
});
await new Promise((r) => frab.listen(0, "127.0.0.1", r));
const FRAB = `http://127.0.0.1:${frab.address().port}/schedule.xml`;

// an empty program, published on a public page; the stages of the demo stay (the import reuses them by name)
py(`
from apps.core import settings_store
from apps.events.models import Event
from apps.schedule.models import Session
e=Event.objects.get(slug="demo")
Session.objects.filter(event=e).delete()
settings_store.save("program", "event", str(e.pk), {"public_page": True}, event=e)`);

const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
const staff = await ctx.newPage();
staff.on("pageerror", (e) => logs.push(`staff pageerror: ${e.message}`));
staff.on("dialog", (d) => void d.accept());
await staff.goto(`${B}/accounts/login/`);
await staff.fill("input[name=username], input[name=email]", "admin@evac.local");
await staff.fill("input[name=password]", "evac-demo-admin");
await Promise.all([staff.waitForNavigation(), staff.click("main form button")]);
const sk = (await ctx.cookies()).find((c) => c.name === "sessionid").value;
py(`
from django.contrib.sessions.backends.db import SessionStore
from apps.accounts.twofactor import SESSION_KEY
s=SessionStore(session_key="${sk}"); s[SESSION_KEY]="2026-01-01T00:00:00"; s.save()`);

// 1. connect the frab extension, test it, sync
await staff.goto(`${B}/e/demo/settings/extensions/frab/`);
await staff.fill("#id_s-url", FRAB);
await staff.fill("#id_s-interval_minutes", "0");
await staff.check("#id_enabled");
for (const box of await staff.$$('input[type=checkbox][name^="feature__"]')) await box.check();
await Promise.all([staff.waitForNavigation(), staff.click('main form button.btn-primary')]);
await staff.click('button:has-text("Test connection")');
await staff.waitForFunction(() => document.querySelector("#test-result")?.textContent?.includes("sessions"), null,
                            { timeout: 10000 }).catch(() => null);
const tested = (await staff.textContent("#test-result")) ?? "";
ok(tested.includes("6 sessions on 3 stages"), `test connection reads the frab schedule: ${tested.trim()}`);
await staff.screenshot({ path: `${OUT}/program-frab-extension.png`, fullPage: true });
await staff.goto(`${B}/e/demo/schedule/`);
await Promise.all([staff.waitForNavigation(), staff.click('button:has-text("Sync now")')]);
const imported = Number(py(`
from apps.schedule.models import Session
print(Session.objects.filter(event__slug="demo", source__startswith="frab:").count())`));
ok(imported === 6 && fetched >= 2, `program imported (${imported} sessions)`);
ok((await staff.content()).includes("Program sync: 6 new"), "the sync is in the extension log");

// 2. a layout with the program element: now/next (stage automatic) and the live changes
await staff.goto(`${B}/e/demo/content/layouts/`);
await staff.fill("#id_new-name", "Program board");
await Promise.all([staff.waitForNavigation(), staff.click("main form button.btn-primary")]);
await staff.waitForSelector("evac-layout-editor .evac-stage");
const field = async (label, value, kind = "input") => {
  const f = staff.locator(`label.ed-field:has(> span:text-is("${label}")) ${kind}`);
  await f.fill(value);
  await f.dispatchEvent("change");
};
await staff.click('.ed-layers button:has-text("Message")');  // the new layout's welcome text goes
await staff.click('.ed-right button:text-is("Delete")');
await staff.click('.ed-add button:text-is("Program")');
await field("Heading", "On this stage", "textarea");
for (const [k, v] of [["X", "5"], ["Y", "24"], ["Width", "55"], ["Height", "70"]]) await field(k, v);
await staff.click('.ed-add button:text-is("Program")');
await staff.locator('label.ed-field:has(> span:text-is("Show")) select').selectOption("changes");
await field("Heading", "Program changes", "textarea");
for (const [k, v] of [["X", "64"], ["Y", "24"], ["Width", "31"], ["Height", "70"]]) await field(k, v);
await staff.waitForTimeout(600);
ok((await staff.textContent("evac-layout-editor .evac-stage")).includes("Keeping the lights on"),
   "the editor previews the imported sessions");
await staff.screenshot({ path: `${OUT}/program-editor.png` });
await staff.click('.ed-toolbar button:text-is("Save")');
await staff.waitForSelector('.ed-status[data-status="saved"]', { timeout: 10000 });
await staff.click('.ed-toolbar button:has-text("Publish")');
await staff.waitForTimeout(800);
const lid = py(`
from apps.content.models import Layout
print(Layout.objects.get(name="Program board").pk)`);
await staff.goto(`${B}/e/demo/content/layouts/${lid}/`);
if (await staff.$('button:has-text("Make default for screens")')) {  // the first layout of an event already is
  await Promise.all([staff.waitForNavigation(), staff.click('button:has-text("Make default for screens")')]);
}

// 3. a screen in Hall A shows now and next of the Main stage
const player = await browser.newPage({ viewport: { width: 1280, height: 720 } });
player.on("pageerror", (e) => logs.push(`player pageerror: ${e.message}`));
await player.goto(`${B}/player/`);
await player.waitForSelector(".code");
const code = (await player.textContent(".code")).trim();
await staff.goto(`${B}/e/demo/screens/pair/?code=${code}`);
await staff.fill("#id_name", "Hall A door");
await Promise.all([staff.waitForNavigation(), staff.click("main form button.btn-primary")]);
py(`
from apps.screens.models import Screen
from apps.venues.models import Room
s=Screen.objects.get(name="Hall A door"); s.room=Room.objects.get(name="Hall A", venue__slug="demo-hall"); s.save()`);
await player.waitForFunction(() => document.querySelector(".evac-program")?.textContent?.includes("Keeping the lights on"),
                             null, { timeout: 20000 });
await player.reload();  // the screen's room arrives with the schedule data
await player.waitForFunction(() => {
  const t = document.querySelector(".evac-program-now_next")?.textContent ?? "";
  return t.includes("Keeping the lights on") && t.includes("Screens that keep working offline") && !t.includes("DECT");
}, null, { timeout: 20000 });
ok(true, "the screen shows now and next of the Main stage (Hall A)");
await player.waitForTimeout(500);
await player.screenshot({ path: `${OUT}/player-program-now-next.png` });

// 4. live change: delay the next talk by 10 minutes; the screen shows it in < 5 s
await staff.goto(`${B}/e/demo/schedule/`);
await staff.screenshot({ path: `${OUT}/program-index.png`, fullPage: true });
const row = staff.locator('tr:has(th:has-text("Screens that keep working offline"))');
await row.locator("summary").click();
await staff.screenshot({ path: `${OUT}/program-live-change.png`, fullPage: true });
const clicked = Date.now();
await Promise.all([staff.waitForNavigation(), row.locator('button[name=minutes][value="10"]').click()]);
await player.waitForFunction(() => document.querySelector(".evac-program-now_next")?.textContent?.includes("+10 min"),
                             null, { timeout: 5000 }).catch(() => null);
const took = Date.now() - clicked;
const shown = (await player.textContent(".evac-program-now_next")) ?? "";
ok(shown.includes("+10 min") && took < 5000, `the delay reached the screen in ${took} ms`);
await player.waitForFunction(() => document.querySelector(".evac-program-changes")?.textContent?.includes("now starts at"),
                             null, { timeout: 5000 }).catch(() => null);
ok(((await player.textContent(".evac-program-changes")) ?? "").includes("now starts at"), "the change list shows it");
await player.waitForTimeout(400);
await player.screenshot({ path: `${OUT}/player-program-delay.png` });

// 5. a re-sync keeps the local delay; the public program and its exports show it
await staff.goto(`${B}/e/demo/schedule/`);
await Promise.all([staff.waitForNavigation(), staff.click('button:has-text("Sync now")')]);
const kept = py(`
from apps.schedule.models import Session
print(Session.objects.get(event__slug="demo", external_id="e2e-2").delay_minutes)`);
ok(kept === "10", `a re-sync keeps the local delay (${kept} min)`);
const anon = await browser.newPage({ viewport: { width: 1100, height: 800 } });
await anon.goto(`${B}/public/demo/program/`);
const pub = await anon.content();
ok(pub.includes("Screens that keep working offline") && pub.includes("+10 min"), "public program shows the delay");
await anon.screenshot({ path: `${OUT}/program-public.png`, fullPage: true });
const ics = await (await anon.request.get(`${B}/public/demo/program.ics`)).text();
ok(ics.includes("BEGIN:VEVENT") && ics.includes("Screens that keep working offline"), "iCal export");
const frabOut = await (await anon.request.get(`${B}/public/demo/schedule.xml`)).text();
ok(frabOut.includes("<schedule>") && frabOut.includes("Lightning talks"), "frab XML export");

frab.close();
await browser.close();
const unexpected = logs.filter((l) => !l.includes("ERR_CONNECTION_REFUSED"));
ok(unexpected.length === 0, `no unexpected page errors${unexpected.length ? `: ${unexpected.join(" | ")}` : ""}`);
