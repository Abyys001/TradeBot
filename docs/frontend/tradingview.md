# TradingView charts — setup

Spec §3 requires a TradingView chart where SL/TP lines can be **dragged**, plus
visual indicator editing on the panel. There is no Charting Library access
today (`questions.md` Q3), so this is a two-phase plan behind one interface.

## Which TradingView product does what

TradingView ships three different things and only two of them are usable here.

| Product | Cost | Draggable SL/TP? | Indicators / drawing tools | Custom data feed |
|---|---|---|---|---|
| **Embed widget** (`s3.tradingview.com/tv.js`) | free, no signup | ❌ it is an iframe — no DOM access, no price-scale access | built-in, but not controllable from our code | ❌ TradingView's data only |
| **Lightweight Charts** | free, Apache-2.0, npm | ✅ via price lines + our own drag handling | ❌ none built in — we implement them | ✅ our data |
| **Charting Library** ("Advanced Charts") | free, but **application required** | ✅ native order lines | ✅ full suite + drawing toolbar | ✅ our data |

The embed widget is ruled out: an iframe cannot expose the pixel↔price mapping,
so a stop line cannot be drawn on it, let alone dragged. It would satisfy "show
a chart" and none of the rest of spec §3.

## Phase 1 — Lightweight Charts (build on this now)

```bash
npm i lightweight-charts
```

No application, no license key, no account. It renders our own candles from our
own backend, which we need anyway — the chart must show the *admin's* positions
across exchanges, not a generic symbol feed.

What we implement on top:

- **Draggable SL/TP**: `createPriceLine()` renders the line;
  `series.coordinateToPrice()` / `priceToCoordinate()` convert pointer Y ↔ price.
  Drag handling is ours: pointerdown near the line → capture → move → on release,
  emit the new price to the order store.
- **Indicators**: computed in a composable (`useIndicators`) and drawn as extra
  line series / histogram series. Starter set: MA, EMA, RSI, MACD, Bollinger.
  RSI and MACD go in a separate pane below the price pane.
- **Position overlays**: entry line, liquidation line, and the SL/TP pair, each
  a `PriceLine` with its own colour and title.

Limits to accept in phase 1: no drawing toolbar (trendlines, fib), no
indicator-on-indicator, no saved chart layouts. If the admin needs those before
phase 2, they can be done in a TradingView tab side-by-side.

## Where the candles come from

`GET /api/trading/market/candles/` and `/market/ticker/`, served by
`backend/apps/exchanges/marketdata.py` — a public, **credential-free** module
that is deliberately not an adapter (see Q13 in `questions.md`). Providers are
tried in order (Binance, then Bybit); a provider that fails is skipped for 60s
rather than costing every request its timeout.

The frontend side is `stores/market.ts`: one poll loop for the whole page,
candles every 15s and the ticker every 3s, with the tick folded into the current
bar so the chart moves between fetches. Nothing here shares a budget with the
one-second fan-out — this is a chart, not the order path.

**Every candle came from an exchange.** When no provider answers, the API
returns 503; there is no synthetic series behind the panel. `market.feedDown`
drives an explicit "no price feed" state and `SymbolBar.vue` says so next to the
price. Any future chart adapter has to keep that property: a chart that invents
bars is how someone reads a price that never existed. The same rule holds on the
routing side — with no feed there is no reference price, so nothing sizes.

**The view belongs to the admin.** Nothing pans, zooms or re-fits the chart on
its own. `resetView()` runs when the instrument changes and when the admin
presses the button in the chart's top-right corner — never on a data refresh,
which is what used to yank the chart back to the newest bar every 15 seconds.

**What the chart draws.** Only the lines the admin acts on: SL, TP, and a
working limit order's entry, plus the liquidation line once a position exists.
The live price is an axis label (`priceLineVisible: false`), and the candle
countdown sits in the corner. Four lines inside one narrow price band is how a
drag lands on the wrong one.

## Phase 2 — Charting Library (apply today)

Apply at **https://www.tradingview.com/advanced-charts/**. It is free but
access-gated: submit the form, agree to their terms, and they grant access to a
private GitHub repo. **Approval is days-to-weeks of external lead time, so the
application should go in now, not when phase 1 finishes.**

Once granted:

1. Clone their private repo, copy `charting_library/` and `datafeeds/` into
   `frontend/public/` (it is not on npm and must not be committed to a public
   repo — their license forbids redistribution).
2. Implement the **UDF datafeed** interface against our backend:
   `onReady`, `resolveSymbol`, `getBars`, `subscribeBars`, `searchSymbols`.
3. Order lines come free: `chart.createOrderLine().onMove(...)` gives native
   dragging, which replaces our hand-rolled drag code.
4. Indicators and drawing tools come free — delete the `useIndicators` fallback.

## The interface that makes the swap cheap

Everything above the chart talks to one adapter, so phase 2 is a swap, not a
rewrite:

```ts
interface ChartAdapter {
  mount(el: HTMLElement, symbol: string, interval: string): Promise<void>
  setCandles(bars: Bar[]): void
  appendCandle(bar: Bar): void
  showPosition(p: { entry: number; liquidation: number; side: 'long' | 'short' }): void
  showSLTP(sl: number | null, tp: number | null): void
  onSLTPDrag(cb: (kind: 'sl' | 'tp', price: number) => void): void
  addIndicator(name: IndicatorName, params: Record<string, number>): string
  removeIndicator(id: string): void
  destroy(): void
}
```

`LightweightChartAdapter` now, `ChartingLibraryAdapter` later. The order store,
the SL/TP fan-out, and the positions panel never learn which one is mounted.

## SL/TP editing must work in three places (spec §3)

The chart is only one of them. All three write to the same store action, and
that action is what triggers the fan-out:

1. Order-entry ticket (before entry).
2. Chart drag (this document).
3. Position row under the chart.

Whichever surface changes it, the other two re-render from the store, and one
`amendSLTP` command goes to the execution engine.
