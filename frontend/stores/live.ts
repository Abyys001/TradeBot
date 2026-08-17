import { defineStore } from 'pinia'

/**
 * The one live channel to the engine.
 *
 * Previously each component that wanted live data opened its own WebSocket, so
 * the terminal and the dashboard each held a connection and neither saw what
 * the other received. There is exactly one socket now, owned here, opened once
 * by the app shell.
 *
 * It carries per-leg results and failure notices as they happen rather than
 * after the whole fan-out settles — with a short deadline and N accounts, the
 * admin should see the first failure immediately, not at the end.
 */
export interface LegResult {
  accountId: number
  ok: boolean
  error: string
  ms: number
  at: number
}

let socket: WebSocket | null = null
let retryTimer: ReturnType<typeof setTimeout> | null = null
let heartbeat: ReturnType<typeof setInterval> | null = null
let connectTimeout: ReturnType<typeof setTimeout> | null = null
let retries = 0
let intentionalClose = false
/** Set when a ping goes out, cleared by its pong. Module-level: not state. */
let pingSentAt: number | null = null

export const useLiveStore = defineStore('live', {
  state: () => ({
    connected: false,
    /** Nulled until the first connection attempt, so the UI can say "connecting". */
    everConnected: false,
    /** Set the moment the first socket is created, so "connecting" is bounded. */
    attempted: false,
    /**
     * The close code and reason of the last attempt.
     *
     * The panel used to report only "connecting" or "offline", and a socket
     * that had never once connected stayed on "connecting" forever — the same
     * word whether the handshake was in flight, the route did not exist, or
     * the session was refused for not being staff. Three different problems
     * with three different fixes, shown identically, is what made this
     * undebuggable from the deployment where it happened.
     */
    closeCode: null as number | null,
    closeReason: '',
    lastMessageAt: null as number | null,
    /**
     * Round-trip time to the engine, measured on the keepalive ping.
     *
     * Shown in the top bar because this panel's whole promise is a prompt
     * fan-out: if the admin's own link to the engine is 800ms, the deadline was
     * spent before the order was even sent, and that is worth knowing *before*
     * pressing send rather than afterwards from the latency chart.
     */
    pingMs: null as number | null,
    /** Recent samples, so a single lucky packet does not read as a fast link. */
    pingSamples: [] as number[],
    /**
     * The *other* half of the path: the engine's last measured round trip to
     * the exchange, reported in the pong.
     *
     * Browser→engine is often a millisecond on a local network and says
     * nothing about whether an order can reach Binance inside the spec §4
     * deadline. This is the number that does. Null when nothing has been
     * measured recently — never a placeholder.
     */
    exchangeMs: null as number | null,
    exchangeName: '',
    legResults: {} as Record<number, LegResult>,
    /** Balance snapshots pushed by the engine, keyed by account id. */
    balances: {} as Record<number, { balance: string; asset: string; at: number }>,
  }),

  getters: {
    /**
     * "connecting" is now a genuinely transient state: it means a handshake is
     * in flight, not "we have never managed it". A socket that has closed at
     * least once is offline — or refused, which is a different problem and gets
     * its own word because retrying will never fix it.
     */
    status(): 'live' | 'connecting' | 'offline' | 'refused' {
      if (this.connected) return 'live'
      if (this.closeCode === 4403) return 'refused'
      return this.attempted && this.closeCode !== null ? 'offline' : 'connecting'
    },

    /**
     * Why the channel is down, in the admin's terms — never a bare code.
     *
     * Empty while it is up. The point is that the top bar and the settings
     * page can always answer "why", which is what "it just says Connecting"
     * meant: the panel knew and did not say.
     */
    statusDetail(): string {
      if (this.connected) return ''
      if (this.closeCode === null) return this.attempted ? 'handshake' : 'idle'
      if (this.closeCode === 4403) return 'forbidden'
      if (this.closeCode === 1006) return 'unreachable'
      if (this.closeCode === 1011) return 'engine'
      return this.closeReason || `code ${this.closeCode}`
    },
    recentLegs(): LegResult[] {
      return Object.values(this.legResults).sort((a, b) => b.at - a.at)
    },

    /** Median of the recent samples — one stalled packet should not dominate. */
    pingMedian(): number | null {
      if (!this.pingSamples.length) return null
      const sorted = [...this.pingSamples].sort((a, b) => a - b)
      return sorted[Math.floor(sorted.length / 2)]
    },

    /**
     * Thresholds are about the spec §4 deadline, not about feeling fast: a
     * 250ms round trip is a large slice of even a generous deadline when it is
     * the admin's own link, and past 600ms no deadline survives however fast
     * the exchanges answer.
     */
    pingQuality(): 'good' | 'fair' | 'poor' | null {
      const value = this.pingMedian
      if (value === null) return null
      if (value < 250) return 'good'
      return value < 600 ? 'fair' : 'poor'
    },

    /**
     * Same deadline logic applied to the leg that actually carries the order.
     * A round trip to the exchange is paid twice inside the fan-out (send and
     * acknowledge), so 150ms is already a serious share of the budget.
     */
    exchangeQuality(): 'good' | 'fair' | 'poor' | null {
      const value = this.exchangeMs
      if (value === null) return null
      if (value < 150) return 'good'
      return value < 400 ? 'fair' : 'poor'
    },
  },

  actions: {
    /**
     * Same-origin: wss://<panel host>/ws/trading/, relayed to Channels by the
     * panel's own server (server/routes/ws/[...].ts).
     *
     * `NUXT_PUBLIC_WS_BASE` still overrides it for a deployment that puts
     * Channels on a separate hostname, but two overrides are refused rather
     * than obeyed, because both produce a socket that can never connect while
     * looking correctly configured:
     *
     *   - a loopback address seen from a browser that is not on the server. A
     *     baked `ws://localhost:8000` is right on the developer's laptop and
     *     meaningless from anyone else's machine — the single reason the panel
     *     connected in development and sat on "Connecting" on the VPS.
     *   - a `ws://` URL on an `https://` page. The browser blocks it as mixed
     *     content before the request leaves, so the failure never even reaches
     *     the network tab.
     *
     * In both cases the same-origin URL is what the deployment actually meant.
     */
    url(): string {
      const secure = location.protocol === 'https:'
      const sameOrigin = `${secure ? 'wss:' : 'ws:'}//${location.host}/ws/trading/`
      const configured = String(useRuntimeConfig().public.wsBase || '').trim()
      if (!configured) return sameOrigin

      let host = ''
      let insecure = false
      try {
        const parsed = new URL(configured.replace(/^ws/, 'http'))
        host = parsed.hostname
        insecure = parsed.protocol === 'http:'
      } catch {
        return sameOrigin
      }

      const loopback = ['localhost', '127.0.0.1', '::1', '[::1]'].includes(host)
      const browserIsLocal = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)
      if (loopback && !browserIsLocal) return sameOrigin
      if (insecure && secure) return sameOrigin
      return `${configured.replace(/\/+$/, '')}/trading/`
    },

    connect() {
      if (import.meta.server || socket) return
      intentionalClose = false
      this.attempted = true
      this.closeCode = null
      this.closeReason = ''
      socket = new WebSocket(this.url())

      // Safety net: if the upgrade never completes (proxy silently drops it,
      // backend unreachable, wrong port) the socket sits in CONNECTING state
      // forever — no onclose fires, no retry starts.  Force-close after 10 s
      // so the retry loop kicks in instead of showing "Connecting" forever.
      if (connectTimeout) clearTimeout(connectTimeout)
      connectTimeout = setTimeout(() => {
        if (socket && socket.readyState === WebSocket.CONNECTING) {
          socket.close(1000, 'handshake timeout')
        }
      }, 10_000)

      socket.onopen = () => {
        if (connectTimeout) { clearTimeout(connectTimeout); connectTimeout = null }
        this.connected = true
        this.everConnected = true
        this.closeCode = null
        retries = 0
        // The keepalive doubles as the latency probe: a silent proxy drops an
        // idle upgrade, and the round trip is the number the top bar shows.
        // Every 8s, so the reading is current without being chatty.
        this.ping()
        heartbeat = setInterval(() => this.ping(), 8000)
        // A reconnect has to re-join the market room: the engine dropped this
        // channel's subscription when the old socket died, so without this the
        // chart would stay on the polled feed until the admin touched it.
        useMarketStore().resubscribe()
      }

      socket.onmessage = (event) => {
        this.lastMessageAt = Date.now()
        let payload: any
        try {
          payload = JSON.parse(event.data)
        } catch {
          return
        }
        this.handle(payload)
      }

      socket.onclose = (event) => {
        if (connectTimeout) { clearTimeout(connectTimeout); connectTimeout = null }
        this.connected = false
        socket = null
        // What actually happened, so the panel can stop saying "Connecting"
        // and say why instead. 4403 is the consumer refusing a session that is
        // not staff — a wrong answer to retry forever, and the one failure the
        // admin can act on. 1006 is an abnormal close with no frame: the
        // handshake never completed, which is what a missing proxy route or an
        // unreachable host looks like from the browser.
        this.closeCode = event.code || null
        this.closeReason = event.reason || ''
        // A latency reading from a dead socket is a lie, not a stale number.
        this.pingMs = null
        this.pingSamples = []
        this.exchangeMs = null
        this.exchangeName = ''
        pingSentAt = null
        // No socket, no pushes. The chart must resume polling immediately
        // rather than sitting on a bar that has stopped updating.
        useMarketStore().streamDown()
        if (heartbeat) clearInterval(heartbeat)
        heartbeat = null
        if (intentionalClose) return
        // Backoff to 10s. The panel stays usable over REST while disconnected.
        const delay = Math.min(1000 * 2 ** retries++, 10000)
        retryTimer = setTimeout(() => this.connect(), delay)
      }

      socket.onerror = () => socket?.close()
    },

    /** Send a keepalive and start the clock; `pong` stops it. */
    ping() {
      if (!socket || socket.readyState !== WebSocket.OPEN) return
      pingSentAt = performance.now()
      socket.send(JSON.stringify({ type: 'ping' }))
    },

    /**
     * Follow one pair's live bars. Returns false when the socket is not up, so
     * the caller keeps polling rather than waiting for pushes that cannot come.
     *
     * The engine holds one exchange subscription per pair however many panels
     * ask for it, so this is cheap to call on every symbol or timeframe change
     * — and re-sending it is how switching works, since the engine drops the
     * previous room before joining the new one.
     */
    subscribeMarket(payload: { symbol: string; interval: string; market: string }): boolean {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false
      socket.send(JSON.stringify({ type: 'subscribe_market', ...payload }))
      return true
    },

    unsubscribeMarket() {
      if (!socket || socket.readyState !== WebSocket.OPEN) return
      socket.send(JSON.stringify({ type: 'unsubscribe_market' }))
    },

    handle(payload: any) {
      if (payload.type === 'pong') {
        // Reported by the engine whether or not this pong was the one we timed.
        this.exchangeMs = typeof payload.exchange_ms === 'number' ? payload.exchange_ms : null
        this.exchangeName = payload.exchange ?? ''
        if (pingSentAt === null) return
        const rtt = Math.round(performance.now() - pingSentAt)
        pingSentAt = null
        this.pingMs = rtt
        this.pingSamples = [...this.pingSamples, rtt].slice(-5)
        return
      }
      if (payload.type === 'market_bar') {
        useMarketStore().applyBar(payload)
        return
      }
      if (payload.type === 'market_stream_up') {
        useMarketStore().streamUp(payload.source ?? '')
        return
      }
      if (payload.type === 'market_stream_down') {
        // Not an outage: the REST feed is still real, just slower. The market
        // store goes back to polling on its own.
        useMarketStore().streamDown()
        return
      }
      if (payload.type === 'system_log') {
        useSystemLogStore().receive(payload)
        return
      }
      if (payload.type === 'notification') {
        useNotificationStore().receive({
          id: payload.id ?? `ws-${Date.now()}-${Math.random()}`,
          account: payload.account_id ?? null,
          accountLabel: payload.account_label ?? '',
          message: payload.message ?? '',
          code: payload.code ?? '',
          created_at: payload.created_at ?? new Date().toISOString(),
        })
      } else if (payload.type === 'leg_result') {
        for (const leg of payload.legs ?? []) {
          this.legResults[leg.account_id] = {
            accountId: leg.account_id,
            ok: leg.ok,
            error: leg.error ?? '',
            ms: leg.ms ?? 0,
            at: Date.now(),
          }
        }
      } else if (payload.type === 'stop_all') {
        // Spec §7: a halt flipped in one tab has to show in every open panel,
        // including one sitting on a page that never polls the policy.
        useTradingStore().applyHalt({
          stop_all: !!payload.stop_all,
          locked: !!payload.locked,
          reason: payload.reason ?? '',
        })
      } else if (payload.type === 'balances') {
        // One panel's refresh updates every open panel, which is what makes
        // "the balance of every account at all times" (spec §6) true on a
        // second screen that nobody is clicking.
        for (const row of payload.accounts ?? []) {
          this.balances[row.id] = {
            balance: String(row.balance ?? row.last_balance ?? ''),
            asset: row.asset ?? row.last_balance_asset ?? '',
            at: Date.now(),
          }
        }
        // A pushed balance is authoritative; fold it into the account list so
        // every surface reading balances sees the same figure.
        useAccountsStore().applyLiveBalances(this.balances)
      }
    },

    disconnect() {
      intentionalClose = true
      if (retryTimer) clearTimeout(retryTimer)
      if (heartbeat) clearInterval(heartbeat)
      if (connectTimeout) clearTimeout(connectTimeout)
      retryTimer = null
      heartbeat = null
      connectTimeout = null
      socket?.close()
      socket = null
      this.connected = false
      // A deliberate teardown (logout, page leave) is not a diagnosis. Clearing
      // these keeps a stale "refused" from greeting the next session.
      this.attempted = false
      this.closeCode = null
      this.closeReason = ''
    },
  },
})
