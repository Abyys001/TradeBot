/**
 * Attach the Content-Security-Policy the panel's own Settings card asked for.
 *
 * It has to happen here rather than in Django, because Nuxt is what renders
 * the HTML. A CSP on a JSON API response protects nothing — there is no
 * document for a browser to apply it to.
 *
 * The mode is read from the backend (`/security/csp/`, unauthenticated: it
 * reports a header a browser would receive anyway) and cached for a minute.
 * That cache is the whole performance story: a switch this rarely touched must
 * not put a backend round trip in front of every page render, and the panel is
 * a single-page app that renders its shell once.
 *
 * Failure is *no header*, never a broken page. A CSP the server could not read
 * is not a reason to serve the operator a panel with half its scripts blocked;
 * the switch is off until proven otherwise, like everything else in this layer.
 */
const TTL_MS = 60_000

let cached: { header: string; value: string } | null = null
let until = 0

export default defineEventHandler(async (event) => {
  // Only the HTML. The API proxy and the WebSocket relay carry no document,
  // and the static assets are served with their own headers.
  const path = getRequestURL(event).pathname
  if (path.startsWith('/api') || path.startsWith('/ws') || path.startsWith('/_nuxt')) return

  const now = Date.now()
  if (!cached || now > until) {
    const target = useRuntimeConfig(event).apiProxyTarget.replace(/\/+$/, '')
    try {
      const body = await $fetch<{ header: string; value: string }>(`${target}/security/csp/`)
      cached = body?.header ? { header: body.header, value: body.value } : null
    } catch {
      cached = null
    }
    until = now + TTL_MS
  }

  if (cached) setResponseHeader(event, cached.header, cached.value)
})
