// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player service worker, built from frontend/src with `npm run build` - do not edit.
function o(a) {
  return [...new Set([...a.matchAll(/(?:src|href)="(\/static\/[^"]+)"/g)].map((e) => e[1].replace(/&amp;/g, "&")))];
}
const i = self, r = "evac-player-v4";
async function h() {
  const a = await caches.open(r), e = await fetch("/player/", { cache: "no-store", credentials: "omit" });
  e.ok && (await a.put("/player/", e.clone()), await Promise.all(o(await e.text()).map((t) => a.add(t).catch(() => {
  }))));
}
i.addEventListener("install", (a) => {
  a.waitUntil(h().catch(() => {
  })), i.skipWaiting();
});
i.addEventListener("activate", (a) => {
  a.waitUntil((async () => {
    for (const t of await caches.keys()) t !== r && await caches.delete(t);
    await i.clients.claim();
  })());
});
i.addEventListener("fetch", (a) => {
  const e = a, t = new URL(e.request.url);
  if (!(e.request.method !== "GET" || t.origin !== i.location.origin)) {
    if (["/player/api/content/files/", "/player/api/announcements/speech/", "/player/api/evacuation/speech/"].some((n) => t.pathname.startsWith(n))) {
      e.respondWith((async () => {
        const n = await caches.open(r), c = await n.match(e.request, { ignoreSearch: !0 });
        if (c) return c;
        const s = await fetch(e.request);
        return s.ok && s.status === 200 && await n.put(e.request, s.clone()), s;
      })());
      return;
    }
    if (!t.pathname.startsWith("/player/api/")) {
      if (t.pathname === "/player/" || t.pathname === "/player/index.html") {
        e.respondWith((async () => {
          const n = await caches.open(r);
          try {
            const c = await fetch(e.request);
            return c.ok && await n.put("/player/", c.clone()), c;
          } catch {
            return await n.match("/player/") ?? Response.error();
          }
        })());
        return;
      }
      t.pathname.startsWith("/static/") && e.respondWith((async () => {
        const n = await caches.open(r), c = await n.match(e.request);
        if (c) return c;
        const s = await fetch(e.request);
        return s.ok && await n.put(e.request, s.clone()), s;
      })());
    }
  }
});
