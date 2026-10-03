/* ABT Service Worker — app-shell caching */
const CACHE_NAME = 'abt-v9';
const SHELL_ASSETS = [
  '/',
  '/static/styles.css',
  '/static/app.js',
  '/static/Logo_ABT.png',
  '/static/favicon.png',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/manifest.json',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // API calls: network only (never cache)
  if (url.pathname.startsWith('/api/')) return;

  // Static images and fonts: cache first
  if (url.pathname.match(/\.(png|svg|ico|jpg|woff2?)$/)) {
    e.respondWith(
      caches.match(e.request).then((cached) => {
        if (cached) return cached;
        return fetch(e.request).then((resp) => {
          if (resp.ok && e.request.method === 'GET') {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
          }
          return resp;
        });
      })
    );
    return;
  }

  // App shell (HTML, CSS, JS): Network first, cache fallback
  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        if (resp.ok && e.request.method === 'GET') {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
        }
        return resp;
      })
      .catch(() => caches.match(e.request))
  );
});

// --- Web Push Notifications ---
self.addEventListener('push', (e) => {
  let data = { title: 'Budget Tracker Alert', body: 'New notification', url: '/' };
  try {
    if (e.data) {
      data = e.data.json();
    }
  } catch (err) {
    if (e.data) data.body = e.data.text();
  }

  const options = {
    body: data.body,
    icon: '/static/icon-192.png',
    badge: '/static/favicon.png',
    data: { url: data.url || '/' },
    tag: data.tag || 'budget-notification',
    renotify: true,
  };

  e.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const targetUrl = e.notification.data?.url || '/';

  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          if (targetUrl && client.navigate) {
            client.navigate(targetUrl);
          }
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
