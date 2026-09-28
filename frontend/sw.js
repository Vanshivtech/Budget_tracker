/* ABT — AI Budget Tracker Service Worker v4 */
const CACHE_NAME = "abt-v4";

const PRECACHE = [
    "/",
    "/static/styles.css?v=4",
    "/static/app.js?v=4",
    "/static/favicon.png",
    "/static/favicon.svg",
    "/static/icon-192.png",
    "/static/icon-512.png",
    "/static/Logo_ABT.png",
    "/manifest.json",
];

self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(PRECACHE))
    );
    self.skipWaiting();
});

self.addEventListener("activate", event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            )
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", event => {
    const { request } = event;
    const url = new URL(request.url);

    // Never cache API calls
    if (url.pathname.startsWith("/api/")) {
        event.respondWith(fetch(request));
        return;
    }

    // Network-first for HTML
    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(() => caches.match("/"))
        );
        return;
    }

    // Cache-first for static assets
    event.respondWith(
        caches.match(request).then(cached => cached || fetch(request))
    );
});
