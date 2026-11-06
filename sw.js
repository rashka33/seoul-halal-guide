/* Offline copy of this site's own files. Network first, so a live visit always gets current listings.
 * Third-party requests (AlAdhan, map tiles) are left alone. Freshness is still judged at runtime. */
const CACHE = 'shg-v2';
const SHELL = ['./', 'index.html', 'styles.css', 'app.js', 'data/places.js', 'data/phrases.js', 'assets/vendor/leaflet/leaflet.css', 'assets/vendor/leaflet/leaflet.js', 'manifest.webmanifest', 'assets/icons/favicon.svg', 'assets/icons/icon-192.png', 'assets/icons/apple-touch-icon.png'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))));
});

self.addEventListener('fetch', event => {
  const {request} = event;
  if (request.method !== 'GET' || new URL(request.url).origin !== location.origin) return;
  event.respondWith(fetch(request).then(response => {
    if (response.status === 200) {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(request, copy)).catch(() => {});
    }
    return response;
  }).catch(async () => (await caches.match(request)) || (request.mode === 'navigate' && await caches.match('index.html')) || Response.error()));
});
