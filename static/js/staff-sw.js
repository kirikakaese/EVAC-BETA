// SPDX-License-Identifier: AGPL-3.0-or-later
// Service worker of the staff PWA (ADR-0021), served at /sw.js (scope /; the screen player has its own worker
// below /player/). It keeps the app shell and the last staff page for offline use and shows Web Push
// notifications. __VERSION__ and __SHELL__ are filled in by the server.
const VERSION = "__VERSION__";
const CACHE = "evac-staff-" + VERSION;
const SHELL = __SHELL__;

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () {
    return self.skipWaiting();
  }));
});

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf("evac-staff-") === 0 && k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function isStaffPage(url) { return /^\/e\/[^/]+\/staff\/$/.test(url.pathname); }

self.addEventListener("fetch", function (event) {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.indexOf("/player/") === 0) return;
  if (url.pathname.indexOf("/static/") === 0) {
    // versioned assets: cache first
    event.respondWith(caches.match(req).then(function (hit) {
      return hit || fetch(req).then(function (res) {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(function (c) { c.put(req, copy); }); }
        return res;
      });
    }));
    return;
  }
  if (req.mode === "navigate") {
    // network first; the staff page is kept for offline use, everything else falls back to the offline page
    event.respondWith(fetch(req).then(function (res) {
      if (res.ok && isStaffPage(url)) { const copy = res.clone(); caches.open(CACHE).then(function (c) { c.put(req, copy); }); }
      return res;
    }).catch(function () {
      return caches.match(req).then(function (hit) { return hit || caches.match("/offline/"); });
    }));
  }
});

self.addEventListener("push", function (event) {
  let msg = {};
  try { msg = event.data ? event.data.json() : {}; } catch (e) { msg = { title: event.data ? event.data.text() : "EVAC" }; }
  const urgent = msg.level === "err";
  event.waitUntil(self.registration.showNotification(msg.title || "EVAC", {
    body: msg.body || "",
    tag: msg.tag || undefined,
    data: { url: msg.url || "/" },
    icon: "/static/icons/evac-192.png",
    badge: "/static/icons/evac-192.png",
    requireInteraction: urgent,
    renotify: urgent,
    vibrate: urgent ? [400, 200, 400, 200, 800] : [200],
  }).then(function () {
    // open staff pages show the alert in the page too
    return self.clients.matchAll({ type: "window" }).then(function (list) {
      list.forEach(function (c) { c.postMessage({ type: "push", message: msg }); });
    });
  }));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (const c of list) { if (c.url === target && "focus" in c) return c.focus(); }
    return self.clients.openWindow(target);
  }));
});
