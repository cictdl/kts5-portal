/* Service worker — குறள் உறியடி · Kural Uriyadi, offline-first.
   shell: network first, the cached copy when offline, so a new version lands on the next open;
   data and fonts: cache first, kept as they are fetched (the chapters played, the language chosen).
   Raise VERSION when build/build_data.py is run again.
   The couplets lie in corpus/, not data/: the web server of the KTS portal hides every address with a part named data. */
const VERSION = 'v2';
const SHELL = 'ku-shell-' + VERSION;
const DATA = 'ku-data-' + VERSION;
const SHELL_URLS = ['./index.html', './app.js', './styles.css', './manifest.json', './assets/fonts.css', './assets/icon.svg',
  './assets/icon-192.png', './assets/icon-512.png', './assets/favicon-32.png', './corpus/meta.json', './corpus/scripts.json'];

self.addEventListener('install', e => {
  e.waitUntil((async () => { await (await caches.open(SHELL)).addAll(SHELL_URLS); await self.skipWaiting(); })());
});
self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith('ku-') && ![SHELL, DATA].includes(k)) await caches.delete(k);
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin || e.request.method !== 'GET') return;
  if (url.pathname.includes('/corpus/ch/') || url.pathname.includes('/corpus/tr/') || url.pathname.includes('/assets/fonts/')) {
    e.respondWith(caches.open(DATA).then(async c => (await c.match(e.request)) || fetch(e.request).then(r => {
      if (r.ok) c.put(e.request, r.clone());
      return r;
    })));
    return;
  }
  e.respondWith((async () => {
    try {
      const r = await fetch(e.request, { cache: 'no-cache' });
      if (r.ok) (await caches.open(SHELL)).put(e.request, r.clone());
      return r;
    } catch (err) {
      const cached = await caches.match(e.request, { ignoreSearch: true });
      if (cached) return cached;
      if (e.request.mode === 'navigate') return caches.match('./index.html');
      return Response.error();
    }
  })());
});
