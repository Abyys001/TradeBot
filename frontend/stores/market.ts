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
/**
 * Bars asked for on load, and per page when scrolling back.
 *
 * 1000 is the server's cap on what a *venue* is asked for; beyond that the
 * backend fills the window out of the stored archive, which is where the real
 * depth is. The chart used to open on 300 and had no way to ask for more, so a
 * year of downloaded history was on disk and unreachable.
 */
const CANDLE_LIMIT = 1000
/** One page of older bars, fetched when the view reaches the left edge. */
const CANDLE_PAGE = 1000

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
export const PINNED_SYMBOLS = ['BTCUSDC', 'HYPEUSDC', 'PUMPUSDC', 'SOLUSDC', 'ZECUSDC', 'LINKUSDC', 'KAITOUSDC', 'BNBUSDC', 'WLDUSDC', 'LITUSDC']
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

/** One wire candle to one chart bar. Strings on the wire stay Decimal-safe there. */
function toCandle(c: { t: number; o: string; h: string; l: string; c: string }): Candle {
  return { time: c.t, open: Number(c.o), high: Number(c.h), low: Number(c.l), close: Number(c.c) }
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
 *
 * The handle's type comes from this factory rather than from
 * `ReturnType<typeof useCookie<string>>`: that annotation resolves the
 * no-default overload, whose ref is not writable, and `setSymbol` could not
 * assign to it.
 */
function symbolCookie() {
  return useCookie<string>('chart-symbol', {
    default: () => 'BTCUSDC',
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })
}

let _symbolCookie: ReturnType<typeof symbolCookie> | null = null

export const useMarketStore = defineStore('market', {
  state: () => ({
    symbol: 'BTCUSDC',
    market: 'futures' as 'futures' | 'spot',
    interval: '1m' as Interval,

    candles: [] as Candle[],
    price: null as number | null,
    changePct: null as number | null,

    /**
     * False once the archive has run out of older bars for this series, so
     * scrolling further back stops asking. Reset with the series itself.
     */
    hasMore: true,
    /** A page of history is in flight; the left edge must not re-trigger. */
    loadingOlder: false,
    /**
     * How many of the bars on screen came out of the stored archive rather than
     * the live response. The depth the admin is actually scrolling through.
     */
    storedBars: 0,

    /** True once real exchange data has arrived. Never true for anything else. */
    live: false,
    /**
     * True when the bars on screen came out of downloaded history rather than
     * the live feed — real exchange data that is merely old.
     *
     * Deliberately separate from `live`. `live` is a fact about the *price* on
     * the top line, which the ticker poll refreshes every few seconds; this is
     * a fact about the *series*, which the candle poll refreshes and which can
     * be hours behind while the price is current. Folding the two into one flag
     * is what let the panel badge a three-day-old chart as live.
     */
    stored: false,
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
     * The most bars to keep in memory: everything paged in so far, plus one
     * more page for the live tail to grow into. Grows as the admin scrolls
     * back, so history is never trimmed off the front by `applyTick`.
     */
    windowCap: (s) => Math.max(CANDLE_LIMIT, s.candles.length) + CANDLE_PAGE,

    /** The oldest bar on screen — where the next page back starts from. */
    oldestCandle: (s): Candle | null => s.candles[0] ?? null,

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

    /**
     * How many whole intervals the newest bar is behind the current bucket.
     *
     * 0 is the bar being built right now, 1 is the ordinary state for the first
     * moments after a rollover (the venue has not published the new bar yet).
     * Anything higher means bars stopped arriving, however healthy the ticker
     * looks — and the ticker *does* keep looking healthy, because it is a
     * different endpoint on a different cadence. This is the only place the
     * panel can tell that the chart itself has stopped moving.
     */
    barsBehind(): number | null {
      const last = this.lastCandle
      if (!last) return null
      // Read only to take the dependency: `clock` ticks on every poll attempt,
      // successful or not, and without it this getter would keep returning the
      // answer it computed when the bars were still arriving.
      void this.clock
      const seconds = this.intervalSeconds
      const bucket = Math.floor(Math.floor(Date.now() / 1000) / seconds) * seconds
      return Math.max(0, Math.round((bucket - last.time) / seconds))
    },

    /**
     * The series is no longer current — the chart is a picture of the past
     * while the price above it is not.
     *
     * Two intervals rather than one: at 1m a bar can legitimately be one bucket
     * behind for a few seconds after the rollover, and greying a working chart
     * is its own kind of lie.
     */
    chartStale(): boolean {
      const behind = this.barsBehind
      return this.stored || (behind !== null && behind >= 2)
    },
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
      // A pushed bar is the venue's own tick: whatever the series was before,
      // it is current now.
      this.stored = false
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
          limit: CANDLE_LIMIT,
        })
        // A late response for a symbol the admin already switched away from
        // must not repaint the chart with the wrong instrument.
        if (feed.symbol !== this.symbol || feed.interval !== this.interval) return
        const fresh = feed.candles.map(toCandle)
        // A refresh used to replace the series outright, which was harmless
        // while there was only ever one window of it. Now that older pages can
        // be scrolled in, replacing would throw them away every fifteen
        // seconds; anything older than this window is kept in front of it.
        const from = fresh[0]?.time ?? 0
        const older = this.candles.filter((c) => c.time < from)
        this.candles = older.concat(fresh)
        // Stored bars are real and old; the panel says which of the two it is
        // looking at rather than letting the ticker's freshness cover for them.
        // `live` stays the price feed's own flag: a stored series must not turn
        // the badge to "no feed" three times a minute while the ticker is
        // answering perfectly, and the ticker must not badge these bars fresh.
        this.stored = feed.stored === true
        this.storedBars = feed.stored_bars ?? 0
        if (feed.live) this.live = true
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
     * One page further back, out of the stored archive.
     *
     * Called when the chart's view reaches its left edge. `end` is the bar
     * before the oldest one on screen, so pages butt up against each other with
     * no gap and no overlap; the backend serves the window from `StoredCandle`
     * once the venue's own page limit runs out.
     *
     * A short page means the archive has nothing older, and `hasMore` stops the
     * chart asking again — otherwise every further scroll is a round trip that
     * can only ever return the same nothing.
     */
    async loadOlder() {
      const oldest = this.oldestCandle
      if (this.loadingOlder || !this.hasMore || !oldest) return
      const series = this.seriesKey
      this.loadingOlder = true
      try {
        const feed = await useApi().candles({
          symbol: this.symbol,
          interval: this.interval,
          market: this.market,
          limit: CANDLE_PAGE,
          end: oldest.time - 1,
        })
        // The admin can change instrument while a page is in flight; painting
        // it would splice another pair's bars onto this one's series.
        if (series !== this.seriesKey) return
        const older = feed.candles.map(toCandle).filter((c) => c.time < oldest.time)
        if (!older.length) {
          this.hasMore = false
          return
        }
        this.candles = older.concat(this.candles)
        this.storedBars += older.length
        // Short of a full page: that is the bottom of the archive.
        if (older.length < CANDLE_PAGE / 2) this.hasMore = false
        this.revision++
      } catch {
        // A failed page is not a broken chart — the bars already on screen are
        // untouched and the next scroll retries. `hasMore` deliberately stays
        // true so a transient 503 does not permanently end the scrollback.
      } finally {
        this.loadingOlder = false
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
     *
     * **Only onto a series that is actually current.** A quote is evidence of a
     * price now, never of what happened in the bars nobody sent us. When the
     * candle feed has been failing — a pinned venue in cooldown, a stream that
     * died quietly — the newest bar can be hours or days old, and appending the
     * live price to it drew a bar the exchange never published, sitting alone
     * across a gap the whole width of the outage. That single point then owned
     * the price scale and flattened every real candle into a line at the bottom
     * of the chart, which is the state in the screenshots.
     *
     * So the tick extends the series by at most one bucket. Behind that, the
     * bars stay exactly as the exchange sent them and `chartStale` says so.
     */
    applyTick(price: number) {
      const seconds = this.intervalSeconds
      const bucket = Math.floor(Math.floor(Date.now() / 1000) / seconds) * seconds
      const last = this.lastCandle
      if (!last) return
      if (bucket > last.time + seconds) return
      if (bucket > last.time) {
        this.candles.push({ time: bucket, open: price, high: price, low: price, close: price })
        // The series used to be trimmed to 600 bars here, which was fine while
        // 300 was all the chart could ever hold — and fatal once it can page
        // back into the archive, because every bar `loadOlder` prepended was
        // shifted straight back off the front by the next tick. What actually
        // needs bounding is the *live* tail this line appends to, so the cap is
        // the loaded window plus room for it to grow, not a flat 600.
        if (this.candles.length > this.windowCap) this.candles.shift()
      } else if (bucket === last.time) {
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
      this.stored = false
      this.hasMore = true
      this.storedBars = 0
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
      this.stored = false
      this.hasMore = true
      this.storedBars = 0
      this.applyHistory()
      this.resubscribe()
      await this.loadCandles()
    },

    async setMarket(market: 'futures' | 'spot') {
      if (market === this.market) return
      this.market = market
      this.candles = []
      this.stored = false
      this.hasMore = true
      this.storedBars = 0
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
      if (!_symbolCookie) _symbolCookie = symbolCookie()
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
