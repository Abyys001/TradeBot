/**
 * ChartAdapter — the seam described in docs/frontend/tradingview.md.
 *
 * Phase 1 is LightweightChartAdapter: free, no application, and it supports the
 * draggable SL/TP lines spec §3 requires. Phase 2 swaps in a
 * ChartingLibraryAdapter once TradingView grants access; nothing above this
 * interface changes.
 *
 * Colours are read from the CSS theme variables rather than hard-coded, so the
 * chart follows the light/dark switch. `applyTheme()` re-reads them, because
 * Lightweight Charts caches its options and will otherwise keep painting the
 * dark grid on a white page.
 *
 * **What is drawn, and what deliberately is not.** The chart carries the lines
 * the admin *acts on*: SL, TP, and a working limit order's entry. The live
 * price is an axis label, and a filled position's entry line only appears once
 * there is a position to have an entry. Everything else — the price readout,
 * the countdown, provenance — lives in the bars around the chart. Four lines
 * inside one narrow price band is how a drag lands on the wrong one.
 *
 * Markers are the exception, and they are deliberately not lines. *When* a
 * trade was entered and left is a point in time, not a price level, so it is
 * drawn against the time axis where it cannot be grabbed by mistake and cannot
 * crowd the SL/TP band. See `repaintMarkers` for why they group.
 *
 * The view is the admin's. Nothing here scrolls, zooms or re-fits the chart on
 * its own; `resetView()` runs when the instrument changes and when the admin
 * asks for it, and never on a data refresh.
 */
import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  type AutoscaleInfo,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type IPriceLine,
  type CandlestickData,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'

export type Bar = { time: Time; open: number; high: number; low: number; close: number }
/** Every line the admin can grab. `entry` is draggable only for a limit order. */
export type DragKind = 'sl' | 'tp' | 'entry'
export type SLTPKind = DragKind

/**
 * One moment worth marking on the chart: the platform's own entry or close —
 * from the admin's ticket or a bot's signal, both drawn the same way — or an
 * exchange getting in or out.
 *
 * `time` is the moment itself, in unix seconds. The adapter snaps it to the bar
 * that contains it, because a bar is the finest resolution the chart has — at
 * 1m the whole fan-out lands inside one candle.
 */
export type TradeMarker = {
  time: number
  kind: 'entry' | 'exit'
  side: 'long' | 'short'
  /** The exchange's name, or the platform's own ("You" or a bot's name). */
  label: string
  /** The platform's own action (admin ticket or bot), which leads its group's label. */
  admin: boolean
}

export interface ChartAdapter {
  mount(el: HTMLElement): Promise<void>
  setCandles(bars: Bar[]): void
  appendCandle(bar: Bar): void
  /**
   * Add older bars to the *front* of the series without moving the view.
   *
   * Lightweight Charts pins its time scale to bar indices, so inserting `n`
   * bars at the head shifts everything on screen `n` places right. This shifts
   * the visible range back by the same amount, which is what makes scrolling
   * into history feel continuous rather than jumping.
   */
  prependCandles(bars: Bar[]): void
  /**
   * Called when the view reaches the left edge of the loaded series — the
   * chart asking for another page of history. Fires at most once per arrival,
   * not once per frame of the scroll.
   */
  onNeedOlder(cb: () => void | Promise<void>): void
  showPosition(p: { entry: number; liquidation: number | null; side: 'long' | 'short' }): void
  showSLTP(sl: number | null, tp: number | null): void
  /**
   * Mark where trades were entered and left. Replaces the whole set, so the
   * caller passes what should be on screen rather than diffing.
   */
  setTradeMarkers(markers: TradeMarker[]): void
  clearPosition(): void
  onSLTPDrag(cb: (kind: DragKind, price: number) => void): void
  /**
   * Whether the entry line can be dragged. True for a working limit order —
   * dragging it *is* how the limit price is set — false once a position is
   * open, where the entry is a historical fact and not an input.
   */
  setEntryDraggable(value: boolean): void
  /**
   * Snap back to the newest candle and re-enable price autoscaling.
   *
   * Called on every symbol change. Without it, switching BTC → AVAX leaves the
   * price scale pinned where BTC was and the new candles sit $80k off-screen.
   */
  resetView(): void
  applyTheme(): void
  destroy(): void
  /** True while a line is held. Callers must not repaint lines mid-drag. */
  readonly isDragging: boolean
}

/** A marker mid-layout: its icon, where it sits, and who it stands for. */
type Placed = {
  marker: SeriesMarker<Time>
  up: boolean
  kind: 'entry' | 'exit'
  admin: boolean
  names: string[]
  x: number | null
  /** Folded into a neighbour's label, or beaten by one. Arrow only. */
  merged?: boolean
}

/** Index of the last bar at or before `time`. Bars are ascending. */
function barIndexAt(times: number[], time: number): number {
  let lo = 0
  let hi = times.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if ((times[mid] as number) <= time) lo = mid
    else hi = mid - 1
  }
  return lo
}

/**
 * The names on one icon, capped.
 *
 * Eight exchanges spelled out beside a candle is a paragraph lying across the
 * price. Two names and a count says who and how many in the width of a word,
 * and the position panel underneath is where the full list already lives.
 */
function groupLabel(names: string[], limit: number): string {
  if (names.length <= limit) return names.join(', ')
  return `${names.slice(0, limit).join(', ')} +${names.length - limit}`
}

function palette() {
  return {
    long: tokenColor('--c-long', '#3BC9D8'),
    short: tokenColor('--c-short', '#FF6B81'),
    entry: tokenColor('--c-ink-muted', '#8B94A3'),
    liquidation: tokenColor('--c-signal', '#F0A020'),
    grid: tokenColor('--c-chart-grid', '#1E232B'),
    text: tokenColor('--c-ink-muted', '#8B94A3'),
  }
}

export class LightweightChartAdapter implements ChartAdapter {
  private chart: IChartApi | null = null
  private series: ISeriesApi<'Candlestick'> | null = null
  /**
   * Markers are a series *primitive* rather than a series method: attached
   * once here, and the only thing `repaintMarkers` writes to. It dies with
   * the series, so `destroy` drops the reference rather than detaching.
   */
  private markerLayer: ISeriesMarkersPluginApi<Time> | null = null
  private lines: Partial<Record<'sl' | 'tp' | 'entry' | 'liq', IPriceLine>> = {}
  private dragCb: ((kind: DragKind, price: number) => void) | null = null
  private dragging: DragKind | null = null
  private hovered: DragKind | null = null
  private el: HTMLElement | null = null
  /** Every line's price. `liq` is not draggable but is scaled against like the rest. */
  private prices: {
    sl: number | null
    tp: number | null
    entry: number | null
    liq: number | null
  } = {
    sl: null,
    tp: null,
    entry: null,
    liq: null,
  }
  private entryDraggable = false
  private side: 'long' | 'short' = 'long'
  private colors = palette()
  /** Every entry and exit to mark, unsnapped. Bars decide where they land. */
  private markers: TradeMarker[] = []
  /** Names shown on one icon before the rest collapse into "+N". */
  private static readonly MARKER_NAMES = 2
  /** Rough width of a label character at the chart's font size, in pixels. */
  private static readonly LABEL_CHAR_PX = 6.5
  /** Clear space demanded either side of a label before it counts as clashing. */
  private static readonly LABEL_GAP_PX = 6
  /** Half the arrow glyph's width. Arrows always draw, labels work around them. */
  private static readonly ARROW_HALF_PX = 7
  /** What was last handed to the series, so a pan does not repaint for nothing. */
  private markerSignature = ''
  /** The series as given, so autoscale can be reasoned about (see `autoscale`). */
  private bars: Bar[] = []
  private visible: { from: number; to: number } | null = null
  /** Asked for another page of history; see `onNeedOlder`. */
  private needOlder: (() => void | Promise<void>) | null = null
  /** True between asking for a page and the bars for it arriving. */
  private awaitingOlder = false

  /**
   * How close to bar 0 the view has to come before another page is requested.
   * A screen's worth of slack, so the page is on its way before the admin
   * reaches the end of what is loaded and sees the series stop.
   */
  private static readonly PAGE_AHEAD_BARS = 50

  /**
   * How far from the visible bars a price line may sit and still stretch the
   * price scale, as a fraction of the bars' own price level.
   *
   * Lightweight Charts scales to the bars *and* every price line, which is
   * right for the SL/TP/entry of a real order — they are a few percent away and
   * the admin needs to see them against the candles. It stops being right when
   * a line lands somewhere the market is not: the candles collapse into a
   * one-pixel band at the edge and the chart stops being readable at exactly
   * the moment something is wrong. Past this distance the bars keep the scale
   * and the line keeps its axis label, which still says where it is.
   */
  private static readonly LINE_SCALE_BAND = 0.25

  async mount(el: HTMLElement) {
    this.el = el
    this.colors = palette()
    this.chart = createChart(el, {
      layout: { background: { color: 'transparent' }, textColor: this.colors.text, fontSize: 11 },
      grid: {
        vertLines: { color: this.colors.grid },
        horzLines: { color: this.colors.grid },
      },
      rightPriceScale: { borderColor: this.colors.grid },
      timeScale: { borderColor: this.colors.grid, timeVisible: true },
      crosshair: { mode: 0 },
      autoSize: true,
      // Touch: let a vertical swipe scroll the page instead of the chart
      // eating it, or the terminal becomes unscrollable on a phone.
      handleScroll: { vertTouchDrag: false },
    })
    this.series = this.chart.addSeries(CandlestickSeries, {
      upColor: this.colors.long,
      downColor: this.colors.short,
      wickUpColor: this.colors.long,
      wickDownColor: this.colors.short,
      borderVisible: false,
      // The live price belongs on the axis, not stretched across the chart.
      // Its horizontal line used to sit among SL, TP and entry — four lines
      // competing for the same band of pixels, and the two that matter are the
      // two you drag. The axis label says the same thing and gets out of the way.
      lastValueVisible: true,
      priceLineVisible: false,
      autoscaleInfoProvider: (original: () => AutoscaleInfo | null) => this.autoscale(original),
    })
    this.markerLayer = createSeriesMarkers(this.series)
    this.chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
      this.visible = range ? { from: Number(range.from), to: Number(range.to) } : null
      // Which labels fit is a function of zoom: bars that were a screen apart
      // are touching two scroll-wheel notches later.
      this.repaintMarkers()
    })
    // The *logical* range is in bar indices rather than timestamps, which is
    // what makes "how close is the view to the start of what we loaded" a
    // question with an answer. The time range above cannot say that — it
    // reports timestamps, and the gap between the oldest bar and the left of
    // the viewport is the same shape whether more history exists or not.
    this.chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (!range || this.awaitingOlder || !this.needOlder) return
      if (range.from > LightweightChartAdapter.PAGE_AHEAD_BARS) return
      this.awaitingOlder = true
      // Un-latched when the caller settles, whatever it settled as. Clearing it
      // only on the bars arriving would leave the chart permanently unable to
      // ask again after one failed page.
      Promise.resolve(this.needOlder()).finally(() => {
        this.awaitingOlder = false
      })
    })
    this.attachDragHandlers()
  }

  /**
   * The price range the scale should cover: the visible bars, plus the order
   * lines that are actually near them.
   *
   * Falls back to the library's own answer whenever there is nothing to reason
   * about — no bars yet, or a window with none in it — so panning past the end
   * of the series behaves exactly as before.
   */
  private autoscale(original: () => AutoscaleInfo | null): AutoscaleInfo | null {
    const info = original()
    const window = this.visibleBarRange()
    if (!info || !window) return info

    const level = (window.min + window.max) / 2
    const band = level * LightweightChartAdapter.LINE_SCALE_BAND
    let { min, max } = window
    for (const price of Object.values(this.prices)) {
      if (price === null || Math.abs(price - level) > band) continue
      min = Math.min(min, price)
      max = Math.max(max, price)
    }
    return { priceRange: { minValue: min, maxValue: max }, margins: info.margins }
  }

  private visibleBarRange(): { min: number; max: number } | null {
    if (!this.bars.length) return null
    const from = this.visible?.from ?? -Infinity
    const to = this.visible?.to ?? Infinity
    let min = Infinity
    let max = -Infinity
    for (const bar of this.bars) {
      const time = Number(bar.time)
      if (time < from || time > to) continue
      if (bar.low < min) min = bar.low
      if (bar.high > max) max = bar.high
    }
    return max > -Infinity ? { min, max } : null
  }

  applyTheme() {
    if (!this.chart || !this.series) return
    this.colors = palette()
    this.chart.applyOptions({
      layout: { textColor: this.colors.text },
      grid: { vertLines: { color: this.colors.grid }, horzLines: { color: this.colors.grid } },
      rightPriceScale: { borderColor: this.colors.grid },
      timeScale: { borderColor: this.colors.grid },
    })
    this.series.applyOptions({
      upColor: this.colors.long,
      downColor: this.colors.short,
      wickUpColor: this.colors.long,
      wickDownColor: this.colors.short,
    })
    this.showSLTP(this.prices.sl, this.prices.tp)
    // Marker colours come from the same tokens the candles do.
    this.repaintMarkers()
  }

  setCandles(bars: Bar[]) {
    const grewAtTheFront =
      this.bars.length > 0 && bars.length > this.bars.length && bars[0].time < this.bars[0].time
    if (grewAtTheFront) {
      // A poll that also carries pages the admin scrolled in. Treat it as a
      // prepend so the view holds still, rather than as a fresh series.
      this.prependCandles(bars)
      return
    }
    this.bars = bars.slice()
    this.series?.setData(bars as CandlestickData[])
    // Which bar a marker belongs to is a fact about *these* bars: a timeframe
    // change re-buckets every one of them.
    this.repaintMarkers()
  }

  prependCandles(bars: Bar[]) {
    const added = bars.length - this.bars.length
    const range = this.chart?.timeScale().getVisibleLogicalRange()
    this.bars = bars.slice()
    this.series?.setData(bars as CandlestickData[])
    // `setData` leaves the logical range alone, and the range is bar *indices*
    // — so the bars the admin was looking at have just slid `added` places to
    // the right underneath a viewport that did not move. Shifting the range by
    // the same amount puts them back where they were.
    if (range && added > 0) {
      this.chart?.timeScale().setVisibleLogicalRange({
        from: range.from + added,
        to: range.to + added,
      })
    }
    this.repaintMarkers()
  }

  onNeedOlder(cb: () => void | Promise<void>) {
    this.needOlder = cb
  }

  setTradeMarkers(markers: TradeMarker[]) {
    this.markers = markers.slice().sort((a, b) => a.time - b.time)
    this.repaintMarkers()
  }

  /**
   * Snap every marker to the bar holding it, then draw **one icon per bar and
   * direction** — never one per exchange.
   *
   * The grouping is the whole point. A fan-out puts the admin's entry and every
   * exchange's fill inside the same second, so drawn separately they are a
   * stack of icons over one candle, hiding the price exactly where the admin
   * most wants to read it. Collapsed, they are a single arrow labelled with who
   * is in it, which answers "when did we get in, and who came with us" without
   * covering the bar. Entry and exit stay separate icons on opposite sides of
   * the candle, because those are the two things being asked about.
   */
  private repaintMarkers() {
    if (!this.series || !this.markerLayer) return
    if (!this.bars.length || !this.markers.length) {
      if (this.markerSignature !== '') {
        this.markerSignature = ''
        this.markerLayer.setMarkers([])
      }
      return
    }

    const times = this.bars.map((b) => Number(b.time))
    const first = times[0] as number

    type Group = {
      time: number
      kind: 'entry' | 'exit'
      side: 'long' | 'short'
      names: string[]
      admin: boolean
    }
    const groups = new Map<string, Group>()

    for (const m of this.markers) {
      // Older than the loaded history. Its bar is not on screen, and pinning it
      // to the first one would put the icon at a time it did not happen.
      if (m.time < first) continue
      const at = times[barIndexAt(times, m.time)] as number
      const key = `${at}|${m.kind}`
      let group = groups.get(key)
      if (!group) {
        group = { time: at, kind: m.kind, side: m.side, names: [], admin: false }
        groups.set(key, group)
      }
      if (m.admin) group.admin = true
      if (group.names.includes(m.label)) continue
      // The admin's own action leads: it is the one the other names followed.
      if (m.admin) group.names.unshift(m.label)
      else group.names.push(m.label)
    }

    const scale = this.chart?.timeScale()
    const placed: Placed[] = []
    for (const g of groups.values()) {
      // An entry sits on the side the trade is taken from and points that way;
      // an exit sits opposite and points back out. Long and short therefore
      // mirror each other, and an entry can never be mistaken for an exit.
      const up = g.kind === 'entry' ? g.side === 'long' : g.side === 'short'
      placed.push({
        marker: {
          time: g.time as Time,
          position: up ? 'belowBar' : 'aboveBar',
          shape: up ? 'arrowUp' : 'arrowDown',
          // Entries carry the trade's colour because they are the loud event;
          // exits are muted, being a record of something already over.
          color:
            g.kind === 'entry'
              ? g.side === 'long'
                ? this.colors.long
                : this.colors.short
              : this.colors.text,
          size: 1,
        },
        up,
        kind: g.kind,
        admin: g.admin,
        names: g.names,
        x: scale ? (scale.timeToCoordinate(g.time as Time) as number | null) : null,
      })
    }

    this.layOutLabels(placed)

    // Lightweight Charts requires markers in ascending time order.
    const out = placed.map((p) => p.marker).sort((a, b) => Number(a.time) - Number(b.time))
    // Panning fires the range subscription continuously; only touch the series
    // when the result actually differs, or every frame repaints for nothing.
    const signature = out.map((m) => `${String(m.time)}:${m.text ?? ''}`).join('|')
    if (signature === this.markerSignature) return
    this.markerSignature = signature
    this.markerLayer.setMarkers(out)
  }

  /** Half the pixel width a set of names will occupy once rendered. */
  private labelHalf(names: string[]): number {
    return (
      (groupLabel(names, LightweightChartAdapter.MARKER_NAMES).length *
        LightweightChartAdapter.LABEL_CHAR_PX) /
      2
    )
  }

  /**
   * Decide which icons carry text, and what that text says.
   *
   * Lightweight Charts centres a marker's text on its arrow and never checks
   * whether two of them land on the same pixels, so left alone this renders as
   * one unreadable smear across the price — the exact thing markers must not
   * do. Two passes fix it:
   *
   *   1. **Merge.** Icons of the same kind standing closer than their own label
   *      is wide are one event as far as the eye is concerned — a fan-out that
   *      straddled a bar boundary, or a straggling leg. Their names collapse
   *      into the leftmost icon's label, and *every arrow stays where it is*.
   *      Nothing about when an exchange got in is lost; only the repeated text
   *      is. This is what makes the admin's own label survive a neighbour,
   *      rather than being blanked by an arrow it cannot move.
   *   2. **Drop.** Whatever labels still overlap after merging belong to
   *      genuinely different events (an entry and an exit sharing a band, two
   *      trades at a zoomed-out scale). There is nothing sensible to merge, so
   *      the lower-priority one loses its text and keeps its arrow. Admin-led
   *      icons are considered first, so the one saying when *we* acted is never
   *      the one that yields.
   */
  private layOutLabels(items: Placed[]) {
    const { ARROW_HALF_PX: ARROW, LABEL_GAP_PX: GAP } = LightweightChartAdapter

    // Pass 1 — merge. Same band *and* same kind: an entry and an exit can share
    // a band when one trade is long and the next is short, and rolling those
    // two into one label would claim a getting-in was a getting-out.
    for (const up of [true, false]) {
      for (const kind of ['entry', 'exit'] as const) {
        const band = items
          .filter((i) => i.up === up && i.kind === kind && i.x !== null)
          .sort((a, b) => (a.x as number) - (b.x as number))
        let anchor: Placed | null = null
        for (const item of band) {
          if (anchor && (item.x as number) - (anchor.x as number) < this.labelHalf(anchor.names) + ARROW + GAP) {
            for (const name of item.names) {
              if (!anchor.names.includes(name)) anchor.names.push(name)
            }
            item.merged = true
          } else {
            anchor = item
          }
        }
      }
    }

    // Pass 2 — drop what still collides, admin-led icons first.
    for (const up of [true, false]) {
      const band = items
        .filter((i) => i.up === up && i.x !== null && !i.merged)
        .sort((a, b) => (a.admin === b.admin ? (a.x as number) - (b.x as number) : a.admin ? -1 : 1))
      const taken: [number, number][] = []
      for (const item of band) {
        const half = this.labelHalf(item.names)
        const left = (item.x as number) - half - GAP
        const right = (item.x as number) + half + GAP
        if (taken.some(([l, r]) => left < r && right > l)) item.merged = true
        else taken.push([left, right])
      }
    }

    for (const item of items) {
      if (!item.merged) item.marker.text = groupLabel(item.names, LightweightChartAdapter.MARKER_NAMES)
    }
  }

  /** True while a line is held, so callers can suppress conflicting repaints. */
  get isDragging() {
    return this.dragging !== null
  }

  appendCandle(bar: Bar) {
    const last = this.bars[this.bars.length - 1]
    // `update` replaces the last bar or starts a new one; the mirror has to
    // follow the same rule or the autoscale window drifts from what is drawn.
    if (last && Number(last.time) === Number(bar.time)) this.bars[this.bars.length - 1] = bar
    else if (!last || Number(bar.time) > Number(last.time)) {
      this.bars.push(bar)
      // A trade entered seconds before its bar opened snapped to the previous
      // one, because that was the newest bar there was. Now it has its own.
      this.series?.update(bar as CandlestickData)
      this.repaintMarkers()
      return
    } else return
    this.series?.update(bar as CandlestickData)
  }

  showPosition(p: { entry: number; liquidation: number | null; side: 'long' | 'short' }) {
    this.prices.entry = p.entry
    this.side = p.side
    this.replace('entry', {
      price: p.entry,
      // A draggable entry is an input and looks like one: solid, in the side's
      // colour, labelled. A fixed entry is a record and stays grey and dashed.
      color: this.entryDraggable
        ? p.side === 'long'
          ? this.colors.long
          : this.colors.short
        : this.colors.entry,
      title: this.entryDraggable ? 'LIMIT' : 'entry',
      lineStyle: this.entryDraggable ? 0 : 2,
      kind: this.entryDraggable ? 'entry' : undefined,
    })
    this.prices.liq = p.liquidation
    if (p.liquidation !== null) {
      this.replace('liq', {
        price: p.liquidation,
        color: this.colors.liquidation,
        title: 'liq',
        lineStyle: 1,
      })
    }
  }

  clearPosition() {
    this.prices.entry = null
    this.prices.liq = null
    this.remove('entry')
    this.remove('liq')
  }

  showSLTP(sl: number | null, tp: number | null) {
    this.prices.sl = sl
    this.prices.tp = tp
    if (sl !== null)
      this.replace('sl', { price: sl, color: this.colors.short, title: 'SL', kind: 'sl' })
    else this.remove('sl')
    if (tp !== null)
      this.replace('tp', { price: tp, color: this.colors.long, title: 'TP', kind: 'tp' })
    else this.remove('tp')
  }

  onSLTPDrag(cb: (kind: DragKind, price: number) => void) {
    this.dragCb = cb
  }

  setEntryDraggable(value: boolean) {
    if (value === this.entryDraggable) return
    this.entryDraggable = value
    // Repaint so the line's appearance matches what it now does.
    if (this.prices.entry !== null) {
      this.showPosition({
        entry: this.prices.entry,
        liquidation: null,
        side: this.side,
      })
    }
  }

  resetView() {
    if (!this.chart || !this.series) return
    // Both axes: the time scale is what got scrolled, the price scale is what
    // got locked to the old instrument's range by any manual zoom.
    this.chart.priceScale('right').applyOptions({ autoScale: true })
    this.chart.timeScale().resetTimeScale()
    this.chart.timeScale().scrollToRealTime()
  }

  destroy() {
    this.detachDragHandlers()
    this.chart?.remove()
    this.chart = null
    this.series = null
    this.markerLayer = null
    this.lines = {}
    this.bars = []
    this.markers = []
    this.markerSignature = ''
    this.visible = null
  }

  // --- dragging -----------------------------------------------------------
  // Lightweight Charts has no built-in draggable order line, so this is ours.
  // Grab within GRAB_PX of a line, move, release to commit. The commit fires
  // once on release, not on every pointermove — each change fans out to every
  // connected account, and we are not sending one order per pixel.
  //
  // Three things make the grab actually land, all learned the hard way:
  //
  //  1. The chart pans on the same pointer stream. While a line is held, the
  //     library's own scroll and scale handling is switched off, or the chart
  //     slides under the pointer and the line appears not to move.
  //  2. The grab zone has to be a target, not a hairline. 6px is roughly the
  //     line itself — you had to hit it exactly. It is a band now, and wider
  //     still for a finger.
  //  3. Hovering thickens the line, so it is visible *before* the click that it
  //     is a thing you can grab.

  private static readonly GRAB_PX = 14
  /** Touch has no hover to aim with, so the grab zone is wider for a finger. */
  private static readonly GRAB_PX_TOUCH = 28

  private grabRadius(e: PointerEvent) {
    return e.pointerType === 'touch'
      ? LightweightChartAdapter.GRAB_PX_TOUCH
      : LightweightChartAdapter.GRAB_PX
  }

  /** Colour and label per draggable line, in one place. */
  private lineStyleFor(kind: DragKind) {
    if (kind === 'sl') return { color: this.colors.short, title: 'SL' }
    if (kind === 'tp') return { color: this.colors.long, title: 'TP' }
    return {
      color: this.side === 'long' ? this.colors.long : this.colors.short,
      title: 'LIMIT',
    }
  }

  private paint(kind: DragKind, price: number, state: 'idle' | 'hover' | 'drag') {
    const { color, title } = this.lineStyleFor(kind)
    this.replace(kind, {
      price,
      color,
      title,
      width: state === 'idle' ? 1 : state === 'hover' ? 2 : 3,
      kind,
    })
  }

  /** Freeze the chart's own pan/zoom for the duration of a drag. */
  private setChartInteractive(enabled: boolean) {
    this.chart?.applyOptions({
      handleScroll: enabled ? { vertTouchDrag: false } : false,
      handleScale: enabled,
    })
  }

  private onPointerDown = (e: PointerEvent) => {
    const kind = this.lineNear(e)
    if (!kind) return
    this.dragging = kind
    this.setChartInteractive(false)
    this.el?.setPointerCapture(e.pointerId)
    if (this.el) this.el.style.cursor = 'grabbing'
    const price = this.prices[kind]
    if (price !== null) this.paint(kind, price, 'drag')
    e.preventDefault()
    e.stopPropagation()
  }

  private onPointerMove = (e: PointerEvent) => {
    if (!this.dragging) {
      if (e.pointerType !== 'mouse') return
      // Cursor and line weight both react, so a grabbable line announces itself
      // before the pointer is pressed rather than after a failed attempt.
      const near = this.lineNear(e)
      if (near !== this.hovered) {
        if (this.hovered && this.prices[this.hovered] !== null) {
          this.paint(this.hovered, this.prices[this.hovered] as number, 'idle')
        }
        if (near && this.prices[near] !== null) {
          this.paint(near, this.prices[near] as number, 'hover')
        }
        this.hovered = near
      }
      if (this.el) this.el.style.cursor = near ? 'ns-resize' : 'crosshair'
      return
    }
    const price = this.priceAt(e)
    if (price === null) return
    this.paint(this.dragging, price, 'drag')
    e.preventDefault()
  }

  private onPointerUp = (e: PointerEvent) => {
    if (!this.dragging) return
    const price = this.priceAt(e)
    const kind = this.dragging
    this.dragging = null
    this.hovered = null
    this.setChartInteractive(true)
    this.el?.releasePointerCapture(e.pointerId)
    if (this.el) this.el.style.cursor = 'crosshair'
    if (price !== null) {
      this.prices[kind] = price
      this.paint(kind, price, 'idle')
      this.dragCb?.(kind, price)
    }
  }

  /** A drag that leaves the window must not leave the chart frozen. */
  private onPointerCancel = (e: PointerEvent) => {
    if (!this.dragging) return
    this.onPointerUp(e)
  }

  private priceAt(e: PointerEvent): number | null {
    if (!this.series || !this.el) return null
    const y = e.clientY - this.el.getBoundingClientRect().top
    const price = this.series.coordinateToPrice(y)
    return price === null ? null : Number(price)
  }

  /** The nearest grabbable line under the pointer, or null. */
  private lineNear(e: PointerEvent): DragKind | null {
    if (!this.series || !this.el) return null
    const y = e.clientY - this.el.getBoundingClientRect().top
    const radius = this.grabRadius(e)
    const kinds: DragKind[] = this.entryDraggable ? ['sl', 'tp', 'entry'] : ['sl', 'tp']

    let best: DragKind | null = null
    let bestDistance = radius
    for (const kind of kinds) {
      const price = this.prices[kind]
      if (price === null) continue
      const coord = this.series.priceToCoordinate(price)
      if (coord === null) continue
      const distance = Math.abs(coord - y)
      // Nearest wins: with a 14px band, SL and TP can overlap when they are
      // close together, and grabbing whichever was listed first is a coin toss.
      if (distance <= bestDistance) {
        best = kind
        bestDistance = distance
      }
    }
    return best
  }

  private attachDragHandlers() {
    this.el?.addEventListener('pointerdown', this.onPointerDown)
    this.el?.addEventListener('pointermove', this.onPointerMove)
    this.el?.addEventListener('pointerup', this.onPointerUp)
    this.el?.addEventListener('pointercancel', this.onPointerCancel)
    this.el?.addEventListener('pointerleave', this.onPointerCancel)
  }

  private detachDragHandlers() {
    this.el?.removeEventListener('pointerdown', this.onPointerDown)
    this.el?.removeEventListener('pointermove', this.onPointerMove)
    this.el?.removeEventListener('pointerup', this.onPointerUp)
    this.el?.removeEventListener('pointercancel', this.onPointerCancel)
    this.el?.removeEventListener('pointerleave', this.onPointerCancel)
  }

  // --- price line helpers -------------------------------------------------

  private replace(
    key: keyof typeof this.lines,
    opts: {
      price: number
      color: string
      title: string
      lineStyle?: number
      width?: number
      /** Set when this line is currently draggable — drives the ⇕ affordance. */
      kind?: DragKind
    },
  ) {
    this.remove(key)
    if (!this.series) return
    this.lines[key] = this.series.createPriceLine({
      price: opts.price,
      color: opts.color,
      lineWidth: (opts.width ?? 1) as never,
      lineStyle: (opts.lineStyle ?? 0) as never,
      axisLabelVisible: true,
      // The arrows say "this one moves" on the line itself, which is the only
      // place the admin is looking when they reach for it.
      title: opts.kind ? `⇕ ${opts.title}` : opts.title,
    })
  }

  private remove(key: keyof typeof this.lines) {
    const line = this.lines[key]
    if (line && this.series) this.series.removePriceLine(line)
    delete this.lines[key]
  }
}

export function useChartAdapter(): ChartAdapter {
  // Phase 2: return new ChartingLibraryAdapter() once TradingView grants access.
  return new LightweightChartAdapter()
}
