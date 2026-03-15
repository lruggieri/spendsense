const CACHE_NAME = 'spendsense-v69';
const RUNTIME_CACHE = 'spendsense-runtime-v69';

// Assets to cache on install (static assets only, no dynamic data pages)
const PRECACHE_ASSETS = [
  '/static/css/categories.css',
  '/static/css/fetchers.css',
  '/static/css/groups.css',
  '/static/css/main.css',
  '/static/css/onboarding.css',
  '/static/css/patterns.css',
  '/static/css/review.css',
  '/static/js/categories.js',
  '/static/js/currency-utils.js',
  '/static/js/fab.js',
  '/static/js/fetchers.js',
  '/static/js/groups.js',
  '/static/js/onboarding.js',
  '/static/js/onboarding-wizard.js',
  '/static/js/patterns.js',
  '/static/js/review.js',
  '/static/js/passkey-manager.js',
  '/static/js/timezone-utils.js',
  '/static/js/date-filter-handler.js',
  '/static/js/email-token.js',
  '/static/js/gmail-fetch.js',
  '/static/manifest.json',
  '/static/favicon.ico',
  '/static/logo.png'
];

// Install event - cache core assets
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[Service Worker] Precaching assets');
        return cache.addAll(PRECACHE_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activating...');
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((cacheName) => {
              return cacheName !== CACHE_NAME && cacheName !== RUNTIME_CACHE;
            })
            .map((cacheName) => {
              console.log('[Service Worker] Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            })
        );
      })
      .then(() => self.clients.claim())
  );
});

// Fetch event - network first with cache fallback for API, cache first for static assets
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip cross-origin requests
  if (url.origin !== location.origin) {
    return;
  }

  // API requests: Network first, respect Cache-Control headers
  if (url.pathname.startsWith('/api/') ||
      request.method !== 'GET' ||
      url.pathname.includes('/assign-') ||
      url.pathname.includes('/update-') ||
      url.pathname.includes('/add-') ||
      url.pathname.includes('/recategorize')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Only cache GET requests if Cache-Control allows it
          if (request.method === 'GET' && response.status === 200) {
            const cacheControl = response.headers.get('Cache-Control');
            const shouldCache = cacheControl &&
                               !cacheControl.includes('no-store') &&
                               !cacheControl.includes('no-cache');

            if (shouldCache) {
              const responseClone = response.clone();
              caches.open(RUNTIME_CACHE).then((cache) => {
                cache.put(request, responseClone);
              });
            }
          }
          return response;
        })
        .catch(() => {
          // Fallback to cache for GET requests
          if (request.method === 'GET') {
            return caches.open(RUNTIME_CACHE).then(cache => cache.match(request));
          }
          // Return a custom offline response for POST/PUT/DELETE
          return new Response(
            JSON.stringify({ error: 'Offline - changes will sync when online' }),
            {
              status: 503,
              statusText: 'Service Unavailable',
              headers: new Headers({ 'Content-Type': 'application/json' })
            }
          );
        })
    );
    return;
  }

  // Static assets: Cache first, network fallback
  if (url.pathname.startsWith('/static/') ||
      PRECACHE_ASSETS.includes(url.pathname)) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          return fetch(request).then((response) => {
            // Cache the fetched resource
            if (response.status === 200) {
              const responseClone = response.clone();
              cache.put(request, responseClone);
            }
            return response;
          });
        });
      })
    );
    return;
  }

  // HTML pages: Network first, respect Cache-Control headers
  event.respondWith(
    fetch(request)
      .then((response) => {
        // Check Cache-Control header to decide if we should cache
        const cacheControl = response.headers.get('Cache-Control');
        const shouldCache = response.status === 200 &&
                           cacheControl &&
                           !cacheControl.includes('no-store') &&
                           !cacheControl.includes('no-cache');

        // Only cache if the server says it's okay
        if (shouldCache) {
          const responseClone = response.clone();
          caches.open(RUNTIME_CACHE).then((cache) => {
            cache.put(request, responseClone);
          });
        }

        return response;
      })
      .catch(() => {
        // Fallback to cache when offline
        return caches.open(RUNTIME_CACHE).then(cache => {
          return cache.match(request).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // Return a generic offline page
            return new Response(
              '<html><body><h1>Offline</h1><p>Please check your connection.</p></body></html>',
              { headers: { 'Content-Type': 'text/html' } }
            );
          });
        });
      })
  );
});

// Handle messages from clients
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }

  if (event.data && event.data.type === 'CLEAR_CACHE') {
    event.waitUntil(
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => caches.delete(cacheName))
        );
      }).then(() => {
        return self.clients.matchAll();
      }).then((clients) => {
        clients.forEach((client) => {
          client.postMessage({ type: 'CACHE_CLEARED' });
        });
      })
    );
  }
});

// Background sync for offline transactions (future enhancement)
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-transactions') {
    event.waitUntil(syncTransactions());
  }
});

async function syncTransactions() {
  // Placeholder for future offline transaction sync functionality
  console.log('[Service Worker] Background sync triggered');
}
