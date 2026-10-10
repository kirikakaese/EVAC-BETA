// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase 1 acceptance gate (brief §17): pair a screen, design a slide with an uploaded font, publish, override,
// unplug the network: the screen keeps playing. Plus: a code element that tries to break out of its sandbox.
// Run with `make e2e`: scripts/e2e.sh starts a throw-away server (demo data) and sets the E2E_* variables.
import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";

import { chromium } from "playwright-core";

const OUT = process.env.E2E_OUT || "e2e-output";
const ROOT = process.env.E2E_ROOT || "..";
const PY = process.env.E2E_PYTHON || ".venv/bin/python";
const B = process.env.E2E_BASE || "http://localhost:8000";
const FONT = process.env.E2E_FONT || "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf";
const exe = process.env.E2E_CHROMIUM;
mkdirSync(OUT, { recursive: true });
const py = (code) => execSync(`${PY} manage.py shell -c '${code}'`, { cwd: ROOT }).toString().split("\n")
  .filter((l) => !l.includes("DEBUG") && !l.includes("objects imported")).join("\n").trim();
const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const logs = [];
const ok = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"} ${msg}`); if (!cond) process.exitCode = 1; };

// staff logs in (demo admin, two-factor verified session)
const staff = await browser.newPage({ viewport: { width: 1500, height: 950 } });
staff.on("pageerror", (e) => logs.push(`staff pageerror: ${e.message}`));
await staff.goto(`${B}/accounts/login/`);
await staff.fill("input[name=username], input[name=email]", "admin@evac.local");
await staff.fill("input[name=password]", "evac-demo-admin");
await Promise.all([staff.waitForNavigation(), staff.click("main form button")]);
const sk = (await staff.context().cookies()).find((c) => c.name === "sessionid").value;
py(`
from django.contrib.sessions.backends.db import SessionStore
from apps.accounts.twofactor import SESSION_KEY
s=SessionStore(session_key="${sk}"); s[SESSION_KEY]="2026-01-01T00:00:00"; s.save()`);

// 1. pair a screen
const player = await browser.newPage({ viewport: { width: 1280, height: 720 } });
player.on("pageerror", (e) => logs.push(`player pageerror: ${e.message}`));
player.on("response", (r) => { if (r.status() >= 500) logs.push(`player HTTP ${r.status()} ${r.request().method()} ${r.url()}`); });
player.on("console", (m) => { if (m.type() === "error" && !m.text().includes("Content Security Policy")) logs.push(`player console: ${m.text()}`); });
await player.goto(`${B}/player/`);
await player.waitForSelector(".code");
const code = (await player.textContent(".code")).trim();
await staff.goto(`${B}/e/demo/screens/pair/?code=${code}`);
await staff.fill("#id_name", "Main entrance");
await Promise.all([staff.waitForNavigation(), staff.click("main form button.btn-primary")]);
await player.waitForSelector(".evac-stage", { timeout: 15000 });
ok(true, `screen paired with code ${code} and shows content`);

// 2. upload a font
await staff.goto(`${B}/e/demo/content/fonts/`);
await staff.setInputFiles("#id_font-file", FONT);
await staff.fill("#id_font-name", "Festival Serif");
await staff.check("#id_font-subset");
await Promise.all([staff.waitForNavigation(), staff.click('main form button:has-text("Upload")')]);
ok((await staff.content()).includes("Festival Serif"), "font uploaded (Latin subset, WOFF2)");
await staff.screenshot({ path: `${OUT}/fonts.png`, fullPage: true });

// 3. design a slide in the editor: title in the uploaded font, plus a code element
await staff.goto(`${B}/e/demo/content/layouts/`);
await staff.fill("#id_new-name", "Opening night");
await Promise.all([staff.waitForNavigation(), staff.click("main form button.btn-primary")]);
await staff.waitForSelector("evac-layout-editor .evac-stage");
await staff.click('.ed-box[data-id="title"]');
const fontSelect = staff.locator('label.ed-field:has(> span:text-is("Font")) select');
await fontSelect.selectOption({ label: "Festival Serif" });
await staff.click('.ed-add button:text-is("Code")');
const codeArea = (label) => staff.locator(`label.ed-field:has(> span:text-is("${label}")) textarea`);
await codeArea("HTML").fill('<div class="card"><h2 id="ev">…</h2><p id="sec">checking…</p></div>');
await codeArea("HTML").dispatchEvent("change");
await codeArea("CSS").fill(".card{height:100%;display:grid;place-content:center;text-align:center;background:linear-gradient(135deg,#2b1055,#7597de);border-radius:3vh;color:#fff}h2{margin:0;font-size:9vh}p{font-size:4vh;opacity:.85}");
await codeArea("CSS").dispatchEvent("change");
await codeArea("JavaScript").fill([
  "const out = [];",
  "try { parent.document.title; out.push('PARENT-ACCESS'); } catch (e) { out.push('parent blocked'); }",
  "try { localStorage.getItem('evac.player.token'); out.push('STORAGE-ACCESS'); } catch (e) { out.push('storage blocked'); }",
  "fetch('/player/api/config/').then(() => out.push('FETCH-OK'), () => out.push('fetch blocked')).finally(() => {",
  "  document.getElementById('sec').textContent = out.join(' · '); evac.log(out.join(' | ')); });",
  "evac.onData((d) => { const ev = document.getElementById('ev');",
  "  const tick = () => { ev.textContent = d.event.name + ' · ' + new Date(evac.now()).toISOString().slice(11, 19) + ' UTC'; };",
  "  tick(); setInterval(tick, 1000); });",
].join("\n"));
await codeArea("JavaScript").dispatchEvent("change");
await staff.locator('label.ed-check:has-text("Event") input').check();
await staff.waitForTimeout(800);
await staff.screenshot({ path: `${OUT}/editor-code.png` });
await staff.click('.ed-toolbar button:text-is("Save")');
await staff.waitForSelector('.ed-status[data-status="saved"]', { timeout: 10000 });
await staff.click('.ed-toolbar button:has-text("Publish")');
await staff.waitForTimeout(800);
const lid = py(`
from apps.content.models import Layout
print(Layout.objects.get(name="Opening night").pk)`);
await staff.goto(`${B}/e/demo/content/layouts/${lid}/`);
await Promise.all([staff.waitForNavigation(), staff.click('button:has-text("Make default for screens")')]);
ok(true, "slide designed, saved, published and made the default");

// 4. the screen shows it: uploaded font + code element with event data, sandbox holds
await player.waitForFunction(() => !!document.querySelector(".evac-stage iframe"), null, { timeout: 15000 });
await player.waitForTimeout(2500);
const fontUsed = await player.evaluate(() => getComputedStyle(document.querySelector('.evac-el[data-id="title"]')).fontFamily);
const loaded = await player.evaluate(() => [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family));
ok(/evac-/.test(fontUsed) && loaded.some((f) => fontUsed.includes(f.replace(/"/g, ""))), `uploaded font in use (${fontUsed.split(",")[0]})`);
const frame = player.mainFrame().childFrames()[0];
const ev = await frame.textContent("#ev");
const sec = await frame.textContent("#sec");
ok(ev.startsWith("Demo"), `code element got event data: "${ev}"`);
ok(sec === "parent blocked · storage blocked · fetch blocked", `sandbox: ${sec}`);
ok(player.url().endsWith("/player/"), "screen still on the player");
await player.screenshot({ path: `${OUT}/player-slide.png` });

// 5. override
await staff.goto(`${B}/e/demo/playlists/overrides/`);
await staff.fill("#id_title", "Doors open");
await staff.fill("#id_message", "The main hall is open. Please have your tickets ready.");
const pushed = Date.now();
await Promise.all([staff.waitForNavigation(), staff.click("#push button.btn-primary")]);
await player.waitForFunction(() => document.querySelector(".evac-stage")?.textContent?.includes("Doors open"), null, { timeout: 10000 });
ok(true, `override on screen after ${Date.now() - pushed} ms`);
await player.screenshot({ path: `${OUT}/player-override.png` });
await staff.goto(`${B}/e/demo/playlists/`);
await Promise.all([staff.waitForNavigation(), staff.click('button:has-text("Cancel")')]);
await player.waitForFunction(() => !!document.querySelector(".evac-stage iframe"), null, { timeout: 10000 });
ok(true, "override cancelled, the slide is back");

// 6. unplug the network (stop the server): the screen keeps playing, also after a restart of the browser tab
const shellCached = await player.evaluate(async () => {
  await navigator.serviceWorker.ready;
  const src = new URL(document.querySelector("script[type=module]").src);
  return !!(await caches.match(src.pathname + src.search));
});
ok(shellCached, "the player app (script) is in the offline cache");
process.kill(Number(process.env.E2E_SERVER_PID), "SIGTERM");
await player.waitForTimeout(6000);
ok(!!(await player.$(".evac-stage iframe")), "server gone: the slide is still on screen");
await player.reload();
try {
  await player.waitForSelector(".evac-stage", { timeout: 15000 });
} catch (err) {
  await player.screenshot({ path: `${OUT}/player-offline-failed.png` });
  console.log("player shows:", (await player.evaluate(() => document.body.innerText)).slice(0, 300));
  console.log("storage:", await player.evaluate(() => Object.keys(localStorage).join(",")));
  console.log("boot stage:", await player.evaluate(() => document.documentElement.dataset.boot ?? "script did not run"));
  throw err;
}
await player.waitForTimeout(3000);
const offlineFont = await player.evaluate(() => [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family).join(","));
const frame2 = player.mainFrame().childFrames()[0];
ok(!!frame2 && (await frame2.textContent("#ev")).startsWith("Demo"), "offline reload: slide and code element render");
ok(/evac-/.test(offlineFont), "offline reload: the uploaded font is loaded from the cache");
await player.screenshot({ path: `${OUT}/player-offline.png` });
const unexpected = logs.filter((l) => !l.includes("ERR_CONNECTION_REFUSED"));
ok(unexpected.length === 0, `no unexpected page errors${unexpected.length ? `: ${unexpected.join(" | ")}` : ""}`);
await browser.close();
