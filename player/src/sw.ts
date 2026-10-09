// SPDX-License-Identifier: AGPL-3.0-or-later
// Service worker of the player (scope /player/): keeps the app shell available without a server.
// The page is fetched network-first (updates arrive), its assets cache-first (they are versioned with ?v=),
// the device API is never cached.
const sw = self as unknown as ServiceWorkerGlobalScope;

const CACHE = "evac-player-v1";

sw.addEventListener("install", (e) => {
  const event = e as ExtendableEvent;
  event.waitUntil(caches.open(CACHE).then((c) => c.add("/player/")).catch(() => undefined));
  void sw.skipWaiting();
});

sw.addEventListener("activate", (e) => {
  const event = e as ExtendableEvent;
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
    await sw.clients.claim();
  })());
});

sw.addEventListener("fetch", (e) => {
  const event = e as FetchEvent;
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== sw.location.origin) return;
  if (url.pathname.startsWith("/player/api/")) return;
  if (url.pathname === "/player/" || url.pathname === "/player/index.html") {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      try {
        const res = await fetch(event.request);
        if (res.ok) await cache.put("/player/", res.clone());
        return res;
      } catch {
        return (await cache.match("/player/")) ?? Response.error();
      }
    })());
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      const hit = await cache.match(event.request);
      if (hit) return hit;
      const res = await fetch(event.request);
      if (res.ok) await cache.put(event.request, res.clone());
      return res;
    })());
  }
});
