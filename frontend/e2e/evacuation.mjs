// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase 3 acceptance (ROADMAP 3.12, brief §8.7): the safety statement is accepted, an alarm raised on the control
// page (hold to confirm) takes a screen over within 2 s, the screen confirms it ("1 of 1 screens confirmed"),
// staff answer, the all clear shows and the screen returns to normal content.
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

async function login(email) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
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

async function hold(page, selector) {
  await page.focus(selector);
  await page.keyboard.down("Space");
  await page.waitForTimeout(1800);
  await page.keyboard.up("Space");
}

py(`
from apps.core import modules, settings_store
from apps.events.models import Event
e=Event.objects.get(slug="demo")
modules.set_instance("evacuation", True); modules.set_event(e, "evacuation", True)
settings_store.save("evacuation", "event", str(e.pk), {"model": "staged"}, event=e)`);
const admin = await login("admin@evac.local");

// 1. the safety statement comes first
await admin.goto(`${B}/e/demo/evacuation/`);
ok((await admin.content()).includes("not a certified fire alarm system"), "the evacuation page shows the safety statement first");
await admin.screenshot({ path: `${OUT}/evacuation-statement.png`, fullPage: true });
await admin.check("input[name=accept]");
await Promise.all([admin.waitForNavigation(), admin.click("main form button.btn-primary")]);
ok((await admin.content()).includes("Whole event"), "statement accepted: the control page opens");

// 2. a screen
const player = await browser.newPage({ viewport: { width: 1280, height: 720 } });
player.on("pageerror", (e) => logs.push(`player pageerror: ${e.message}`));
player.on("response", (r) => { if (r.status() >= 500) logs.push(`player HTTP ${r.status()} ${r.url()}`); });
await player.goto(`${B}/player/`);
await player.waitForSelector(".code");
const code = (await player.textContent(".code")).trim();
await admin.goto(`${B}/e/demo/screens/pair/?code=${code}`);
await admin.fill("#id_name", "Foyer");
await Promise.all([admin.waitForNavigation(), admin.click("main form button.btn-primary")]);
await player.waitForSelector(".evac-stage", { timeout: 15000 });
await player.waitForTimeout(1500); // the player fetched its evacuation bundle
ok(true, `screen paired (${code})`);

// 3. evacuate, held to confirm, as a drill
await admin.goto(`${B}/e/demo/evacuation/`);
await admin.selectOption("form.evac-change select[name$=state]", "evacuate");
await admin.check("form.evac-change input[name$=drill]");
await admin.fill("form.evac-change input[name$=reason]", "Drill: smoke in hall A");
const raised = Date.now();
await Promise.all([admin.waitForNavigation(), hold(admin, "form.evac-change button[data-hold]")]);
await player.waitForSelector('#evac-layer[data-mode="takeover"][data-state="evacuate"]', { timeout: 10000 });
const took = Date.now() - raised - 1800;
ok(took < 2000, `the screen took over ${took} ms after the hold completed`);
ok((await player.textContent("#evac-layer .evac-drill")).trim().length > 0, "the drill is marked on the screen");
ok((await player.locator("#evac-layer svg[aria-label^='Emergency exit']").count()) > 0, "ISO 7010 exit sign shown");
await player.screenshot({ path: `${OUT}/evacuation-screen.png` });

// 4. the control page sees the confirmation
let confirmed = false;
for (let i = 0; i < 20 && !confirmed; i++) {
  await admin.goto(`${B}/e/demo/evacuation/propagation/`);
  confirmed = (await admin.content()).includes("1 of 1 screens confirmed");
  if (!confirmed) await admin.waitForTimeout(500);
}
ok(confirmed, "control page: 1 of 1 screens confirmed");
await admin.goto(`${B}/e/demo/evacuation/`);
await admin.screenshot({ path: `${OUT}/evacuation-control.png`, fullPage: true });

// 5. staff answer from the staff app
await admin.goto(`${B}/e/demo/staff/`);
await Promise.all([admin.waitForNavigation(), admin.click('form.evac-answer button[value="on_it"]')]);
await admin.goto(`${B}/e/demo/evacuation/propagation/`);
ok((await admin.content()).includes("on it"), "the staff answer reaches the control page");

// 6. the all clear, then back to normal
await admin.goto(`${B}/e/demo/evacuation/`);
await admin.selectOption("form.evac-change select[name$=state]", "all_clear");
await Promise.all([admin.waitForNavigation(), hold(admin, "form.evac-change button[data-hold]")]);
await player.waitForSelector('#evac-layer[data-state="all_clear"]', { timeout: 10000 });
ok(true, "the all clear shows on the screen");
await player.screenshot({ path: `${OUT}/evacuation-all-clear.png` });
await admin.goto(`${B}/e/demo/evacuation/`);
await Promise.all([admin.waitForNavigation(), admin.click('form[action$="end-all-clear/"] button')]);
await player.waitForSelector("#evac-layer[hidden]", { state: "attached", timeout: 10000 });
ok(await player.isVisible(".evac-stage"), "the screen is back to its normal content");

// 7. readiness and history
await admin.goto(`${B}/e/demo/evacuation/readiness/`);
await admin.screenshot({ path: `${OUT}/evacuation-readiness.png`, fullPage: true });
await admin.goto(`${B}/e/demo/evacuation/history/`);
ok((await admin.content()).includes("smoke in hall A"), "the history lists the drill");

await browser.close();
const unexpected = logs.filter((l) => !l.includes("ERR_CONNECTION_REFUSED"));
ok(unexpected.length === 0, `no unexpected page errors${unexpected.length ? `: ${unexpected.join(" | ")}` : ""}`);
