// SPDX-License-Identifier: AGPL-3.0-or-later
// Check-in app of the access module (ADR-0044): /e/<event>/access/scan/<zone>/[?dir=out].
// The device keeps the zone's ticket list (codes only as SHA-256 prefixes) and decides at once, also offline.
// Every scan is queued with an id and the device's time and sent in batches; the server applies the same rule
// and its answer wins (a ticket let in at another door meanwhile shows up as a conflict in the log). Codes come
// from a hardware scanner or the keyboard (the input field) or, where the browser has BarcodeDetector, the camera.
(function () {
  "use strict";
  const root = document.querySelector("[data-scanner]");
  if (!root) return;
  const zone = root.getAttribute("data-zone");
  const dir = root.getAttribute("data-dir") === "out" ? "out" : "in";
  const LKEY = "evac.scan-list." + zone;
  const SKEY = "evac.scan-state." + zone;
  const QKEY = "evac.scan-queue";
  const DKEY = "evac.scan-device";
  const resultEl = root.querySelector("[data-scanner-result]");
  const form = root.querySelector("[data-scanner-form]");
  const input = root.querySelector("[data-scanner-code]");
  const syncEl = root.querySelector("[data-scanner-sync]");
  const listEl = root.querySelector("[data-scanner-list]");
  const logEl = root.querySelector("[data-scanner-log]");
  const deviceEl = root.querySelector("[data-scanner-device]");
  const camBtn = root.querySelector("[data-scanner-camera]");
  const video = root.querySelector("[data-scanner-video]");
  const GLYPH = { ok: "✓", denied: "✕", invalid: "✕", unknown: "?", duplicate: "!", pending: "…", refused: "✕" };
  let sending = false;
  let lastCode = "";
  let lastAt = 0;

  function label(key, vars) {
    return (root.getAttribute("data-label-" + key) || "").replace(/\{(\w+)\}/g, function (m, n) {
      return vars && Object.prototype.hasOwnProperty.call(vars, n) ? String(vars[n]) : m;
    });
  }
  function load(key, fallback) {
    try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch (e) { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* full or blocked */ }
  }
  function token() {
    try { return JSON.parse(document.body.getAttribute("hx-headers") || "{}")["X-CSRFToken"] || ""; } catch (e) { return ""; }
  }
  function uid() {
    return (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2);
  }
  async function keyOf(code) {
    if (!(window.crypto && crypto.subtle)) return null;
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(code.trim()));
    return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, "0"); }).join("").slice(0, 20);
  }

  let list = load(LKEY, null);
  // what this device changed since the list was fetched: key -> inside (true/false)
  let local = load(SKEY, {});

  function decide(key) {
    if (!list || !key) return null;  // nothing to decide with: the server decides
    const t = list.tickets[key];
    if (!t) return { result: "unknown" };
    const name = t[0], type = t[1], valid = t[2], wasIn = t[3];
    if (!valid) return { result: "invalid", name: name };
    const inside = Object.prototype.hasOwnProperty.call(local, key) ? local[key] : !!wasIn;
    if (dir === "in") {
      if (list.zone.allowed.indexOf(type) < 0) {
        return { result: "denied", name: name, type: (list.types[type] || {}).name || "" };
      }
      if (inside && !list.zone.reentry) return { result: "duplicate", name: name };
    }
    return { result: "ok", name: name, type: (list.types[type] || {}).name || "", colour: (list.types[type] || {}).colour };
  }

  function message(d) {
    if (d.result === "ok") return label(dir === "in" ? "welcome" : "goodbye", { name: d.name });
    if (d.result === "denied") return label("not-granted", { type: d.type || "" });
    if (d.result === "pending") return label("saved-sub");
    return d.name || "";
  }

  function show(d) {
    resultEl.dataset.state = d.result;
    const big = document.createElement("span");
    big.className = "scanner-big";
    big.textContent = (GLYPH[d.result] || "") + " " + (label(d.result === "pending" ? "saved" : d.result) || d.result);
    const sub = document.createElement("span");
    sub.className = "scanner-sub";
    sub.textContent = d.message || message(d);
    resultEl.replaceChildren(big, sub);
    if (navigator.vibrate) navigator.vibrate(d.result === "ok" ? 60 : [120, 80, 120]);
  }

  function addLog(id, d) {
    const li = document.createElement("li");
    li.dataset.id = id;
    li.dataset.state = d.result;
    const t = new Date();
    li.textContent = t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) + "  " +
      (GLYPH[d.result] || "") + " " + (d.name || label(d.result)) ;
    logEl.prepend(li);
    while (logEl.children.length > 30) logEl.lastElementChild.remove();
  }

  function paint() {
    const q = load(QKEY, []);
    const n = q.length;
    syncEl.dataset.state = n ? (navigator.onLine ? "waiting" : "offline") : "synced";
    syncEl.textContent = n ? label(navigator.onLine ? "pending" : "offline", { n: n }) : label("synced");
    if (list) {
      const at = new Date(list.generated);
      listEl.textContent = label("list", { n: list.count, time: at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) });
    } else {
      listEl.textContent = label("nolist");
    }
  }

  async function handle(raw) {
    const code = (raw || "").trim();
    if (!code) return;
    const now = Date.now();
    if (code === lastCode && now - lastAt < 2500) return;  // the camera sees the same code again
    lastCode = code;
    lastAt = now;
    const id = uid();
    const key = await keyOf(code);
    const d = decide(key) || { result: "pending" };
    if (d.result === "ok" && key) {
      local[key] = dir === "in";
      save(SKEY, local);
    }
    show(d);
    addLog(id, d);
    const q = load(QKEY, []);
    q.push({ id: id, zone: zone, code: code, dir: dir, at: new Date().toISOString(),
             device: deviceEl.value || "", offline: !navigator.onLine, local: d.result });
    save(QKEY, q);
    paint();
    send();
  }

  function reconcile(item, r) {
    const li = logEl.querySelector('[data-id="' + r.id + '"]');
    if (item && item.local !== r.result && r.result !== "refused") {
      if (li) {
        li.dataset.state = r.result;
        li.textContent += "  → " + label("conflict", { name: r.name || "", result: label(r.result) });
      }
      if (resultEl && li === logEl.firstElementChild) show({ result: r.result, name: r.name, message: r.name || r.message });
    }
  }

  function send() {
    const q = load(QKEY, []);
    if (!q.length || sending || !navigator.onLine) return paint();
    sending = true;
    const batch = q.slice(0, 200);
    fetch(root.getAttribute("data-sync-url"), {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token() },
      body: JSON.stringify({ scans: batch }),
    }).then(function (r) {
      if (r.ok || r.status === 400 || r.status === 403) {
        const sent = {};
        batch.forEach(function (s) { sent[s.id] = s; });
        save(QKEY, load(QKEY, []).filter(function (s) { return !sent[s.id]; }));
        return r.ok ? r.json().then(function (data) {
          (data.results || []).forEach(function (res) { reconcile(sent[res.id], res); });
        }) : null;
      }
      return null;
    }).catch(function () { /* offline: kept */ })
      .then(function () {
        sending = false;
        paint();
        if (load(QKEY, []).length && navigator.onLine) setTimeout(send, 300);
      });
  }

  function refresh() {
    if (!navigator.onLine) return paint();
    fetch(root.getAttribute("data-list-url"), { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        list = data;
        save(LKEY, data);
        if (!load(QKEY, []).length) { local = {}; save(SKEY, local); }  // the server's list now includes our scans
        paint();
      })
      .catch(function () { paint(); });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const v = input.value;
    input.value = "";
    handle(v);
    input.focus();
  });
  try { deviceEl.value = localStorage.getItem(DKEY) || ""; } catch (e) { /* ignore */ }
  deviceEl.addEventListener("change", function () {
    try { localStorage.setItem(DKEY, deviceEl.value); } catch (e) { /* ignore */ }
  });

  // camera scanning where the browser can decode QR codes itself (no library)
  if (camBtn && video && "BarcodeDetector" in window) {
    camBtn.hidden = false;
    let stream = null;
    camBtn.addEventListener("click", function () {
      if (stream) {
        stream.getTracks().forEach(function (t) { t.stop(); });
        stream = null;
        video.hidden = true;
        return;
      }
      const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
      navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then(function (s) {
        stream = s;
        video.srcObject = s;
        video.hidden = false;
        video.play();
        const tick = function () {
          if (!stream) return;
          detector.detect(video).then(function (codes) {
            if (codes.length) handle(codes[0].rawValue);
          }).catch(function () { /* frame not ready */ }).then(function () { setTimeout(tick, 300); });
        };
        tick();
      }).catch(function () { camBtn.hidden = true; });
    });
  }

  window.addEventListener("online", function () { send(); refresh(); });
  window.addEventListener("offline", paint);
  const every = Math.max(10, parseInt(root.getAttribute("data-refresh"), 10) || 60) * 1000;
  setInterval(refresh, every);
  setInterval(function () { if (load(QKEY, []).length) send(); }, 5000);
  paint();
  refresh();
  send();
})();
