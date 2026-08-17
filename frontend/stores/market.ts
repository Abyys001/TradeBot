import { defineStore } from 'pinia'

/**
 * The price feed behind the chart and the position panel (spec §3).
 *
 * One store, one poll loop, one copy of "what is BTC worth right now".
 *
 * **Every number here came from an exchange.** The backend has no synthetic
 * source: when no provider answers it returns 503 and this store raises
 * `feedDown` instead of drawing anything. The last real candles stay on screen,
 * greyed and labelled — but nothing invents a bar, and `stale` stops the panel
 * presenting an old price as current.
 *
 * Prices arrive two ways, and the store treats them as one series:
 *
 *   - **streamed**, pushed bar by bar from the engine's exchange socket. This
 *     is the live path — the same tick the venue publishes, in the tens of
 *     milliseconds, with no poll interval in front of it.
 *   - **polled**, the REST feed below. It draws the history on load and takes
 *     over whenever the stream is not up, so the chart degrades to "a few
 *     seconds behind" rather than to "stopped".
 *
 * Polling never stops entirely while streaming: it drops to a slow repair loop
 * that re-fetches the window. A push feed can miss a bar across a reconnect,
 * and re-reading the series is how that heals without anyone noticing.
 *
 * The polling cadence is deliberately modest — this is a chart, not the order
 * path. Nothing here shares a budget with the fan-out.
 */
const CANDLE_POLL_MS = 15000
const TICKER_POLL_MS = 3000
/** While bars are streaming, the poll is only a safety net against gaps. */
const CANDLE_REPAIR_MS = 120000
const TICKER_STREAMING_MS = 30000
/** How long a *stream* may be silent before the price is no longer current. */
const STREAM_STALE_MS = 90000

/**
 * Pinned pairs that always appear at the top of the symbol picker and always
 * have live ticker data, regardless of which symbol the chart is showing.
 */
export const PINNED_SYMBOLS = ['BTCUSDC', 'HYPEUSDC', 'PUMPUSDC', 'SOLUSDC', 'ZECUSDC', 'LINKUSDC', 'KAITOUSDC', 'BMBUSDC', 'WLDUSDC', 'LITUSDC']
const PINNED_POLL_MS = 5000

export interface PinnedTicker {
  price: number | null
  changePct: number | null
  live: boolean
}

export type Interval = '1m' | '5m' | '15m' | '1h' | '4h' | '1d'

export interface Candle {
  time: number
  open: number
  high: number
  low: number
  close: number
}

/** Interval length in seconds — used to place a live tick in the right bar. */
const INTERVAL_SECONDS: Record<Interval, number> = {
  '1m': 60,
  '5m': 300,
  '15m': 900,
  '1h': 3600,
  '4h': 14400,
  '1d': 86400,
}

let candleTimer: ReturnType<typeof setInterval> | null = null
let tickerTimer: ReturnType<typeof setInterval> | null = null
let pinnedTimer: ReturnType<typeof setInterval> | null = null

/**
 * Cookie-persisted chart symbol. Read at module level so it is available
 * during store initialisation; written inside `setSymbol` on every change.
 */
let _symbolCookie: ReturnType<typeof useCookie<string>> | null = null

export const useMarketStore = defineStore('market', {
  state: () => ({
    symbol: 'BTCUSDC',
    market: 'futures' as 'futures' | 'spot',
    interval: '1m' as Interval,

    candles: [] as Candle[],
    price: null as number | null,
    changePct: null as number | null,

    /** True once real exchange data has arrived. Never true for anything else. */
    live: false,
    source: '',
    /**
     * The venue the feed is *pinned* to (`MARKET_DATA_PIN`), or '' when it
     * follows whatever exchange the accounts sit on.
     *
     * Distinct from `source` on purpose. `source` is who answered this
     * request; `pinned` is who is allowed to. They read as the same string
     * while everything is healthy, and the difference is the whole point of
     * the pin: a Binance mark compared against a Hyperliquid fill is a
     * different number, and sizing reads it.
     */
    pinnedSource: '',
    /** Measured engine→exchange round trip in ms. Null = nothing timed lately. */
    providerMs: null as number | null,
    loading: false,
    error: '',
    /**
     * Set when the API answered "no exchange reachable" (503). Distinct from
     * `error`: this is the honest empty state the panel renders instead of a
     * chart, not a transient request failure to retry quietly.
     */
    feedDown: false,
    /**
     * Set while the pair's on-demand history download is running (the API
     * answers 202). Distinct from `feedDown`: a 503 means no exchange is
     * reachable at all, while a 202 means the chart's history is being fetched
     * and will arrive — the panel says which one is true.
     */
    downloading: false,
    /** 0–100 across the download's series, straight from the backend status. */
    historyPercent: 0,
    /** How many other pairs are waiting in the download queue behind this one. */
    historyQueued: 0,
    lastTickAt: null as number | null,
    /**
     * Ticked on every poll *attempt*, successful or not. `stale` needs a
     * reactive clock: comparing Date.now() against lastTickAt inside a getter
     * would never re-evaluate once the polls started failing, which is exactly
     * when the panel must stop presenting the price as current.
     */
    clock: 0,

    symbols: [] as SymbolInfo[],
    /** Bumped whenever the whole series is replaced, so the chart can re-set it. */
    revision: 0,

    /**
     * True while bars are being pushed rather than polled.
     *
     * Shown in the top bar, because "live" meaning *streaming* and "live"
     * meaning *a real exchange produced this* are different promises and the
     * admin is entitled to know which one is currently true.
     */
    streaming: false,
    /** Which venue the stream is coming from — may differ from the poll's. */
    streamSource: '',
    /** Bumped on every streamed bar, so the chart can append without a watcher
     *  on the whole candle array. */
    tick: 0,

    /** Live ticker data for pinned pairs, always kept fresh. */
    pinnedTickers: {} as Record<string, PinnedTicker>,
  }),

  getters: {
    lastCandle: (s): Candle | null => s.candles[s.candles.length - 1] ?? null,

    /** The price everything marks against: the live tick, else the last close. */
    mark(): number | null {
      return this.price ?? this.lastCandle?.close ?? null
    },

    intervalSeconds: (s) => INTERVAL_SECONDS[s.interval],

    /**
     * Identifies *which series* is on screen, as opposed to how fresh it is.
     *
     * The chart uses this to decide whether a repaint is a new instrument
     * (snap the view back) or the same one refreshed (leave the view exactly
     * where the admin put it). Without the distinction, every 15-second poll
     * yanked the chart back to the newest candle mid-inspection.
     */
    seriesKey: (s) => `${s.symbol}|${s.interval}|${s.market}`,

    /**
     * Stale means the feed stopped answering; the panel greys the price.
     *
     * The threshold follows which feed is in force. Polled, four missed ticks
     * is twelve seconds and means the loop is broken. Streamed, silence is not
     * evidence of anything for much longer — an illiquid pair genuinely has no
     * trades for a minute, and the slow repair poll only refreshes `clock`
     * every thirty seconds, so the polled threshold would grey out a stream
     * that is working perfectly.
     */
    stale: (s) =>
      s.lastTickAt !== null &&
      s.clock - s.lastTickAt > (s.streaming ? STREAM_STALE_MS : TICKER_POLL_MS * 4),
  },

  actions: {
    /**
     * Fold one pushed bar into the series.
     *
     * The exchange re-sends the *same* bar on every tick until it closes, so
     * the rule is replace-or-append on the bar's own timestamp — never append
     * blindly, which is how a live chart grows a duplicate candle per tick.
     *
     * A bar for a pair or timeframe the admin has already switched away from
     * is dropped: the engine's unsubscribe and the panel's own state can be a
     * round trip apart, and repainting the chart with the wrong instrument is
     * far worse than missing one frame of the right one.
     */
    applyBar(payload: {
      symbol: string
      interval: string
      market: string
      source?: string
      bar: { t: number; o: string; h: string; l: string; c: string; closed?: boolean }
    }) {
      if (
        payload.symbol !== this.symbol ||
        payload.interval !== this.interval ||
        payload.market !== this.market
      ) {
        return
      }

      const bar: Candle = {
        time: payload.bar.t,
        open: Number(payload.bar.o),
        high: Number(payload.bar.h),
        low: Number(payload.bar.l),
        close: Number(payload.bar.c),
      }
      if (!Number.isFinite(bar.close)) return

      const last = this.candles[this.candles.length - 1]
      if (last && bar.time === last.time) {
        this.candles[this.candles.length - 1] = bar
      } else if (!last || bar.time > last.time) {
        this.candles.push(bar)
      } else {
        // Older than what is on screen: a late frame from a stream that just
        // handed over between providers. The series already moved past it.
        return
      }

      this.price = bar.close
      this.live = true
      if (payload.source) this.streamSource = payload.source
      if (!this.streaming) {
        // A bar can beat its own `market_stream_up` across the wire. Slow the
        // polls here too, or a stream that never announced itself would keep
        // the panel re-fetching a series it is already being pushed.
        this.streaming = true
        this.retime()
      }
      this.lastTickAt = Date.now()
      this.clock = Date.now()
      this.feedDown = false
      this.tick += 1
    },

    /** The engine has a venue answering again. */
    streamUp(source: string) {
      this.streaming = true
      this.streamSource = source
      this.retime()
    },

    /** No venue is streaming — fall back to the polled feed at full cadence. */
    streamDown() {
      if (!this.streaming && !this.streamSource) return
      this.streaming = false
      this.streamSource = ''
      this.retime()
    },

    /** Ask the engine for this pair's live bars, if the socket is up. */
    resubscribe() {
      const sent = useLiveStore().subscribeMarket({
        symbol: this.symbol,
        interval: this.interval,
        market: this.market,
      })
      // Until the first bar lands the panel is still on the polled feed, so
      // `streaming` stays false and the poll keeps its fast cadence.
      if (!sent) this.streamDown()
    },

    async loadSymbols() {
      if (this.symbols.length) return
      try {
        this.symbols = (await useApi().symbols()).symbols
      } catch {
        // The picker falls back to a free-text field; not worth an error banner.
      }
    },

    async loadCandles() {
      this.loading = !this.candles.length
      try {
        const feed = await useApi().candles({
          symbol: this.symbol,
          interval: this.interval,
          market: this.market,
        })
        // A late response for a symbol the admin already switched away from
        // must not repaint the chart with the wrong instrument.
        if (feed.symbol !== this.symbol || feed.interval !== this.interval) return
        this.candles = feed.candles.map((c) => ({
          time: c.t,
          open: Number(c.o),
          high: Number(c.h),
          low: Number(c.l),
          close: Number(c.c),
        }))
        this.live = feed.live
        this.source = feed.source
        this.pinnedSource = feed.pinned ?? this.pinnedSource
        this.providerMs = feed.provider_ms ?? this.providerMs
        this.error = ''
        this.feedDown = false
        this.applyHistory(feed.history)
        this.revision++
      } catch (e: any) {
        // 503 is the backend saying no exchange answered. It is not a transient
        // glitch to retry silently: the panel has to stop claiming the chart is
        // current, and it must not draw a bar nobody quoted.
        if (statusOf(e) === 503) {
          this.feedDown = true
          this.live = false
          this.source = ''
        }
        // A non-202 failure carries no history block; stop promising a
        // download that the next successful poll can always re-raise.
        this.applyHistory()
        this.error = errorMessage(e)
      } finally {
        this.loading = false
      }
    },

    /**
     * Fold the backend's on-demand history status into the panel.
     *
     * Only a `downloading` status keeps the flag raised, so the chart can say
     * "history being fetched" instead of an empty state; `none`, `ready`,
     * `failed` and an absent block all mean the chart shows what it has and
     * says nothing about a download.
     */
    applyHistory(history?: HistoryStatus) {
      if (history?.state === 'downloading') {
        this.downloading = true
        this.historyPercent = history.percent
        this.historyQueued = history.queued
        return
      }
      this.downloading = false
      this.historyPercent = 0
      this.historyQueued = 0
    },

    async loadTicker() {
      try {
        const quote = await useApi().ticker(this.symbol, this.market)
        if (quote.symbol !== this.symbol) return
        this.price = Number(quote.price)
        this.changePct = quote.change_pct === null ? null : Number(quote.change_pct)
        this.live = quote.live
        this.source = quote.source
        this.pinnedSource = quote.pinned ?? this.pinnedSource
        this.providerMs = quote.provider_ms ?? this.providerMs
        this.lastTickAt = Date.now()
        this.error = ''
        this.feedDown = false
        this.applyTick(this.price)
      } catch (e: any) {
        // The last real price stays on screen but `stale` greys it within a few
        // seconds. What must never happen is a *new* price appearing from
        // anywhere but an exchange, so nothing is written here.
        if (statusOf(e) === 503) {
          this.feedDown = true
          this.live = false
        }
        this.error = errorMessage(e)
      } finally {
        this.clock = Date.now()
      }
    },

    /**
     * Fold a tick into the current bar so the chart moves between candle
     * fetches. Opens a new bar when the tick crosses the interval boundary,
     * which is what keeps the last candle from growing forever.
     */
    applyTick(price: number) {
      const now = Math.floor(Date.now() / 1000)
      const bucket = Math.floor(now / this.intervalSeconds) * this.intervalSeconds
      const last = this.lastCandle
      if (!last) return
      if (bucket > last.time) {
        this.candles.push({ time: bucket, open: price, high: price, low: price, close: price })
        // Keep the series bounded; the chart never shows more than this anyway.
        if (this.candles.length > 600) this.candles.shift()
      } else {
        last.close = price
        last.high = Math.max(last.high, price)
        last.low = Math.min(last.low, price)
      }
    },

    async setSymbol(symbol: string) {
      const next = symbol.trim().toUpperCase()
      if (!next || next === this.symbol) return
      this.symbol = next
      this.price = null
      this.candles = []
      this.applyHistory()
      this.resubscribe()
      // Persist so the chart opens on the same pair after a refresh.
      if (_symbolCookie) _symbolCookie.value = next
      await Promise.all([this.loadCandles(), this.loadTicker()])
    },

    /** Not named `setInterval` — shadowing the global inside `start()` is a trap. */
    async setTimeframe(interval: Interval) {
      if (interval === this.interval) return
      this.interval = interval
      this.candles = []
      this.applyHistory()
      this.resubscribe()
      await this.loadCandles()
    },

    async setMarket(market: 'futures' | 'spot') {
      if (market === this.market) return
      this.market = market
      this.candles = []
      this.applyHistory()
      this.resubscribe()
      await Promise.all([this.loadCandles(), this.loadTicker()])
    },

    /**
     * Re-arm the poll loops at the cadence the current feed deserves.
     *
     * Called whenever streaming starts or stops. The polls are never cancelled
     * outright: a push feed that silently stops is indistinguishable from a
     * quiet market, and the slow repair loop is what notices.
     */
    retime() {
      if (import.meta.server) return
      if (candleTimer) clearInterval(candleTimer)
      if (tickerTimer) clearInterval(tickerTimer)
      candleTimer = setInterval(
        () => this.loadCandles(),
        this.streaming ? CANDLE_REPAIR_MS : CANDLE_POLL_MS,
      )
      tickerTimer = setInterval(
        () => this.loadTicker(),
        this.streaming ? TICKER_STREAMING_MS : TICKER_POLL_MS,
      )
    },

    /** Called by the terminal on mount; safe to call twice. */
    async start() {
      // Initialise the cookie handle once (composables cannot run in state factory).
      if (!_symbolCookie) {
        _symbolCookie = useCookie<string>('chart-symbol', {
          default: () => 'BTCUSDC',
          maxAge: 60 * 60 * 24 * 365,
          sameSite: 'lax',
        })
      }
      // Restore the last-viewed symbol from the cookie.
      const saved = _symbolCookie.value
      if (saved && saved !== this.symbol) {
        this.symbol = saved
      }
      await Promise.all([this.loadSymbols(), this.loadCandles(), this.loadTicker()])
      if (import.meta.server) return
      this.retime()
      this.resubscribe()
      this.startPinnedPolling()
    },

    stop() {
      if (candleTimer) clearInterval(candleTimer)
      if (tickerTimer) clearInterval(tickerTimer)
      if (pinnedTimer) clearInterval(pinnedTimer)
      candleTimer = null
      tickerTimer = null
      pinnedTimer = null
      useLiveStore().unsubscribeMarket()
      this.streaming = false
      this.streamSource = ''
    },

    /** Background ticker poll for pinned pairs so their prices are always fresh. */
    async loadPinnedTickers() {
      try {
        const data = await useApi().tickers(PINNED_SYMBOLS, 'spot')
        const next: Record<string, PinnedTicker> = {}
        for (const q of data.tickers) {
          next[q.symbol] = {
            price: Number(q.price),
            changePct: q.change_pct === null ? null : Number(q.change_pct),
            live: q.live,
          }
        }
        this.pinnedTickers = next
      } catch {
        // Background poll — a transient failure is not worth a banner.
      }
    },

    /** Start (or restart) the pinned-pairs background ticker poll. */
    startPinnedPolling() {
      if (import.meta.server) return
      if (pinnedTimer) clearInterval(pinnedTimer)
      this.loadPinnedTickers()
      pinnedTimer = setInterval(() => this.loadPinnedTickers(), PINNED_POLL_MS)
    },
  },
})
