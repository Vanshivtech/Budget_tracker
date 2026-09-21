/* ================================================================
   Budget Tracker — PWA Service Worker (App Shell Cache)
   Instant repeat launches, resilient shell caching
   ================================================================ */

const CACHE_NAME = "budget-tracker-shell-v2";
const SHELL_ASSETS = [
  "/",
  "/static/styles.css?v=2",
  "/static/app.js?v=2",
  "/static/favicon.svg",
  "/static/logo.svg",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png"
];

// 1. Install: Pre-cache core app shell
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(SHELL_ASSETS).catch((err) => {
        console.warn("[SW] Cache addAll warning:", err);
      });
    }).then(() => self.skipWaiting())
  );
});

// 2. Activate: Clean up previous cache versions
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Fetch: Network-first for dynamic /api, stale-while-revalidate for static shell
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache API routes or non-GET requests
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) {
    return;
  }

  // Navigation requests (HTML document)
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((networkRes) => {
          if (networkRes && networkRes.status === 200) {
            const copy = networkRes.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put("/", copy));
          }
          return networkRes;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }

  // Static assets: Stale-while-revalidate
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});
