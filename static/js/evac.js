// EVAC portal helpers: theme toggle, menus, delegated data-action handlers, hold-to-confirm,
// auto-refresh, live event stream. No user-facing strings live here - templates pass text via data-* attributes.
(function () {
  const root = document.documentElement;
  const toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      document.cookie = "evac_theme=" + next + ";path=/;max-age=31536000;SameSite=Lax";
    });
  }

  // <details class="menu">: close when clicking outside or pressing Escape, return focus to the summary
  const menus = document.querySelectorAll("details.menu");
  if (menus.length) {
    document.addEventListener("click", function (e) {
      menus.forEach(function (menu) {
        if (menu.open && !menu.contains(e.target)) menu.removeAttribute("open");
      });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      menus.forEach(function (menu) {
        if (menu.open) { menu.removeAttribute("open"); menu.querySelector("summary").focus(); }
      });
    });
    // Tabbing out of an open menu closes it so focus never lands behind the panel
    menus.forEach(function (menu) {
      menu.addEventListener("focusout", function (e) {
        if (menu.open && e.relatedTarget && !menu.contains(e.relatedTarget)) menu.removeAttribute("open");
      });
    });
  }

  // Event sidebar on small screens (off-canvas): focus moves into the menu on open, back to the toggle on close
  const sideToggle = document.getElementById("sidenav-toggle");
  const side = document.getElementById("sidenav");
  if (sideToggle && side) {
    function setSide(open, refocus) {
      document.body.classList.toggle("sidenav-open", open);
      sideToggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        const first = side.querySelector("a, button");
        if (first && window.matchMedia("(max-width: 1000px)").matches) first.focus();
      } else if (refocus) {
        sideToggle.focus();
      }
    }
    sideToggle.addEventListener("click", function () {
      setSide(!document.body.classList.contains("sidenav-open"), false);
    });
    document.addEventListener("click", function (e) {
      if (document.body.classList.contains("sidenav-open") && !side.contains(e.target) && !sideToggle.contains(e.target)) setSide(false, false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && document.body.classList.contains("sidenav-open")) setSide(false, true);
    });
  }

  // Delegated actions instead of inline handlers:
  //   <button data-action="print">                          window.print()
  //   <button data-action="copy" data-target="#id" data-copied="Copied">  copy the target's text to the clipboard
  //   <select data-action="submit">                         submit the enclosing form on change
  //   <select data-action="navigate" data-href="/x/__slug__/">  go to data-href with __slug__ replaced by the value
  document.addEventListener("click", function (e) {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const action = el.getAttribute("data-action");
    if (action === "print") {
      e.preventDefault();
      window.print();
    } else if (action === "copy") {
      e.preventDefault();
      const target = document.querySelector(el.getAttribute("data-target"));
      if (!target || !navigator.clipboard) return;
      const text = "value" in target && target.value ? target.value : target.innerText;
      navigator.clipboard.writeText(text).then(function () {
        const done = el.getAttribute("data-copied");
        if (!done) return;
        const label = el.textContent;
        el.textContent = done;
        el.setAttribute("aria-live", "polite");
        setTimeout(function () { el.textContent = label; }, 1500);
      });
    }
  });
  document.addEventListener("change", function (e) {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const action = el.getAttribute("data-action");
    if (action === "submit" && el.form) {
      el.form.submit();
    } else if (action === "navigate" && el.value) {
      window.location = el.getAttribute("data-href").replace("__slug__", encodeURIComponent(el.value));
    }
  });

  // Auto-refresh for live dashboards: <body data-refresh="15">
  const refresh = document.querySelector("[data-refresh]");
  if (refresh) {
    const secs = parseInt(refresh.getAttribute("data-refresh"), 10);
    if (secs > 0) setTimeout(function () { window.location.reload(); }, secs * 1000);
  }

  // Confirm on dangerous forms / buttons: <form data-confirm="..."> or <button data-confirm="...">
  document.addEventListener("submit", function (e) {
    const form = e.target;
    const btn = e.submitter && e.submitter.getAttribute("data-confirm");
    const msg = btn || form.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Colour swatches: <span class="swatch" data-color="#22c55e"> (no inline styles under the CSP)
  document.querySelectorAll("[data-color]").forEach(function (el) {
    const c = el.getAttribute("data-color");
    if (!/^#[0-9a-fA-F]{6}$/.test(c)) return;
    el.style.backgroundColor = c;
    // data-contrast: text in black or white, whichever has the higher contrast on that colour
    if (el.hasAttribute("data-contrast")) {
      const lum = [1, 3, 5].map(function (i) {
        const v = parseInt(c.slice(i, i + 2), 16) / 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      el.style.color = 0.2126 * lum[0] + 0.7152 * lum[1] + 0.0722 * lum[2] > 0.179 ? "#000" : "#fff";
    }
  });

  // Hold-to-confirm for safety actions: <button data-hold="1500" data-hold-label="Keep holding…">.
  // The enclosing form only submits after the button was held down for data-hold milliseconds
  // (pointer or keyboard: Space/Enter held). Releasing early cancels. A plain click does nothing.
  document.querySelectorAll("button[data-hold]").forEach(function (btn) {
    const ms = parseInt(btn.getAttribute("data-hold"), 10) || 1500;
    const label = btn.textContent;
    let timer = null;
    let started = 0;
    function start(e) {
      if (timer) return;
      e.preventDefault();
      started = Date.now();
      btn.classList.add("holding");
      btn.style.setProperty("--hold-ms", ms + "ms");
      if (btn.dataset.holdLabel) btn.textContent = btn.dataset.holdLabel;
      timer = setTimeout(function () {
        timer = null;
        btn.classList.remove("holding");
        btn.dataset.held = "1";
        if (btn.form) btn.form.requestSubmit(btn);
      }, ms);
    }
    function cancel() {
      if (!timer) return;
      clearTimeout(timer);
      timer = null;
      btn.classList.remove("holding");
      btn.textContent = label;
    }
    btn.addEventListener("pointerdown", start);
    btn.addEventListener("pointerup", cancel);
    btn.addEventListener("pointerleave", cancel);
    btn.addEventListener("keydown", function (e) { if ((e.key === " " || e.key === "Enter") && !e.repeat) start(e); });
    btn.addEventListener("keyup", function (e) { if (e.key === " " || e.key === "Enter") cancel(); });
    btn.addEventListener("click", function (e) { if (btn.dataset.held !== "1") e.preventDefault(); });
  });

  // Live event stream: <div data-live-url="/sse/e/<slug>/" data-live-ws="ws://…/ws/e/<slug>/">.
  // Prefers WebSocket, falls back to SSE, then to long-poll. Dispatches "evac:message" DOM events and
  // updates [data-live-status] with the connection state (text comes from data-* attributes).
  const live = document.querySelector("[data-live-url]");
  if (live) {
    const status = document.querySelector("[data-live-status]");
    function setStatus(state) {
      if (!status) return;
      status.dataset.state = state;
      status.textContent = status.getAttribute("data-label-" + state) || state;
    }
    function dispatch(msg) { document.dispatchEvent(new CustomEvent("evac:message", { detail: msg })); }
    let since = 0;
    function longPoll() {
      setStatus("polling");
      fetch(live.getAttribute("data-poll-url") + "?since=" + since, { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) { (d.messages || []).forEach(function (m) { since = Math.max(since, m.seq); dispatch(m); }); longPoll(); })
        .catch(function () { setStatus("offline"); setTimeout(longPoll, 5000); });
    }
    function sse() {
      if (!window.EventSource) return longPoll();
      const es = new EventSource(live.getAttribute("data-live-url"));
      let opened = false;
      es.onopen = function () { opened = true; setStatus("sse"); };
      es.onmessage = function (e) { const m = JSON.parse(e.data); since = Math.max(since, m.seq || 0); dispatch(m); };
      es.onerror = function () { if (!opened) { es.close(); longPoll(); } else { setStatus("reconnecting"); } };
    }
    const wsUrl = live.getAttribute("data-live-ws");
    if (wsUrl && window.WebSocket) {
      let ws;
      try { ws = new WebSocket(wsUrl); } catch (err) { ws = null; }
      if (!ws) { sse(); } else {
        let opened = false;
        ws.onopen = function () { opened = true; setStatus("websocket"); };
        ws.onmessage = function (e) { const m = JSON.parse(e.data); since = Math.max(since, m.seq || 0); dispatch(m); };
        ws.onclose = function () { if (!opened) sse(); else { setStatus("reconnecting"); setTimeout(sse, 2000); } };
      }
    } else {
      sse();
    }
  }
})();

// Staff PWA (ADR-0021): service worker, Web Push switch, offline action queue, full-screen alerts.
// Strings come from data-* attributes of the elements involved.
(function () {
  function csrf() {
    try { return JSON.parse(document.body.getAttribute("hx-headers") || "{}")["X-CSRFToken"] || ""; } catch (e) { return ""; }
  }
  function postJSON(url, data) {
    return fetch(url, { method: "POST", credentials: "same-origin", body: JSON.stringify(data),
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() } });
  }

  // service worker (scope /); the screen player registers its own below /player/
  if ("serviceWorker" in navigator && location.pathname.indexOf("/player/") !== 0) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () { /* not fatal */ });
  }

  // ---- Web Push: <div data-push data-key="…" data-subscribe-url data-unsubscribe-url data-label-on/off/denied/unsupported>
  const push = document.querySelector("[data-push]");
  function b64ToBytes(s) {
    const pad = "=".repeat((4 - (s.length % 4)) % 4);
    const raw = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, function (c) { return c.charCodeAt(0); });
  }
  function pushState(state) {
    if (!push) return;
    push.dataset.state = state;
    const label = push.querySelector("[data-push-label]");
    if (label) label.textContent = push.getAttribute("data-label-" + state) || state;
    push.querySelectorAll("[data-push-when]").forEach(function (el) {
      el.hidden = el.getAttribute("data-push-when").split(" ").indexOf(state) === -1;
    });
  }
  function refreshPush() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      return pushState("unsupported");
    }
    if (Notification.permission === "denied") return pushState("denied");
    navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); })
      .then(function (sub) { pushState(sub ? "on" : "off"); })
      .catch(function () { pushState("off"); });
  }
  if (push) {
    refreshPush();
    document.addEventListener("click", function (e) {
      const btn = e.target.closest("[data-action='push-enable'], [data-action='push-disable']");
      if (!btn) return;
      e.preventDefault();
      navigator.serviceWorker.ready.then(function (reg) {
        if (btn.getAttribute("data-action") === "push-enable") {
          return Notification.requestPermission().then(function (perm) {
            if (perm !== "granted") return;
            return reg.pushManager.subscribe({ userVisibleOnly: true,
              applicationServerKey: b64ToBytes(push.getAttribute("data-key")) })
              .then(function (sub) { return postJSON(push.getAttribute("data-subscribe-url"), sub.toJSON()); });
          });
        }
        return reg.pushManager.getSubscription().then(function (sub) {
          if (!sub) return;
          return postJSON(push.getAttribute("data-unsubscribe-url"), { endpoint: sub.endpoint })
            .then(function () { return sub.unsubscribe(); });
        });
      }).then(refreshPush, refreshPush);
    });
  }

  // ---- offline queue: <form data-offline data-offline-label="Approve “x”"> is stored when the device is
  // offline and sent when it is back. [data-sync] shows the state (data-label-synced / -waiting with {n}).
  const KEY = "evac.offline-queue";
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } }
  function save(q) { try { localStorage.setItem(KEY, JSON.stringify(q)); } catch (e) { /* storage full or blocked */ } }
  function showSync() {
    const el = document.querySelector("[data-sync]");
    if (!el) return;
    const q = load();
    el.dataset.state = q.length ? "waiting" : (navigator.onLine ? "synced" : "offline");
    const tpl = el.getAttribute("data-label-" + el.dataset.state) || "";
    el.textContent = tpl.replace("{n}", String(q.length));
    const list = document.querySelector("[data-sync-list]");
    if (list) {
      list.replaceChildren.apply(list, q.map(function (item) {
        const li = document.createElement("li");
        li.textContent = item.label;
        return li;
      }));
    }
  }
  let flushing = false;
  function flush() {
    const q = load();
    if (!q.length || !navigator.onLine || flushing) return showSync();
    flushing = true;
    const item = q[0];
    fetch(item.action, { method: "POST", credentials: "same-origin", body: new URLSearchParams(item.body),
      headers: { "X-CSRFToken": csrf(), "X-EVAC-Queued": "1" }, redirect: "follow" })
      .then(function (r) {
        if (r.ok || r.status === 400 || r.status === 403 || r.status === 404) {
          // done, or refused for good (the server's message shows on the next page load)
          const rest = load().filter(function (x) { return x.id !== item.id; });
          save(rest);
        }
      })
      .catch(function () { /* still offline */ })
      .then(function () { flushing = false; showSync(); if (load().length && navigator.onLine) setTimeout(flush, 500); });
  }
  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!form.hasAttribute || !form.hasAttribute("data-offline") || navigator.onLine) return;
    e.preventDefault();
    const data = {};
    new FormData(form, e.submitter || undefined).forEach(function (v, k) { if (typeof v === "string") data[k] = v; });
    const q = load();
    q.push({ id: Date.now() + "-" + Math.random().toString(36).slice(2), action: form.action, body: data,
      label: form.getAttribute("data-offline-label") || form.action, at: new Date().toISOString() });
    save(q);
    showSync();
  }, true);
  window.addEventListener("online", flush);
  window.addEventListener("offline", showSync);
  showSync();
  flush();

  // ---- alerts: <div data-alert-overlay data-label-ack="…"> shows urgent messages full screen with sound.
  const overlay = document.querySelector("[data-alert-overlay]");
  function tone() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.5, 1.0, 1.5].forEach(function (t, i) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "square";
        osc.frequency.value = i % 2 ? 660 : 880;
        gain.gain.setValueAtTime(0.0001, ctx.currentTime + t);
        gain.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.4);
        osc.connect(gain).connect(ctx.destination);
        osc.start(ctx.currentTime + t);
        osc.stop(ctx.currentTime + t + 0.45);
      });
      setTimeout(function () { ctx.close(); }, 2500);
    } catch (e) { /* no audio */ }
    if (navigator.vibrate) navigator.vibrate([400, 200, 400, 200, 800]);
  }
  let lastAlert = "";
  function alertShow(title, body, url) {
    if (!overlay) return;
    const key = title + "|" + body;
    if (key === lastAlert && !overlay.hidden) return;  // the same alert via the live stream and Web Push
    lastAlert = key;
    overlay.querySelector("[data-alert-title]").textContent = title || "";
    overlay.querySelector("[data-alert-body]").textContent = body || "";
    const link = overlay.querySelector("[data-alert-link]");
    if (link) { link.hidden = !url; if (url) link.setAttribute("href", url); }
    overlay.hidden = false;
    const ack = overlay.querySelector("[data-alert-ack]");
    if (ack) ack.focus();
    tone();
  }
  if (overlay) {
    overlay.querySelector("[data-alert-ack]").addEventListener("click", function () { overlay.hidden = true; });
    document.addEventListener("evac:message", function (e) {
      const m = e.detail || {};
      if (m.type === "announcement.live" && m.data && m.data.alert) alertShow(m.data.title, m.data.text, m.data.url);
    });
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.addEventListener("message", function (e) {
        const m = (e.data && e.data.message) || {};
        if (e.data && e.data.type === "push" && m.level === "err" && document.visibilityState === "visible") {
          alertShow(m.title, m.body, m.url);
        }
      });
    }
  }
})();
