// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player service worker, built from frontend/src with `npm run build` - do not edit.
function o(a) {
  return [...new Set([...a.matchAll(/(?:src|href)="(\/static\/[^"]+)"/g)].map((t) => t[1].replace(/&amp;/g, "&")))];
}
const s = self, r = "evac-player-v3";
async function h() {
  const a = await caches.open(r), t = await fetch("/player/", { cache: "no-store", credentials: "omit" });
  t.ok && (await a.put("/player/", t.clone()), await Promise.all(o(await t.text()).map((e) => a.add(e).catch(() => {
  }))));
}
s.addEventListener("install", (a) => {
  a.waitUntil(h().catch(() => {
  })), s.skipWaiting();
});
s.addEventListener("activate", (a) => {
  a.waitUntil((async () => {
    for (const e of await caches.keys()) e !== r && await caches.delete(e);
    await s.clients.claim();
  })());
});
s.addEventListener("fetch", (a) => {
  const t = a, e = new URL(t.request.url);
  if (!(t.request.method !== "GET" || e.origin !== s.location.origin)) {
    if (e.pathname.startsWith("/player/api/content/files/")) {
      t.respondWith((async () => {
        const c = await caches.open(r), n = await c.match(t.request, { ignoreSearch: !0 });
        if (n) return n;
        const i = await fetch(t.request);
        return i.ok && i.status === 200 && await c.put(t.request, i.clone()), i;
      })());
      return;
    }
    if (!e.pathname.startsWith("/player/api/")) {
      if (e.pathname === "/player/" || e.pathname === "/player/index.html") {
        t.respondWith((async () => {
          const c = await caches.open(r);
          try {
            const n = await fetch(t.request);
            return n.ok && await c.put("/player/", n.clone()), n;
          } catch {
            return await c.match("/player/") ?? Response.error();
          }
        })());
        return;
      }
      e.pathname.startsWith("/static/") && t.respondWith((async () => {
        const c = await caches.open(r), n = await c.match(t.request);
        if (n) return n;
        const i = await fetch(t.request);
        return i.ok && await c.put(t.request, i.clone()), i;
      })());
    }
  }
});
