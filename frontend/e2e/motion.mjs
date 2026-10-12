// SPDX-License-Identifier: AGPL-3.0-or-later
// Screen motion (ADR-0051): a paired screen plays a playlist with a fade transition, a title with an entrance
// effect and a slide timer that counts down the slide. A drill evacuation raised in the middle of a transition
// takes the screen over at once: the transition is cut short and nothing in the evacuation layer animates.
// Run with `make e2e` (or E2E_ONLY=motion make e2e): scripts/e2e.sh starts the server with demo data.
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
const TRANSITION_MS = 4500;

// 1. content: two slides of 10 s with a 4.5 s fade, a title that slides up, a slide timer along the bottom.
//    Created before the screen pairs, so its first program already has them. The previous state is restored at the end.
const before = JSON.parse(py(`
import json
from apps.content import services as cs
from apps.core import modules
from apps.events.models import Event
from apps.playlists import services as ps
from apps.playlists.models import Playlist, PlaylistItem
e = Event.objects.get(slug="demo")
state = {"defaults": [str(p) for p in Playlist.objects.filter(event=e, is_default=True).values_list("pk", flat=True)],
         "evac_instance": modules.is_enabled("evacuation"), "evac_event": modules.is_enabled("evacuation", e)}
modules.set_instance("evacuation", True); modules.set_event(e, "evacuation", True); modules.acknowledge(e, "evacuation")
pl = ps.save_playlist(Playlist(event=e, name="Motion loop", transition="fade", transition_ms=${TRANSITION_MS},
                               is_default=True), actor=None)
for n, colour in ((1, "#1d4ed8"), (2, "#9d174d")):
    data = {"format": 1, "width": 1920, "height": 1080, "background": {"color": colour}, "elements": [
        {"id": "title", "type": "text", "frame": {"x": 8, "y": 30, "w": 84, "h": 30},
         "style": {"fontSize": 14, "fontWeight": 800, "textAlign": "center", "color": "#ffffff"},
         "props": {"text": "Motion slide %d" % n}, "animation": {"enter": "slide-up", "duration": 900, "delay": 100}},
        {"id": "timer", "type": "progress", "frame": {"x": 0, "y": 97, "w": 100, "h": 3},
         "style": {"color": "#ffd400", "background": "#000000"}, "props": {"mode": "shrink"}}]}
    lay = cs.create_layout(e, name="Motion %d" % n, key="motion-%d" % n, actor=None, data=data)
    cs.publish_layout(lay, actor=None)
    ps.save_item(PlaylistItem(playlist=pl, layout=lay, duration=10), actor=None)
state["playlist"] = str(pl.pk)
print(json.dumps(state))`).split("\n").pop());

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
const admin = await login("admin@evac.local");

// 2. a screen
const player = await browser.newPage({ viewport: { width: 1280, height: 720 } });
player.on("pageerror", (e) => logs.push(`player pageerror: ${e.message}`));
player.on("response", (r) => { if (r.status() >= 500) logs.push(`player HTTP ${r.status()} ${r.url()}`); });
await player.goto(`${B}/player/`);
await player.waitForSelector(".code");
const code = (await player.textContent(".code")).trim();
await admin.goto(`${B}/e/demo/screens/pair/?code=${code}`);
await admin.fill("#id_name", "Motion screen");
await Promise.all([admin.waitForNavigation(), admin.click("main form button.btn-primary")]);
await player.waitForSelector(".evac-el-progress", { timeout: 15000 });
ok(true, `screen paired (${code}) and plays the motion playlist`);

// 3. the slide timer counts the slide down as one synchronised CSS animation; the title has its entrance effect
const timer = await player.evaluate(() => {
  const bar = document.querySelector("#player .evac-progress-bar");
  return { name: bar.style.animationName, duration: bar.style.animationDuration, delay: bar.style.animationDelay };
});
ok(timer.name === "evac-timer-shrink-x" && timer.duration === "10000ms" && timer.delay.startsWith("-"),
   `the slide timer runs over the slide's 10 s (${JSON.stringify(timer)})`);
const scale = () => player.evaluate(() => new DOMMatrix(getComputedStyle(
  document.querySelector("#player main.view:last-of-type .evac-progress-bar")).transform).a);
let s1 = 0, s2 = 0;
for (let i = 0; i < 3; i++) { // a slide change between the two readings starts the bar again: read again
  s1 = await scale();
  await player.waitForTimeout(1000);
  s2 = await scale();
  if (s2 <= s1) break;
}
ok(s2 < s1 && s1 - s2 > 0.05 && s1 - s2 < 0.15, `the bar shrinks about a tenth per second (${s1.toFixed(3)} → ${s2.toFixed(3)})`);
ok(await player.locator('#player .evac-el[data-id="title"].evac-enter-slide-up').count() > 0,
   "the title has its entrance effect");

// 4. the next slide fades in over the old one; the old one goes when the transition ends
await player.waitForSelector("#player main.view.evac-tr-in.evac-tr-fade", { timeout: 15000 });
ok(await player.locator("#player main.view").count() === 2, "during the transition both slides are on screen");
await player.waitForTimeout(1500);
await player.screenshot({ path: `${OUT}/motion-transition.png` });
await player.waitForSelector("#player main.view.evac-tr-in", { state: "detached", timeout: TRANSITION_MS + 1000 });
ok(await player.locator("#player main.view").count() === 1, "after the transition only the new slide is left");

// 5. a drill evacuation raised in the middle of the next transition takes over at once
await admin.goto(`${B}/e/demo/evacuation/`);
await admin.selectOption("form.evac-change select[name$=state]", "evacuate");
await admin.check("form.evac-change input[name$=drill]");
await admin.fill("form.evac-change input[name$=reason]", "Drill: motion check");
await player.waitForSelector("#player main.view.evac-tr-in", { timeout: 15000 });
// the hold button submits by itself after 1.5 s
const sent = admin.waitForNavigation();
await admin.focus("form.evac-change button[data-hold]");
const held = Date.now();
await admin.keyboard.down("Space");
await admin.waitForTimeout(1300);
const midTransition = await player.locator("#player main.view.evac-tr-in").count() === 1;
await player.waitForSelector('#evac-layer[data-mode="takeover"][data-state="evacuate"]', { timeout: 10000 });
const took = Date.now() - held - 1500;
const shown = await player.evaluate(() => {
  const layer = document.getElementById("evac-layer");
  const inLayer = document.getAnimations().filter((a) => layer.contains(a.effect?.target ?? null));
  return { opacity: getComputedStyle(layer).opacity, animations: inLayer.length,
           entrance: layer.querySelectorAll("[class*='evac-enter-']").length,
           views: document.querySelectorAll("#player main.view").length,
           transitioning: document.querySelectorAll("#player main.view.evac-tr-in").length,
           drill: layer.querySelector(".evac-drill")?.textContent ?? "" };
});
await sent;
await admin.keyboard.up("Space");
ok(midTransition, "the alarm was raised while a slide transition was running");
ok(took < 2000, `the screen took over ${took} ms after the hold completed`);
ok(shown.opacity === "1" && shown.animations === 0 && shown.entrance === 0,
   `the evacuation layer is fully visible and does not animate (${JSON.stringify(shown)})`);
ok(shown.views === 1 && shown.transitioning === 0, "the running transition was cut short, not waited for");
ok(shown.drill.trim().length > 0, "the drill is marked");
await player.screenshot({ path: `${OUT}/motion-evacuation.png` });

// 6. all clear and back to normal, then restore the demo data
await admin.goto(`${B}/e/demo/evacuation/`);
await admin.selectOption("form.evac-change select[name$=state]", "all_clear");
const cleared = admin.waitForNavigation();
await admin.focus("form.evac-change button[data-hold]");
await admin.keyboard.down("Space");
await cleared;
await admin.keyboard.up("Space");
await player.waitForSelector('#evac-layer[data-state="all_clear"]', { timeout: 10000 });
await admin.goto(`${B}/e/demo/evacuation/`);
await Promise.all([admin.waitForNavigation(), admin.click('form[action$="end-all-clear/"] button')]);
await player.waitForSelector("#evac-layer[hidden]", { state: "attached", timeout: 10000 });
ok(await player.isVisible(".evac-el-progress"), "after the all clear the playlist plays again");

await browser.close();
py(`
from apps.content.models import Layout
from apps.core import modules
from apps.events.models import Event
from apps.playlists.models import Playlist
from apps.screens.models import Screen
e = Event.objects.get(slug="demo")
Screen.objects.filter(event=e, name="Motion screen").delete()
Playlist.objects.filter(pk="${before.playlist}").delete()
Layout.objects.filter(event=e, key__in=["motion-1", "motion-2"]).delete()
Playlist.objects.filter(pk__in=${JSON.stringify(before.defaults)}).update(is_default=True)
modules.set_event(e, "evacuation", ${before.evac_event ? "True" : "False"})
modules.set_instance("evacuation", ${before.evac_instance ? "True" : "False"})`);
const unexpected = logs.filter((l) => !l.includes("ERR_CONNECTION_REFUSED"));
ok(unexpected.length === 0, `no unexpected page errors${unexpected.length ? `: ${unexpected.join(" | ")}` : ""}`);
