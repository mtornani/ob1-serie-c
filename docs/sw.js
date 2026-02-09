/**
 * OB1 Radar - Service Worker
 * Caching strategy: Network First, falling back to cache
 * data.json is NEVER cached (always fresh from network)
 */

const CACHE_NAME = 'ob1-radar-v6';
const STATIC_ASSETS = [
  './',
  './index.html',
  './css/style.css',
  './js/app.js',
  './manifest.json'
];

// Files that should NEVER be served from cache
const NEVER_CACHE = ['data.json', 'dna_matches.json'];

// Install: Cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate: Clean ALL old caches immediately
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => {
        return Promise.all(
          keys
            .filter(key => key !== CACHE_NAME)
            .map(key => {
              console.log('Removing old cache:', key);
              return caches.delete(key);
            })
        );
      })
      .then(() => self.clients.claim())
  );
});

// Fetch: Network first, fallback to cache
self.addEventListener('fetch', event => {
  // Skip non-GET requests
  if (event.request.method !== 'GET') return;

  // Skip cross-origin requests
  if (!event.request.url.startsWith(self.location.origin)) return;

  // NEVER cache data files - always go to network
  const isDataFile = NEVER_CACHE.some(f => event.request.url.includes(f));
  if (isDataFile) {
    event.respondWith(fetch(event.request));
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Clone the response to store in cache
        const responseClone = response.clone();

        caches.open(CACHE_NAME)
          .then(cache => {
            cache.put(event.request, responseClone);
          });

        return response;
      })
      .catch(() => {
        // Network failed, try cache
        return caches.match(event.request)
          .then(cachedResponse => {
            if (cachedResponse) {
              return cachedResponse;
            }

            // If no cache, return offline page for navigation
            if (event.request.mode === 'navigate') {
              return caches.match('./index.html');
            }

            return new Response('Offline', {
              status: 503,
              statusText: 'Service Unavailable'
            });
          });
      })
  );
});

// Handle background sync (future feature)
self.addEventListener('sync', event => {
  if (event.tag === 'sync-data') {
    event.waitUntil(syncData());
  }
});

// Handle push notifications (future feature)
self.addEventListener('push', event => {
  if (!event.data) return;

  const data = event.data.json();

  event.waitUntil(
    self.registration.showNotification(data.title || 'OB1 Radar', {
      body: data.body || 'Nuova opportunita disponibile!',
      icon: './icons/icon-192.svg',
      badge: './icons/icon-192.svg',
      tag: data.tag || 'ob1-notification',
      data: data.url || './'
    })
  );
});

// Handle notification click
self.addEventListener('notificationclick', event => {
  event.notification.close();

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(windowClients => {
        // Check if there is already a window/tab open
        for (const client of windowClients) {
          if (client.url.includes('ob1-serie-c') && 'focus' in client) {
            return client.focus();
          }
        }

        // Otherwise, open a new window
        if (clients.openWindow) {
          return clients.openWindow(event.notification.data);
        }
      })
  );
});

async function syncData() {
  console.log('Background sync triggered');
  // Future: sync saved opportunities
}
