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
    if (/^#[0-9a-fA-F]{6}$/.test(c)) el.style.backgroundColor = c;
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
