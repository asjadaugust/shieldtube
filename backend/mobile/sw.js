/* ================================================
   ShieldTube Service Worker
   ================================================ */

const CACHE_NAME = 'shieldtube-v1';
const THUMBNAIL_CACHE = 'shieldtube-thumbs-v1';
const MAX_THUMBNAIL_ENTRIES = 200;

/** Static assets to cache on install */
const STATIC_ASSETS = [
  '/mobile/',
  '/mobile/index.html',
  '/mobile/manifest.json',
  '/mobile/css/theme.css',
  '/mobile/css/app.css',
  '/mobile/js/api.js',
  '/mobile/js/components.js',
  '/mobile/js/player.js',
  '/mobile/js/swipe.js',
  '/mobile/js/app.js',
  '/mobile/icons/icon-192.svg',
  '/mobile/icons/icon-512.svg',
];

/** Install — cache static assets */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

/** Activate — clean old caches */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME && key !== THUMBNAIL_CACHE)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

/** Fetch — routing strategy */
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Thumbnail requests — cache-first with LRU eviction
  if (url.pathname.includes('/api/video/') && url.pathname.endsWith('/thumbnail')) {
    event.respondWith(thumbnailStrategy(event.request));
    return;
  }

  // API calls — network-first, fallback to cache for feeds
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(event.request));
    return;
  }

  // Static assets — cache-first
  event.respondWith(cacheFirstStrategy(event.request));
});


/** Cache-first: return cached version, fallback to network */
async function cacheFirstStrategy(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Offline fallback for navigation
    if (request.mode === 'navigate') {
      return caches.match('/mobile/index.html');
    }
    return new Response('Offline', { status: 503 });
  }
}


/** Network-first: try network, fallback to cache (for API/feeds) */
async function networkFirstStrategy(request) {
  try {
    const response = await fetch(request);
    if (response.ok && request.method === 'GET') {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: 'Offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}


/** Cache-first for thumbnails with LRU eviction */
async function thumbnailStrategy(request) {
  const cache = await caches.open(THUMBNAIL_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      // Evict oldest if over limit
      const keys = await cache.keys();
      if (keys.length >= MAX_THUMBNAIL_ENTRIES) {
        // Remove the oldest entries (first added)
        const toRemove = keys.length - MAX_THUMBNAIL_ENTRIES + 10;
        for (let i = 0; i < toRemove; i++) {
          await cache.delete(keys[i]);
        }
      }
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Return a transparent 1px placeholder
    return new Response('', { status: 404 });
  }
}
