// Velokomp service worker: keeps the app shell and libraries available offline.
// Map tiles are cached by the page itself (Cache Storage "velo-tiles-v1").
const SHELL = 'velo-shell-v17';
const LIBS = 'velo-libs-v1';
const SHELL_FILES = ['./', './index.html', './manifest.webmanifest', './icon-180.png', './icon-192.png', './icon-512.png', './off.html'];
const LIB_HOSTS = ['cdn.jsdelivr.net'];
// Libraries are cached at install, so the app opens with no network even on the second ever launch.
const LIB_URLS = [
  'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js',
  'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css',
  'https://cdn.jsdelivr.net/npm/leaflet-rotate@0.2.8/dist/leaflet-rotate.js',
  'https://cdn.jsdelivr.net/npm/sql.js@1.8.0/dist/sql-wasm.js',
  'https://cdn.jsdelivr.net/npm/sql.js@1.8.0/dist/sql-wasm.wasm'
];

self.addEventListener('install', e => {
  e.waitUntil(Promise.all([
    caches.open(SHELL).then(c => c.addAll(SHELL_FILES)),
    caches.open(LIBS).then(c => Promise.all(LIB_URLS.map(u => c.match(u).then(hit => hit || fetch(u, { mode: 'cors' }).then(r => r.ok && c.put(u, r))).catch(() => {}))))
  ]).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith('velo-shell') && k !== SHELL).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (LIB_HOSTS.includes(url.hostname)) {
    e.respondWith(caches.open(LIBS).then(async c => {
      const hit = await c.match(req.url); if (hit) return hit;
      const res = await fetch(req); if (res.ok || res.type === 'opaque') c.put(req.url, res.clone()); return res;
    }));
    return;
  }
  if (url.pathname.endsWith('/version.json')) return; // update check: always the network, never cached
  if (url.origin === self.location.origin) {
    e.respondWith(fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(SHELL).then(c => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req, { ignoreSearch: true }).then(r => r || caches.match('./index.html'))));
  }
});
