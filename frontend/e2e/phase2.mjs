// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase 2 acceptance gate (ROADMAP): an announcement goes through approval and reaches a screen plus three more
// channels with a delivery report; an emergency announcement takes the screen over and goes away when cancelled.
// Run with `make e2e` (scripts/e2e.sh starts the server with demo data and sets the E2E_* variables).
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
const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const logs = [];
const ok = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"} ${msg}`); if (!cond) process.exitCode = 1; };

async function login(email, { twoFactor = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => logs.push(`${email} pageerror: ${e.message}`));
  page.on("dialog", (d) => void d.accept()); // data-confirm
  await page.goto(`${B}/accounts/login/`);
  await page.fill("input[name=username], input[name=email]", email);
  await page.fill("input[name=password]", "evac-demo-admin");
  await Promise.all([page.waitForNavigation(), page.click("main form button")]);
  if (twoFactor) {
    const sk = (await ctx.cookies()).find((c) => c.name === "sessionid").value;
    py(`
from django.contrib.sessions.backends.db import SessionStore
from apps.accounts.twofactor import SESSION_KEY
s=SessionStore(session_key="${sk}"); s[SESSION_KEY]="2026-01-01T00:00:00"; s.save()`);
  }
  return page;
}

py(`
from apps.core import settings_store
from apps.events.models import Event
e=Event.objects.get(slug="demo")
settings_store.save("announcements", "event", str(e.pk), {"public_feed": True, "feed_title": "Demo Festival news"}, event=e)`);
const admin = await login("admin@evac.local", { twoFactor: true });
const desk = await login("helpdesk@evac.local");

// a screen
const player = await browser.newPage({ viewport: { width: 1280, height: 720 } });
player.on("pageerror", (e) => logs.push(`player pageerror: ${e.message}`));
await player.goto(`${B}/player/`);
await player.waitForSelector(".code");
const code = (await player.textContent(".code")).trim();
await admin.goto(`${B}/e/demo/screens/pair/?code=${code}`);
await admin.fill("#id_name", "Stage left");
await Promise.all([admin.waitForNavigation(), admin.click("main form button.btn-primary")]);
await player.waitForSelector(".evac-stage", { timeout: 15000 });
ok(true, `screen paired (${code})`);

// 1. the helpdesk writes an announcement from a template; it needs approval
await desk.goto(`${B}/e/demo/announcements/`);
await desk.screenshot({ path: `${OUT}/announcements-index-helpdesk.png`, fullPage: true });
await Promise.all([desk.waitForNavigation(), desk.click('.chip-list a:has-text("Doors open soon")')]);
await desk.fill("#id_var_minutes", "10");
await desk.fill("#id_var_place", "The main stage");
await desk.check('input[name=channels][value=webhook]');
await desk.screenshot({ path: `${OUT}/announcement-compose.png`, fullPage: true });
await Promise.all([desk.waitForNavigation(), desk.click('button[name=action][value=send]')]);
ok((await desk.textContent("h1")).includes("Doors open in 10 minutes") && (await desk.content()).includes("Waiting for approval"),
   "helpdesk announcement waits for approval");
const annUrl = desk.url();

// 2. the admin approves; the screen shows the banner, the other channels deliver
await admin.goto(annUrl);
await admin.fill("#id_note", "Thanks, go.");
await admin.screenshot({ path: `${OUT}/announcement-approval.png`, fullPage: true });
const approved = Date.now();
await Promise.all([admin.waitForNavigation(), admin.click('button:has-text("Approve and send")')]);
await player.waitForSelector(".ann-banner", { timeout: 10000 });
const banner = await player.textContent(".ann-banner");
ok(banner.includes("Doors open in 10 min"), `banner on the screen after ${Date.now() - approved} ms: "${banner}"`);
await player.waitForTimeout(700);
await player.screenshot({ path: `${OUT}/player-announcement-banner.png` });
await admin.reload();
const report = await admin.$$eval("table tbody tr", (rows) => rows.map((r) => [...r.cells].map((c) => c.textContent.trim())));
const delivered = report.filter((r) => r[2] === "Delivered").map((r) => r[0]);
ok(["Screens", "Public feed", "Staff notifications", "Webhooks"].every((c) => delivered.includes(c)),
   `delivery report: ${delivered.join(", ")}`);
await admin.screenshot({ path: `${OUT}/announcement-delivery-report.png`, fullPage: true });
await desk.goto(`${B}/notifications/`);
ok((await desk.content()).includes("Your announcement was approved"), "the author was notified");

// 3. an urgent card
await admin.goto(`${B}/e/demo/announcements/new/?level=urgent`);
await admin.fill("#id_title", "Lost child");
await admin.fill("#id_body", "Mia, 6 years, red jacket. Please bring her to the info point at the main entrance.");
await Promise.all([admin.waitForNavigation(), admin.click('button[name=action][value=send]')]);
await player.waitForSelector(".ann-card", { timeout: 10000 });
await player.waitForTimeout(700);
ok((await player.textContent(".ann-card")).includes("Mia, 6 years"), "urgent card on the screen (above the banner)");
await player.screenshot({ path: `${OUT}/player-announcement-card.png` });
await admin.click('button:has-text("Cancel announcement")');
await admin.waitForLoadState();
await player.waitForSelector(".ann-card", { state: "detached", timeout: 10000 });
ok(true, "card gone after cancelling");

// 4. emergency: full screen above everything but evacuation
await admin.goto(`${B}/e/demo/announcements/new/?level=emergency`);
await admin.fill("#id_title", "Severe weather");
await admin.fill("#id_body", "A thunderstorm is approaching. Leave the open-air areas and follow the staff.");
const sent = Date.now();
await Promise.all([admin.waitForNavigation(), admin.click('button[name=action][value=send]')]);
await player.waitForFunction(() => document.querySelector(".evac-stage")?.textContent?.includes("Severe weather"), null,
                             { timeout: 10000 });
ok(true, `emergency takeover on the screen after ${Date.now() - sent} ms`);
ok(!(await player.$(".ann-banner")), "overlays are hidden during the takeover");
await player.waitForTimeout(700);
await player.screenshot({ path: `${OUT}/player-announcement-emergency.png` });
await admin.click('button:has-text("Cancel announcement")');
await admin.waitForLoadState();
await player.waitForFunction(() => !document.querySelector(".evac-stage")?.textContent?.includes("Severe weather"), null,
                             { timeout: 10000 });
await player.waitForSelector(".ann-banner", { timeout: 5000 });
ok(true, "emergency cancelled: content and banner are back");

// 5. overview and the public feed
await admin.goto(`${B}/e/demo/announcements/`);
await admin.screenshot({ path: `${OUT}/announcements-index.png`, fullPage: true });
await admin.goto(`${B}/e/demo/announcements/levels/`);
await admin.screenshot({ path: `${OUT}/announcement-levels.png`, fullPage: true });
const anon = await browser.newPage({ viewport: { width: 1100, height: 800 } });
await anon.goto(`${B}/public/demo/announcements/`);
ok((await anon.content()).includes("Doors open in 10 minutes"), "public feed lists the announcement");
await anon.screenshot({ path: `${OUT}/announcements-public-feed.png`, fullPage: true });
const rss = await (await anon.request.get(`${B}/public/demo/announcements/rss.xml`)).text();
ok(rss.includes("<rss") && rss.includes("Doors open in 10 minutes"), "RSS feed");

const unexpected = logs.filter((l) => !l.includes("ERR_CONNECTION_REFUSED"));
ok(unexpected.length === 0, `no unexpected page errors${unexpected.length ? `: ${unexpected.join(" | ")}` : ""}`);
await browser.close();
