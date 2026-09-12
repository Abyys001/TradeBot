# McG T3 Flow Campaign — a TradingView run, kept as the reference

Read by `tests/test_tradingview_parity.py`. The script is
`../../accept/27_published_strategy.pine`, byte for byte what the admin runs.

## What TradingView ran

Exported by the admin on 2026-09-12 from the Strategy Tester.

- **Chart:** Hyperliquid *spot* `UZEC/USDC` ("Zcash / USDC · Hyperliquid" — no
  "Perpetual"), **30m**, chart timezone **UTC**. Hyperliquid's API calls the
  pair `@272`. The perpetual `ZEC` is a different series: 1001.2 against
  1002.7 for the same bar's low.
- **Inputs:** the script's defaults, apart from Backtest Start = 2026-03-01 13:00.
- **Properties:** 100,000 USDC, 30% of equity, pyramiding 0, commission 0.05%,
  slippage 0, leverage ∞, Bar detalization "Default (4 ticks per bar)" (the
  magnifier off), Script execution "On bar close" (every-tick off).
- **Summary:** 59 closed trades, 46 winners (77.97%), gross profit 52,052.82,
  gross loss 23,642.30, profit factor 2.202, max drawdown 10,522.50 (9.67%).

## `list_of_trades.csv`

One row per TradingView trade — each TP1/TP2/TP3 slice is its own row. Times
are the fill bar's **open**, UTC. Row 60 is still open.

The admin's original is `docs/ScreenShots/trades_1_to_60.csv`. Its "Duration"
column is the quantity (qty × entry = the "Position Size" beside it), and it
rounds that to two decimals. **Twelve rows had their exit columns shifted one
row down** (rows 1, 32–33, 44–47, 56–60): row 32 claims a short opened and
closed at 571.0 on the same bar, for +1106.27. They were rebuilt from the
columns that are internally consistent — side, entry, quantity and PnL — using
the 0.05% commission on both sides:

    exit = (pnl / qty + s·entry + c·entry) / (s − c)      s = ±1, c = 0.0005

Every rebuilt price lands within 0.05 of a price the list prints elsewhere, and
takes that row's time. The chart screenshots agree: row 32 is "Short TP1
+16.9772" on 2026-05-30.

## `bars_hl_spot_uzec_30m.csv`

Hyperliquid `candleSnapshot` for `@272` 30m, as served — **not** rounded, and
with the venue's filler bars left in, because dropping those and rounding to
TradingView's tick is what the test proves `backtest.run` does:

- **33 flat zero-volume candles** for slots in which nothing traded.
  TradingView has no bar there. Replayed, they shift every `x[2]` and drag the
  ATR, and moved the 2026-08-11 reversal a bar early.
- Prices at the venue's precision (465.46); TradingView's bars are at the
  chart's 0.1 tick, rounded half-up (498.25 → 498.3).

The venue keeps 5000 bars, so the file starts on 2026-05-31 12:00; the 39
trades before 2026-06-19 cannot be replayed from it.

## Indicator values TradingView showed

The legend under the cursor in the screenshots, for anyone extending this to
the plots (ATR Signal Trail, Selected Engine Basis), one decimal:

| Bar (UTC)        | Trail | Basis |
|------------------|-------|-------|
| 2026-06-17 18:00 | 476.1 | 484.4 |
| 2026-07-08 18:00 | 457.7 | 463.4 |
| 2026-08-10 04:30 | 507.5 | 510.8 |
| 2026-09-04 09:00 | 849.9 | 865.8 |
