// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase 8 acceptance gate (ROADMAP §11.5): "offline check-in syncs; access zone counts feed occupancy".
// Two gate phones scan tickets into the main entrance. Gate B loses the network and keeps scanning from the ticket
// list on the device (valid, cancelled, unknown are decided locally); a ticket that gate A let in meanwhile is
// accepted offline and flagged by the server after the sync. Every accepted entry and exit moves the occupancy of
// "Festival site" exactly once. Badges come from a layout made in the layout editor. Run with `make e2e`.
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

// the entrance admits once per person (no re-entry), so a ticket used at two gates shows up
const zone = py(`
from apps.access.models import AccessZone
z=AccessZone.objects.get(event__slug="demo", name="Main entrance"); z.reentry=False; z.save(); print(z.pk)`);
const site = () => Number(py(`
from apps.crowd.models import Area
print(Area.objects.get(event__slug="demo", name="Festival site").value)`));
const before = site();
ok(before >= 8, `"Festival site" starts at ${before} (demo check-ins)`);

const orga = await login("admin@evac.local");
await orga.goto(`${B}/e/demo/access/`);
await orga.screenshot({ path: `${OUT}/access-attendees.png`, fullPage: true });

// 1. two gate phones load the ticket list
const gateA = await login("security@evac.local", PHONE);
const gateB = await login("security@evac.local", PHONE);
for (const [p, name] of [[gateA, "Gate A"], [gateB, "Gate B"]]) {
  await p.goto(`${B}/e/demo/access/scan/`);
  await p.click('a.btn-primary:has-text("Entry")');
  await p.fill("[data-scanner-device]", name);
  await p.dispatchEvent("[data-scanner-device]", "change");
  await p.waitForFunction(() => /40 tickets/.test(document.querySelector("[data-scanner-list]")?.textContent ?? ""),
                          null, { timeout: 10000 });
}
ok(true, "both gates hold the ticket list (40 tickets)");
await gateA.screenshot({ path: `${OUT}/scanner-ready.png`, fullPage: true });

const scan = async (p, code) => {
  await p.fill("#scan-code", code);
  await p.press("#scan-code", "Enter");
  await p.waitForTimeout(250);
  return ((await p.textContent("[data-scanner-result]")) ?? "").replace(/\s+/g, " ").trim();
};
const state = (p) => p.getAttribute("[data-scanner-result]", "data-state");

// 2. gate A online: one guest in
let r = await scan(gateA, "DEMO-0012");
ok((await state(gateA)) === "ok" && r.includes("Welcome"), `gate A: ${r}`);
await gateA.screenshot({ path: `${OUT}/scanner-ok.png`, fullPage: true });

// 3. gate B offline: decides from its list
await gateB.context().setOffline(true);
await gateB.evaluate(() => window.dispatchEvent(new Event("offline")));
const offlineResults = [];
for (const code of ["DEMO-0010", "DEMO-0011", "DEMO-0036", "FORGED-777"]) {
  offlineResults.push([code, await state(gateB).then(() => scan(gateB, code)), await state(gateB)]);
}
ok(offlineResults[0][2] === "ok" && offlineResults[1][2] === "ok", "offline: valid tickets accepted");
ok(offlineResults[2][2] === "invalid", `offline: cancelled ticket refused (${offlineResults[2][1]})`);
ok(offlineResults[3][2] === "unknown", `offline: unknown code refused (${offlineResults[3][1]})`);
// a ticket gate A lets in while gate B is offline, then shown at gate B too
r = await scan(gateA, "DEMO-0013");
ok((await state(gateA)) === "ok", "gate A lets DEMO-0013 in");
r = await scan(gateB, "DEMO-0013");
ok((await state(gateB)) === "ok", "offline gate B cannot know it and accepts DEMO-0013 for now");
const waiting = (await gateB.textContent("[data-scanner-sync]")).trim();
ok(/5 scans waiting|Offline/.test(waiting), `gate B keeps its scans: "${waiting}"`);
await gateB.screenshot({ path: `${OUT}/scanner-offline.png`, fullPage: true });
ok(site() === before + 2, `while gate B is offline the site counts gate A only (${site()})`);

// 4. back online: the queue syncs, the server's answers win
await gateB.context().setOffline(false);
await gateB.evaluate(() => window.dispatchEvent(new Event("online")));
await gateB.waitForFunction(() => document.querySelector("[data-scanner-sync]")?.dataset.state === "synced", null,
                            { timeout: 10000 });
await gateB.waitForTimeout(300);
const rows = py(`
from apps.access.models import Scan
for s in Scan.objects.filter(device="Gate B").order_by("at"):
    print(s.attendee.code if s.attendee else "?" + s.code_hint, s.result, s.offline)`).split("\n");
ok(rows.length === 5 && rows.every((l) => l.endsWith("True")), `gate B's 5 offline scans arrived: ${rows.join(" | ")}`);
ok(rows.some((l) => l.startsWith("DEMO-0013 duplicate")), "the server flags DEMO-0013 as already inside");
const conflict = await gateB.textContent("[data-scanner-log]");
ok(conflict.includes("Server:") && conflict.includes("Already inside"), "gate B's log shows the server's answer");
await gateB.screenshot({ path: `${OUT}/scanner-synced.png`, fullPage: true });
const after = site();
ok(after === before + 4, `"Festival site" counted each guest once: ${before} → ${after} (+4: 0010, 0011, 0012, 0013)`);

// 5. leaving counts down
await gateA.goto(`${B}/e/demo/access/scan/${zone}/?dir=out`);
await gateA.waitForFunction(() => /40 tickets/.test(document.querySelector("[data-scanner-list]")?.textContent ?? ""),
                            null, { timeout: 10000 });
r = await scan(gateA, "DEMO-0010");
await gateA.waitForFunction(() => document.querySelector("[data-scanner-sync]")?.dataset.state === "synced", null,
                            { timeout: 10000 });
ok(r.includes("Goodbye") && site() === after - 1, `exit scan: "${r}", site ${site()}`);
await gateA.screenshot({ path: `${OUT}/scanner-exit.png`, fullPage: true });

// 6. the control room and occupancy see it
await orga.goto(`${B}/e/demo/crowd/`);
await orga.screenshot({ path: `${OUT}/occupancy-site.png`, fullPage: true });
await orga.goto(`${B}/e/demo/ops/control/`);
await orga.waitForTimeout(800);
ok((await orga.textContent("#panel-accesscheckin")).includes("checked in"), "control room shows check-in");
await orga.screenshot({ path: `${OUT}/control-room-phase8.png`, fullPage: true });
await orga.goto(`${B}/e/demo/access/`);
await orga.screenshot({ path: `${OUT}/access-after.png`, fullPage: true });

// 7. badges: a layout made in the layout editor, filled per attendee
const crew = py(`
from apps.access.models import TicketType
print(TicketType.objects.get(event__slug="demo", name="Crew").pk)`);
await orga.goto(`${B}/e/demo/access/types/${crew}/`);
await Promise.all([orga.waitForNavigation(), orga.click('button:has-text("Create a badge layout")')]);
await orga.waitForSelector("evac-layout-editor .evac-stage");
await orga.waitForTimeout(500);
ok((await orga.textContent("evac-layout-editor .evac-stage")).includes("Ada Lovelace"), "badge layout opens in the editor");
await orga.screenshot({ path: `${OUT}/badge-layout-editor.png` });
await orga.goto(`${B}/e/demo/access/badges/?type=${crew}`);
await orga.waitForFunction(() => document.querySelectorAll("[data-preview-pages] .evac-print-page svg").length >= 5,
                           null, { timeout: 10000 }).catch(() => null);
const pages = await orga.evaluate(() => [...document.querySelectorAll("[data-preview-pages] .evac-print-page")]
  .map((p) => p.textContent));
ok(pages.length === 5 && pages.every((t) => t.includes("CREW")) && !pages.some((t) => t.includes("Ada Lovelace")),
   `5 crew badges (one crew ticket is cancelled) rendered from the layout, each with its own name (${pages.length})`);
await orga.screenshot({ path: `${OUT}/badges-layout.png`, fullPage: true });
const day = py(`
from apps.access.models import TicketType
print(TicketType.objects.get(event__slug="demo", name="Day ticket").pk)`);
await orga.goto(`${B}/e/demo/access/badges/?type=${day}`);
await orga.screenshot({ path: `${OUT}/badges-builtin.png`, fullPage: true });

await browser.close();
const unexpected = logs.filter((l) => !l.includes("ERR_CONNECTION_REFUSED") && !l.includes("ERR_INTERNET_DISCONNECTED"));
ok(unexpected.length === 0, `no unexpected page errors${unexpected.length ? `: ${unexpected.join(" | ")}` : ""}`);
