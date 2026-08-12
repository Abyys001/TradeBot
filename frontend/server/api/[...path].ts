/**
 * Same-origin proxy to the Django API.
 *
 * The browser only ever talks to the panel's own origin, which removes three
 * whole classes of failure at once:
 *
 *   - CORS preflights and credentialed cross-origin cookies
 *   - session cookies being treated as third-party
 *   - a system-wide HTTP/SOCKS proxy swallowing requests to localhost:8000,
 *     which is what produced "<no response> Failed to fetch" in the browser
 *     while curl --noproxy worked fine
 *
 * The backend URL is server-side only, so it can be a private hostname like
 * `backend:8000` that the browser never has to resolve.
 */
export default defineEventHandler(async (event) => {
  const target = useRuntimeConfig(event).apiProxyTarget.replace(/\/+$/, '')
  const incoming = getRequestURL(event)

  // Forward the path *verbatim*, trailing slash included. Helpers like joinURL
  // normalise it away, and Django then refuses to APPEND_SLASH-redirect a POST
  // (it cannot preserve the body across a redirect), which surfaces as a 500.
  const path = incoming.pathname.replace(/^\/api/, '')

  return proxyRequest(event, `${target}${path}${incoming.search}`, {
    headers: {
      'x-forwarded-host': getRequestHeader(event, 'host') ?? '',
      'x-forwarded-proto': getRequestProtocol(event),
    },
  })
})
