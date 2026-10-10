// SPDX-License-Identifier: AGPL-3.0-or-later
// Phase 7 acceptance gate (ROADMAP §11.2/§11.6/§11.7): "shift board on screens; lend/return with QR".
// The shift board widgets go on a screen layout; a crew member scans a shift's QR code with the phone (walk-in:
// signed up and checked in) and the screen's "needed now" list follows within seconds. A radio is lent by scanning
// its QR label, with a drawn signature, and taken back the same way. The public help page takes a lost report that
// the helpdesk matches with a found item. Run with `make e2e` (scripts/e2e.sh: server with demo data).
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

py(`
from apps.core import modules
for k in ("widgets", "crew", "inventory", "helpdesk"):
    modules.instance_enabled(k) or modules.set_instance(k, True)`);
const orga = await login("admin@evac.local");

// 1. the shift board widgets for screens (one click), on a layout with a data element
await orga.goto(`${B}/e/demo/crew/`);
await orga.screenshot({ path: `${OUT}/crew-shift-board.png`, fullPage: true });
await Promise.all([orga.waitForNavigation(), orga.click('button:has-text("Add shift board widgets for screens")')]);
ok((await orga.content()).includes("widgets added"), "shift board widgets created");
await orga.goto(`${B}/e/demo/content/layouts/`);
await orga.fill("#id_new-name", "Crew board");
await Promise.all([orga.waitForNavigation(), orga.click("main form button.btn-primary")]);
await orga.waitForSelector("evac-layout-editor .evac-stage");
const field = async (label, value, kind = "input") => {
  const f = orga.locator(`label.ed-field:has(> span:text-is("${label}")) ${kind}`);
  await f.fill(value);
  await f.dispatchEvent("change");
};
await orga.click('.ed-layers button:has-text("Message")');
await orga.click('.ed-right button:text-is("Delete")');
await orga.click('.ed-add button:text-is("Data widget")');
await orga.locator('label.ed-field:has(> span:text-is("Widget")) select').selectOption({ label: "Crew: needed now" });
for (const [k, v] of [["X", "5"], ["Y", "24"], ["Width", "90"], ["Height", "70"]]) await field(k, v);
await orga.waitForTimeout(600);
await orga.screenshot({ path: `${OUT}/crew-layout-editor.png` });
await orga.click('.ed-toolbar button:text-is("Save")');
await orga.waitForSelector('.ed-status[data-status="saved"]', { timeout: 10000 });
await orga.click('.ed-toolbar button:has-text("Publish")');
await orga.waitForTimeout(800);
const lid = py(`
from apps.content.models import Layout
print(Layout.objects.get(name="Crew board").pk)`);
await orga.goto(`${B}/e/demo/content/layouts/${lid}/`);
if (await orga.$('button:has-text("Make default for screens")')) {
  await Promise.all([orga.waitForNavigation(), orga.click('button:has-text("Make default for screens")')]);
}

// 2. a screen in the crew room shows who is needed now
const player = await browser.newPage({ viewport: { width: 1280, height: 720 } });
player.on("pageerror", (e) => logs.push(`player pageerror: ${e.message}`));
await player.goto(`${B}/player/`);
await player.waitForSelector(".code");
const code = (await player.textContent(".code")).trim();
await orga.goto(`${B}/e/demo/screens/pair/?code=${code}`);
await orga.fill("#id_name", "Crew room screen");
await Promise.all([orga.waitForNavigation(), orga.click("main form button.btn-primary")]);
const need = () => player.evaluate(() => {
  const row = [...document.querySelectorAll(".evac-data-table tr")].find((r) => r.textContent.includes("Wristbands"));
  return row ? row.querySelector(".evac-data-value")?.textContent ?? "" : null;
});
await player.waitForFunction(() => document.querySelector(".evac-data")?.textContent?.includes("Wristbands"), null,
                             { timeout: 20000 }).catch(() => null);
ok((await need()) === "2 needed", `the screen shows "Wristbands: ${await need()}"`);
await player.waitForTimeout(400);
await player.screenshot({ path: `${OUT}/player-crew-needed.png` });

// 3. Chris scans the shift's QR code with the phone: walk-in, signed up and checked in
const token = py(`
from apps.crew.models import Shift
print(Shift.objects.get(event__slug="demo", title="Wristbands").checkin_token)`);
const chris = await login("crew@evac.local", PHONE);
await chris.goto(`${B}/e/demo/crew/scan/${token}/`);
await chris.screenshot({ path: `${OUT}/crew-scan.png`, fullPage: true });
const scanned = Date.now();
await Promise.all([chris.waitForNavigation(), chris.click('button:has-text("Check in")')]);
ok((await chris.content()).includes("Checked in: Wristbands"), "the phone says checked in");
await chris.screenshot({ path: `${OUT}/crew-scan-checked-in.png`, fullPage: true });
await player.waitForFunction(() => {
  const row = [...document.querySelectorAll(".evac-data-table tr")].find((r) => r.textContent.includes("Wristbands"));
  return row?.querySelector(".evac-data-value")?.textContent === "1 needed";
}, null, { timeout: 10000 }).catch(() => null);
const took = Date.now() - scanned;
ok((await need()) === "1 needed", `the screen shows "1 needed" ${took} ms after the scan`);
await player.waitForTimeout(400);
await player.screenshot({ path: `${OUT}/player-crew-after-scan.png` });
const state = py(`
from apps.crew.models import Assignment
a=Assignment.objects.get(shift__title="Wristbands", member__user__email="crew@evac.local"); print(a.status, a.source)`);
ok(state === "checked_in qr", `assignment: ${state}`);
await chris.goto(`${B}/e/demo/staff/`);
await chris.screenshot({ path: `${OUT}/staff-my-shifts.png`, fullPage: true });

// 4. the shift with its people and QR code; the printable sheet; the control room panel
const sid = py(`
from apps.crew.models import Shift
print(Shift.objects.get(event__slug="demo", title="Wristbands").pk)`);
await orga.goto(`${B}/e/demo/crew/shifts/${sid}/`);
ok((await orga.content()).includes("Chris Crew"), "the shift lists Chris as checked in");
await orga.screenshot({ path: `${OUT}/crew-shift.png`, fullPage: true });
await orga.goto(`${B}/e/demo/crew/shifts/${sid}/?print=1`);
await orga.screenshot({ path: `${OUT}/crew-shift-qr-print.png`, fullPage: true });
await orga.goto(`${B}/e/demo/crew/teams/`);
await orga.screenshot({ path: `${OUT}/crew-teams.png`, fullPage: true });
await orga.goto(`${B}/e/demo/ops/control/`);
await orga.waitForTimeout(800);
ok((await orga.textContent("#panel-crewneeded")).includes("Ticket check"), "control room shows crew needed");
await orga.screenshot({ path: `${OUT}/control-room-phase7.png`, fullPage: true });

// 5. lend a radio by scanning its QR label, with a drawn signature; take it back the same way
const tag = py(`
from apps.inventory.models import Item
print(Item.objects.filter(event__slug="demo", name="Radio TH-1", status="available").order_by("asset_tag")[0].asset_tag)`);
await orga.goto(`${B}/e/demo/inventory/`);
await orga.screenshot({ path: `${OUT}/inventory.png`, fullPage: true });
await orga.goto(`${B}/e/demo/inventory/labels/?category=`);
await orga.screenshot({ path: `${OUT}/inventory-labels.png`, fullPage: true });
const desk = await login("admin@evac.local", PHONE);
await desk.goto(`${B}/e/demo/inventory/t/${tag}/`);
ok(desk.url().includes("/inventory/") && (await desk.content()).includes(tag), `the QR label opens ${tag}`);
await desk.fill("#id_lend-borrower", "Chris Crew");
await desk.fill("#id_lend-contact", "DECT 2101");
const pad = await desk.locator("canvas[data-signature]").boundingBox();
await desk.locator("canvas[data-signature]").scrollIntoViewIfNeeded();
const box = await desk.locator("canvas[data-signature]").boundingBox();
await desk.mouse.move(box.x + 20, box.y + box.height * 0.7);
await desk.mouse.down();
for (let i = 1; i <= 24; i++) {
  await desk.mouse.move(box.x + 20 + i * (box.width - 40) / 24, box.y + box.height * (0.5 + 0.3 * Math.sin(i / 2)));
}
await desk.mouse.up();
ok(pad !== null && (await desk.inputValue("[data-signature-value]")).startsWith("data:image/png;base64,"),
   "the signature pad filled the form");
await desk.screenshot({ path: `${OUT}/inventory-lend-signature.png`, fullPage: true });
await Promise.all([desk.waitForNavigation(), desk.click('button.btn-lg:has-text("Lend")')]);
const lent = py(`
from apps.inventory.models import Loan
ln=Loan.objects.get(item__asset_tag="${tag}", item__event__slug="demo", returned_at=None)
print(ln.borrower, bool(ln.signature), ln.item.status)`);
ok(lent === "Chris Crew True lent", `lent with signature: ${lent}`);
await desk.screenshot({ path: `${OUT}/inventory-lent.png`, fullPage: true });
await desk.goto(`${B}/e/demo/inventory/t/${tag}/`);
await desk.selectOption("#id_back-condition", "ok");
await Promise.all([desk.waitForNavigation(), desk.click('button:has-text("Take back")')]);
const back = py(`
from apps.inventory.models import Item
it=Item.objects.get(asset_tag="${tag}", event__slug="demo"); print(it.status, it.loans.filter(returned_at=None).count())`);
ok(back === "available 0", `taken back: ${back}`);
await desk.screenshot({ path: `${OUT}/inventory-returned.png`, fullPage: true });

// 6. helpdesk: a visitor reports a lost bag on the public page; the helpdesk matches and hands it over
const visitor = await browser.newPage({ viewport: PHONE });
visitor.on("pageerror", (e) => logs.push(`visitor pageerror: ${e.message}`));
await visitor.goto(`${B}/public/demo/help/`);
await visitor.screenshot({ path: `${OUT}/help-public.png`, fullPage: true });
await visitor.goto(`${B}/public/demo/help/lost/`);
await visitor.fill("#id_what", "Car keys");
await visitor.selectOption("#id_category", "keys");
await visitor.fill("#id_colour", "red");
await visitor.fill("#id_where", "Beer garden");
await visitor.fill("#id_contact", "0170 555 0142");
await Promise.all([visitor.waitForNavigation(), visitor.click('button:has-text("Send")')]);
ok(visitor.url().includes("/help/status/"), "the visitor gets a status page");
await visitor.screenshot({ path: `${OUT}/help-status.png`, fullPage: true });
const lostPk = py(`
from apps.helpdesk.models import LostFound
print(LostFound.objects.get(event__slug="demo", kind="lost", what="Car keys").pk)`);
await orga.goto(`${B}/e/demo/helpdesk/lost-found/${lostPk}/`);
ok((await orga.content()).includes("Car keys with a red tag"), "the found keys are suggested");
await orga.screenshot({ path: `${OUT}/helpdesk-match.png`, fullPage: true });
await Promise.all([orga.waitForNavigation(), orga.click('button[name=action][value=match]')]);
await visitor.reload();
ok((await visitor.content()).includes("Probably found"), "the visitor's status page says probably found");
await orga.fill("#to", "Visitor (ID checked)");
await Promise.all([orga.waitForNavigation(), orga.click('button[name=action][value=hand_over]')]);
ok((await orga.content()).includes("Handed over"), "handed over");
await orga.goto(`${B}/e/demo/helpdesk/`);
await orga.screenshot({ path: `${OUT}/helpdesk.png`, fullPage: true });

await browser.close();
const unexpected = logs.filter((l) => !l.includes("ERR_CONNECTION_REFUSED") && !l.includes("ERR_INTERNET_DISCONNECTED"));
ok(unexpected.length === 0, `no unexpected page errors${unexpected.length ? `: ${unexpected.join(" | ")}` : ""}`);
