// SPDX-License-Identifier: AGPL-3.0-or-later
// Staff PWA (roadmap 2.8, ADR-0021) on a phone-sized screen: installable (manifest + service worker), an approval
// taken offline is queued and sent when the network is back, an emergency announcement raises the full-screen
// alert. Run with `make e2e` (scripts/e2e.sh starts the server with demo data).
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
const ok = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"} ${msg}`); if (!cond) process.exitCode = 1; };
const logs = [];

// a helpdesk draft waits for approval
const annId = py(`
from apps.accounts.models import User
from apps.announcements import services as s
from apps.announcements.models import Announcement, Level
from apps.events.models import Event
e=Event.objects.get(slug="demo"); s.ensure_defaults(e)
desk=User.objects.get(email="helpdesk@evac.local")
a=Announcement(event=e, level=Level.objects.get(event=e, key="important"), title="Bar closes at 1 am", body="Last orders at 00:45.", channels=["staff", "screens"])
s.save_draft(a, actor=desk); s.submit(a, actor=desk); print(a.pk)`).split("\n").pop();

const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const ctx = await browser.newContext({ viewport: { width: 412, height: 915 }, deviceScaleFactor: 2, isMobile: true,
                                       hasTouch: true });
const page = await ctx.newPage();
page.on("pageerror", (e) => logs.push(`pageerror: ${e.message}`));
page.on("dialog", (d) => void d.accept());
await page.goto(`${B}/accounts/login/`);
await page.fill("input[name=username], input[name=email]", "admin@evac.local");
await page.fill("input[name=password]", "evac-demo-admin");
await Promise.all([page.waitForNavigation(), page.click("main form button")]);
const sk = (await ctx.cookies()).find((c) => c.name === "sessionid").value;
py(`
from django.contrib.sessions.backends.db import SessionStore
from apps.accounts.twofactor import SESSION_KEY
s=SessionStore(session_key="${sk}"); s[SESSION_KEY]="2026-01-01T00:00:00"; s.save()`);

// 1. installable: manifest and service worker
await page.goto(`${B}/e/demo/staff/`);
const manifest = await page.evaluate(async () => (await fetch(document.querySelector("link[rel=manifest]").href)).json());
ok(manifest.display === "standalone" && manifest.icons.length >= 2, "web app manifest (standalone, icons)");
const swScope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope);
ok(swScope === `${B}/`, `service worker active (scope ${swScope})`);
await page.reload();  // now controlled by the worker: the staff page is kept for offline use
await page.waitForSelector("[data-live-status]");
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/staff-page.png`, fullPage: true });

// 2. offline approval is queued and sent later
await ctx.setOffline(true);
await page.click(`form[action$="/announcements/${annId}/approve/"] button`);
await page.waitForFunction(() => document.querySelector("[data-sync]")?.dataset.state === "waiting");
ok((await page.textContent("[data-sync]")).includes("1 action"), "offline: the approval waits in the queue");
await page.screenshot({ path: `${OUT}/staff-offline-queue.png`, fullPage: true });
const status = () => py(`
from apps.announcements.models import Announcement
print(Announcement.objects.get(pk="${annId}").status)`).split("\n").pop();
ok(status() === "pending", "nothing reached the server while offline");
await page.reload().catch(() => undefined);  // offline reload: the worker serves the kept staff page
ok((await page.textContent("h1"))?.includes("Staff"), "offline reload shows the staff page from the cache");
await ctx.setOffline(false);
await page.evaluate(() => window.dispatchEvent(new Event("online")));
await page.waitForFunction(() => document.querySelector("[data-sync]")?.dataset.state === "synced", null,
                           { timeout: 10000 });
ok(status() === "live", "back online: the queued approval was sent and the announcement is live");

// 3. emergency: full-screen alert on the open staff page
await page.goto(`${B}/e/demo/staff/`);
await page.waitForFunction(() => /Live/.test(document.querySelector("[data-live-status]")?.textContent || ""), null,
                           { timeout: 10000 });
// the control room sends it from another tab (through the server, like in real use)
const control = await ctx.newPage();
await control.goto(`${B}/e/demo/announcements/new/?level=emergency`);
await control.fill("#id_title", "Severe weather");
await control.fill("#id_body", "Leave the open-air areas now.");
await Promise.all([control.waitForNavigation(), control.click("button[name=action][value=send]")]);
await control.close();
await page.waitForSelector("[data-alert-overlay]:not([hidden])", { timeout: 10000 });
ok((await page.textContent("[data-alert-title]")) === "Severe weather", "emergency raises the full-screen alert");
await page.screenshot({ path: `${OUT}/staff-alert.png` });
await page.click("[data-alert-ack]");
ok(await page.isHidden("[data-alert-overlay]"), "alert acknowledged");

const unexpected = logs.filter((l) => !l.includes("ERR_INTERNET_DISCONNECTED"));
ok(unexpected.length === 0, `no unexpected page errors${unexpected.length ? `: ${unexpected.join(" | ")}` : ""}`);
await browser.close();
