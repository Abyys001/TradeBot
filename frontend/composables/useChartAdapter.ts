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
 */
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type IPriceLine,
  type CandlestickData,
  type Time,
} from 'lightweight-charts'

export type Bar = { time: Time; open: number; high: number; low: number; close: number }
/** Every line the admin can grab. `entry` is draggable only for a limit order. */
export type DragKind = 'sl' | 'tp' | 'entry'
export type SLTPKind = DragKind

export interface ChartAdapter {
  mount(el: HTMLElement): Promise<void>
  setCandles(bars: Bar[]): void
  appendCandle(bar: Bar): void
  showPosition(p: { entry: number; liquidation: number | null; side: 'long' | 'short' }): void
  showSLTP(sl: number | null, tp: number | null): void
  /** The live mark. Distinct from entry: one is where we got in, one is now. */
  showMark(price: number | null): void
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

function palette() {
  return {
    long: tokenColor('--c-long', '#3BC9D8'),
    short: tokenColor('--c-short', '#FF6B81'),
    entry: tokenColor('--c-ink-muted', '#8B94A3'),
    liquidation: tokenColor('--c-signal', '#F0A020'),
    mark: tokenColor('--c-brand', '#5B8DEF'),
    grid: tokenColor('--c-chart-grid', '#1E232B'),
    text: tokenColor('--c-ink-muted', '#8B94A3'),
  }
}

export class LightweightChartAdapter implements ChartAdapter {
  private chart: IChartApi | null = null
  private series: ISeriesApi<'Candlestick'> | null = null
  private lines: Partial<Record<'sl' | 'tp' | 'entry' | 'liq' | 'mark', IPriceLine>> = {}
  private dragCb: ((kind: DragKind, price: number) => void) | null = null
  private dragging: DragKind | null = null
  private hovered: DragKind | null = null
  private el: HTMLElement | null = null
  private prices: { sl: number | null; tp: number | null; entry: number | null } = {
    sl: null,
    tp: null,
    entry: null,
  }
  private entryDraggable = false
  private side: 'long' | 'short' = 'long'
  private colors = palette()

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
    this.series = this.chart.addCandlestickSeries({
      upColor: this.colors.long,
      downColor: this.colors.short,
      wickUpColor: this.colors.long,
      wickDownColor: this.colors.short,
      borderVisible: false,
    })
    this.attachDragHandlers()
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
  }

  setCandles(bars: Bar[]) {
    this.series?.setData(bars as CandlestickData[])
  }

  /** True while a line is held, so callers can suppress conflicting repaints. */
  get isDragging() {
    return this.dragging !== null
  }

  appendCandle(bar: Bar) {
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
    if (p.liquidation !== null) {
      this.replace('liq', {
        price: p.liquidation,
        color: this.colors.liquidation,
        title: 'liq',
        lineStyle: 1,
      })
    }
  }

  showMark(price: number | null) {
    if (price === null) {
      this.remove('mark')
      return
    }
    this.replace('mark', {
      price,
      color: this.colors.mark,
      title: 'mark',
      lineStyle: 3,
    })
  }

  clearPosition() {
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
    this.lines = {}
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
