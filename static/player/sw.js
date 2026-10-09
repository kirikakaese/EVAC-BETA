// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player service worker, built from player/src with `npm run build` - do not edit.
const n = self, s = "evac-player-v1";
n.addEventListener("install", (i) => {
  i.waitUntil(caches.open(s).then((e) => e.add("/player/")).catch(() => {
  })), n.skipWaiting();
});
n.addEventListener("activate", (i) => {
  i.waitUntil((async () => {
    for (const e of await caches.keys()) e !== s && await caches.delete(e);
    await n.clients.claim();
  })());
});
n.addEventListener("fetch", (i) => {
  const t = i, e = new URL(t.request.url);
  if (!(t.request.method !== "GET" || e.origin !== n.location.origin) && !e.pathname.startsWith("/player/api/")) {
    if (e.pathname === "/player/" || e.pathname === "/player/index.html") {
      t.respondWith((async () => {
        const c = await caches.open(s);
        try {
          const a = await fetch(t.request);
          return a.ok && await c.put("/player/", a.clone()), a;
        } catch {
          return await c.match("/player/") ?? Response.error();
        }
      })());
      return;
    }
    e.pathname.startsWith("/static/") && t.respondWith((async () => {
      const c = await caches.open(s), a = await c.match(t.request);
      if (a) return a;
      const r = await fetch(t.request);
      return r.ok && await c.put(t.request, r.clone()), r;
    })());
  }
});
