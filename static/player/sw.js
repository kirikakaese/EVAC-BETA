// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player service worker, built from frontend/src with `npm run build` - do not edit.
function o(a) {
  return [...new Set([...a.matchAll(/(?:src|href)="(\/static\/[^"]+)"/g)].map((t) => t[1].replace(/&amp;/g, "&")))];
}
const i = self, r = "evac-player-v3";
async function h() {
  const a = await caches.open(r), t = await fetch("/player/", { cache: "no-store", credentials: "omit" });
  t.ok && (await a.put("/player/", t.clone()), await Promise.all(o(await t.text()).map((e) => a.add(e).catch(() => {
  }))));
}
i.addEventListener("install", (a) => {
  a.waitUntil(h().catch(() => {
  })), i.skipWaiting();
});
i.addEventListener("activate", (a) => {
  a.waitUntil((async () => {
    for (const e of await caches.keys()) e !== r && await caches.delete(e);
    await i.clients.claim();
  })());
});
i.addEventListener("fetch", (a) => {
  const t = a, e = new URL(t.request.url);
  if (!(t.request.method !== "GET" || e.origin !== i.location.origin)) {
    if (e.pathname.startsWith("/player/api/content/files/") || e.pathname.startsWith("/player/api/announcements/speech/")) {
      t.respondWith((async () => {
        const c = await caches.open(r), n = await c.match(t.request, { ignoreSearch: !0 });
        if (n) return n;
        const s = await fetch(t.request);
        return s.ok && s.status === 200 && await c.put(t.request, s.clone()), s;
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
        const s = await fetch(t.request);
        return s.ok && await c.put(t.request, s.clone()), s;
      })());
    }
  }
});
