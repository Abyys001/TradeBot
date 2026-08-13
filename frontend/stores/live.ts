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
 * after the whole fan-out settles — with a 1-second budget and N accounts, the
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
let retries = 0
let intentionalClose = false
/** Set when a ping goes out, cleared by its pong. Module-level: not state. */
let pingSentAt: number | null = null

export const useLiveStore = defineStore('live', {
  state: () => ({
    connected: false,
    /** Nulled until the first connection attempt, so the UI can say "connecting". */
    everConnected: false,
    lastMessageAt: null as number | null,
    /**
     * Round-trip time to the engine, measured on the keepalive ping.
     *
     * Shown in the top bar because this panel's whole promise is a one-second
     * fan-out: if the admin's own link to the engine is 800ms, the budget was
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
     * budget. This is the number that does. Null when nothing has been
     * measured recently — never a placeholder.
     */
    exchangeMs: null as number | null,
    exchangeName: '',
    legResults: {} as Record<number, LegResult>,
    /** Balance snapshots pushed by the engine, keyed by account id. */
    balances: {} as Record<number, { balance: string; asset: string; at: number }>,
  }),

  getters: {
    status(): 'live' | 'connecting' | 'offline' {
      if (this.connected) return 'live'
      return this.everConnected ? 'offline' : 'connecting'
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
     * Thresholds are about the spec §4 budget, not about feeling fast: at
     * 250ms round trip a quarter of the one-second budget is the admin's own
     * link, and past 600ms the budget cannot be met however fast the exchanges
     * answer.
     */
    pingQuality(): 'good' | 'fair' | 'poor' | null {
      const value = this.pingMedian
      if (value === null) return null
      if (value < 250) return 'good'
      return value < 600 ? 'fair' : 'poor'
    },

    /**
     * Same budget logic applied to the leg that actually carries the order.
     * A round trip to the exchange is paid twice inside the fan-out (send and
     * acknowledge), so 150ms is already a third of the second.
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
     * Same-origin by default: ws://<panel host>/ws/trading/, which the Nuxt
     * server proxies onward. Set NUXT_PUBLIC_WS_BASE to point somewhere else.
     */
    url(): string {
      const configured = useRuntimeConfig().public.wsBase
      if (configured) return `${configured}/trading/`
      const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
      return `${scheme}//${location.host}/ws/trading/`
    },

    connect() {
      if (import.meta.server || socket) return
      intentionalClose = false
      socket = new WebSocket(this.url())

      socket.onopen = () => {
        this.connected = true
        this.everConnected = true
        retries = 0
        // The keepalive doubles as the latency probe: a silent proxy drops an
        // idle upgrade, and the round trip is the number the top bar shows.
        // Every 8s, so the reading is current without being chatty.
        this.ping()
        heartbeat = setInterval(() => this.ping(), 8000)
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

      socket.onclose = () => {
        this.connected = false
        socket = null
        // A latency reading from a dead socket is a lie, not a stale number.
        this.pingMs = null
        this.pingSamples = []
        this.exchangeMs = null
        this.exchangeName = ''
        pingSentAt = null
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
      retryTimer = null
      heartbeat = null
      socket?.close()
      socket = null
      this.connected = false
    },
  },
})
