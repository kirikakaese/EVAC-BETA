// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player service worker, built from frontend/src with `npm run build` - do not edit.
const r = self, c = "evac-player-v2";
r.addEventListener("install", (s) => {
  s.waitUntil(caches.open(c).then((e) => e.add("/player/")).catch(() => {
  })), r.skipWaiting();
});
r.addEventListener("activate", (s) => {
  s.waitUntil((async () => {
    for (const e of await caches.keys()) e !== c && await caches.delete(e);
    await r.clients.claim();
  })());
});
r.addEventListener("fetch", (s) => {
  const t = s, e = new URL(t.request.url);
  if (!(t.request.method !== "GET" || e.origin !== r.location.origin)) {
    if (e.pathname.startsWith("/player/api/content/files/")) {
      t.respondWith((async () => {
        const n = await caches.open(c), a = await n.match(t.request, { ignoreSearch: !0 });
        if (a) return a;
        const i = await fetch(t.request);
        return i.ok && i.status === 200 && await n.put(t.request, i.clone()), i;
      })());
      return;
    }
    if (!e.pathname.startsWith("/player/api/")) {
      if (e.pathname === "/player/" || e.pathname === "/player/index.html") {
        t.respondWith((async () => {
          const n = await caches.open(c);
          try {
            const a = await fetch(t.request);
            return a.ok && await n.put("/player/", a.clone()), a;
          } catch {
            return await n.match("/player/") ?? Response.error();
          }
        })());
        return;
      }
      e.pathname.startsWith("/static/") && t.respondWith((async () => {
        const n = await caches.open(c), a = await n.match(t.request);
        if (a) return a;
        const i = await fetch(t.request);
        return i.ok && await n.put(t.request, i.clone()), i;
      })());
    }
  }
});
