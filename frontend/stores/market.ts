import { defineStore } from 'pinia'

/**
 * The price feed behind the chart and the position panel (spec §3).
 *
 * One store, one poll loop, one copy of "what is BTC worth right now". Before
 * this the terminal drew a synthetic random walk and nothing on the page could
 * tell the admin what the market was actually doing — so no position could show
 * a live PnL either.
 *
 * `live` is carried all the way from the backend: false means no exchange was
 * reachable and the series is synthetic. Every surface that draws this data has
 * to render that flag. An unlabelled fake price series on a trading screen is
 * how someone reads a number that was never real.
 *
 * The polling cadence is deliberately modest — this is a chart, not the order
 * path. Nothing here shares a budget with the 1-second fan-out.
 */
const CANDLE_POLL_MS = 15000
const TICKER_POLL_MS = 3000

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

export const useMarketStore = defineStore('market', {
  state: () => ({
    symbol: 'BTCUSDT',
    market: 'futures' as 'futures' | 'spot',
    interval: '1m' as Interval,

    candles: [] as Candle[],
    price: null as number | null,
    changePct: null as number | null,

    /** False while the feed is synthetic — surfaced as a badge, never hidden. */
    live: false,
    source: '',
    loading: false,
    error: '',
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
  }),

  getters: {
    lastCandle: (s): Candle | null => s.candles[s.candles.length - 1] ?? null,

    /** The price everything marks against: the live tick, else the last close. */
    mark(): number | null {
      return this.price ?? this.lastCandle?.close ?? null
    },

    intervalSeconds: (s) => INTERVAL_SECONDS[s.interval],

    /** Stale means the poll loop stopped answering; the panel greys the price. */
    stale: (s) => s.lastTickAt !== null && s.clock - s.lastTickAt > TICKER_POLL_MS * 4,
  },

  actions: {
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
        this.error = ''
        this.revision++
      } catch (e: any) {
        this.error = errorMessage(e)
      } finally {
        this.loading = false
      }
    },

    async loadTicker() {
      try {
        const quote = await useApi().ticker(this.symbol, this.market)
        if (quote.symbol !== this.symbol) return
        this.price = Number(quote.price)
        this.changePct = quote.change_pct === null ? null : Number(quote.change_pct)
        this.live = quote.live
        this.source = quote.source
        this.lastTickAt = Date.now()
        this.error = ''
        this.applyTick(this.price)
      } catch (e: any) {
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
      await Promise.all([this.loadCandles(), this.loadTicker()])
    },

    /** Not named `setInterval` — shadowing the global inside `start()` is a trap. */
    async setTimeframe(interval: Interval) {
      if (interval === this.interval) return
      this.interval = interval
      this.candles = []
      await this.loadCandles()
    },

    async setMarket(market: 'futures' | 'spot') {
      if (market === this.market) return
      this.market = market
      this.candles = []
      await Promise.all([this.loadCandles(), this.loadTicker()])
    },

    /** Called by the terminal on mount; safe to call twice. */
    async start() {
      await Promise.all([this.loadSymbols(), this.loadCandles(), this.loadTicker()])
      if (candleTimer || import.meta.server) return
      candleTimer = setInterval(() => this.loadCandles(), CANDLE_POLL_MS)
      tickerTimer = setInterval(() => this.loadTicker(), TICKER_POLL_MS)
    },

    stop() {
      if (candleTimer) clearInterval(candleTimer)
      if (tickerTimer) clearInterval(tickerTimer)
      candleTimer = null
      tickerTimer = null
    },
  },
})
