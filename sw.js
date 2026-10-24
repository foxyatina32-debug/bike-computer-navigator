// The app at this address is closed. This worker replaces the old one on friends' phones: it removes the cached copy
// of the old app (so it does not open offline either) and unregisters itself. The personal version in dima/ has its
// own worker and caches (velo-me-shell-*), which are left alone, as are the shared map tiles and libraries.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith('velo-shell')).map(k => caches.delete(k))))
    .then(() => self.registration.unregister())
    .then(() => self.clients.matchAll({ type: 'window' }))
    .then(cs => cs.forEach(c => { try { if (!new URL(c.url).pathname.includes('/dima/')) c.navigate(c.url); } catch {} })));
});
