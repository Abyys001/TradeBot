/**
 * Minimal service worker — installability, not offline trading.
 *
 * Android will not offer "install" without one, and a home-screen icon is what
 * the admin asked for. What it deliberately does NOT do is cache anything that
 * could make the panel lie:
 *
 *   - /api/** and /ws/** are never touched. A cached balance, position or
 *     price is a wrong number presented as a current one, which on this panel
 *     is worse than an error.
 *   - navigations are network-first, so a deploy is picked up on the next load
 *     rather than being pinned to a stale shell.
 *
 * Only immutable build assets (/_nuxt/** carry a content hash in the filename)
 * and the icons are cached, and only after the network has served them once.
 */
const CACHE = 'wm-static-v1'
const PRECACHE = ['/favicon.svg', '/icon-192.png', '/icon-512.png', '/apple-touch-icon.png']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  // Live data is never served from a cache. See the note above.
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) return

  const isImmutable = url.pathname.startsWith('/_nuxt/') || PRECACHE.includes(url.pathname)

  if (isImmutable) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone()
              caches.open(CACHE).then((cache) => cache.put(request, copy))
            }
            return response
          }),
      ),
    )
    return
  }

  // Everything else (documents included): network first, cache as a fallback
  // so a dropped connection shows the shell instead of the browser's error.
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok && request.mode === 'navigate') {
          const copy = response.clone()
          caches.open(CACHE).then((cache) => cache.put(request, copy))
        }
        return response
      })
      .catch(() => caches.match(request).then((hit) => hit || caches.match('/dashboard'))),
  )
})
