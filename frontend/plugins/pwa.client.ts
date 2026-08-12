/**
 * Registers the service worker so the panel can be installed to a home screen.
 *
 * Registration is deliberately late (after `load`) and failure-tolerant: this
 * exists to make the app installable, and nothing on the trading path may
 * depend on it. Skipped in dev, where a worker caching the shell fights HMR.
 */
export default defineNuxtPlugin(() => {
  if (!import.meta.client || !('serviceWorker' in navigator) || import.meta.dev) return

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // No worker means no install prompt — everything else still works.
    })
  })
})
