import { WebSocket as UpstreamSocket } from 'ws'

/**
 * Same-origin WebSocket relay to Channels.
 *
 * The panel's live channel used to be the one thing that could not go through
 * the panel's own origin. `routeRules[].proxy` is an h3 `proxyRequest`, which
 * forwards the HTTP request and drops the `Upgrade` handshake, so `/ws` looked
 * routed and silently never connected. The workaround was to point the browser
 * straight at the backend port (`NUXT_PUBLIC_WS_BASE`) in development and to
 * let Caddy terminate `/ws` in production.
 *
 * That workaround is what broke every deployment in between. A baked
 * `ws://localhost:8000` is correct on the developer's laptop and meaningless
 * from anyone else's browser; an `https://` page cannot open a `ws://` socket
 * at all (mixed content); and a reverse proxy that was not told about `/ws`
 * forwards the page but not the upgrade. In all three the panel sat on
 * "Connecting" forever and both latency readouts stayed blank — the exact
 * symptom, and it only ever showed up away from localhost.
 *
 * A real nitro WebSocket *handler* is not a route rule and does not go through
 * `proxyRequest`: nitro hands the upgrade to the worker, which is where this
 * lives. So the panel now dials its own origin everywhere, and the socket
 * works under `nuxt dev`, under the built server, behind Caddy, and behind
 * whatever proxy someone else puts in front — anything that can serve the page
 * can now carry the socket.
 *
 * Caddy still short-circuits `/ws/*` straight to Channels in the production
 * stack. That is one hop fewer, not a different contract; this handler is what
 * makes every other arrangement work.
 *
 * **The session cookie is forwarded verbatim.** `TradingConsumer.connect()`
 * refuses anything that is not a logged-in staff user, and that gate is the
 * reason the channel may carry balances and per-leg failures at all. Relaying
 * the browser's own `Cookie` header keeps the check exactly where it was —
 * this adds a hop, never an exemption.
 */
export default defineWebSocketHandler({
  open(peer) {
    const target = (useRuntimeConfig().wsProxyTarget as string).replace(/\/+$/, '')
    const incoming = new URL(peer.request?.url ?? '/ws/trading/', 'http://localhost')

    // Forward the browser's own credentials and origin. Django checks both:
    // `AuthMiddlewareStack` reads the session from the cookie, and
    // `AllowedHostsOriginValidator` matches the origin's host against
    // ALLOWED_HOSTS. Dropping either turns an authenticated admin into a
    // rejected handshake, which is indistinguishable from an outage.
    const headers: Record<string, string> = {}
    for (const name of ['cookie', 'origin', 'user-agent', 'accept-language']) {
      const value = peer.request?.headers?.get?.(name)
      if (value) headers[name] = value
    }

    const upstream = new UpstreamSocket(`${target}${incoming.pathname}${incoming.search}`, {
      headers,
      // The panel is behind whatever proxy the deployment uses; the upstream
      // hop is inside the Docker network and needs no extra patience.
      handshakeTimeout: 10000,
    })

    // Frames the browser sends before the upstream handshake finishes are
    // held, not dropped: the store's first `subscribe_market` goes out
    // immediately after `onopen` and losing it would leave the chart polling.
    const pending: (string | ArrayBuffer)[] = []
    state.set(peer.id, { upstream, pending })

    upstream.on('open', () => {
      for (const frame of pending.splice(0)) upstream.send(frame)
    })
    upstream.on('message', (data: Buffer, isBinary: boolean) => {
      peer.send(isBinary ? data : data.toString())
    })
    // Close codes carry meaning the panel acts on — 4403 is "not staff", which
    // it must report rather than retry forever — so they are passed through.
    // Anything outside the range a browser will accept becomes 1011.
    upstream.on('close', (code: number, reason: Buffer) => {
      state.delete(peer.id)
      const safe = code >= 1000 && code <= 4999 && code !== 1005 && code !== 1006 ? code : 1011
      peer.close(safe, reason?.toString() || undefined)
    })
    // A consumer that refuses the handshake never opens a socket to close, so
    // its reason arrives as an HTTP status on the upgrade response instead. It
    // is worth recovering: `TradingConsumer` answers 403 for a session that is
    // not staff, and the panel must report that rather than retry it forever
    // as if the engine were down. Everything else is a genuine 1011.
    // Note this handler *replaces* the error path rather than preceding it:
    // `ws` only emits `error` for an unexpected response when nobody is
    // listening here, so this has to finish the job itself — hence the abort.
    upstream.on('unexpected-response', (request, res) => {
      const status = res.statusCode ?? 0
      res.resume()
      request.destroy()
      state.delete(peer.id)
      peer.close(status === 403 ? 4403 : 1011, status ? `engine answered ${status}` : undefined)
    })

    upstream.on('error', () => {
      state.delete(peer.id)
      peer.close(1011, 'upstream unavailable')
    })
  },

  message(peer, message) {
    const entry = state.get(peer.id)
    if (!entry) return
    const frame = message.text()
    if (entry.upstream.readyState === UpstreamSocket.OPEN) entry.upstream.send(frame)
    else entry.pending.push(frame)
  },

  close(peer) {
    const entry = state.get(peer.id)
    state.delete(peer.id)
    entry?.upstream.close()
  },

  error(peer) {
    const entry = state.get(peer.id)
    state.delete(peer.id)
    entry?.upstream.close()
  },
})

interface Relay {
  upstream: UpstreamSocket
  pending: (string | ArrayBuffer)[]
}

/**
 * One upstream socket per connected panel, keyed by peer.
 *
 * Deliberately not a WeakMap: `close` and `error` must be able to reach the
 * upstream socket to shut it down, and a panel that vanishes without a close
 * frame would otherwise leave a Channels connection — and its market
 * subscription — alive with nobody reading it.
 */
const state = new Map<string, Relay>()
