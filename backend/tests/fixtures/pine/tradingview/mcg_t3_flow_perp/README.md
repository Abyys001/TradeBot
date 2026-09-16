# McG T3 Flow Campaign on the ZEC perpetual — a TradingView year, kept as the reference

Read by `tests/test_tradingview_parity_perp.py` and `tests/test_tvimport.py`.
The script is `../../accept/27_published_strategy.pine`, byte for byte what the
admin runs. The spot fixture next door (`../mcg_t3_flow/`) is the same script on
a different chart; this one exists because it is the **instrument the bot will
actually trade**, and because its Properties tab exercises three things the
other does not: slippage, a hundred dollars of capital, and 100% of equity per
entry, which compounds every sizing error forward instead of damping it.

## What TradingView ran

Exported by the admin on 2026-09-12 from the Strategy Tester, "Last 365 days",
deep backtest.

- **Chart:** Hyperliquid **perpetual** `ZEC/USDC` ("Zcash Perpetual Contract ·
  30 · Hyperliquid"), **30m**. The chart's clock was **UTC+03:30**, which the
  export does not record anywhere — see "The clock" below.
- **Inputs:** the script's defaults, untouched. `Backtest Start` is therefore
  its own `01 Jan 2026 00:00 +1100`, before the window.
- **Properties:** 100 USDC initial capital, **100% of equity** per entry,
  pyramiding 1, commission **0.05%**, **slippage 2 ticks**, leverage ∞ both
  ways, Bar detalization "Default (4 ticks per bar)", Script execution "On bar
  close", limit fills at the requested price, no execution delay.
- **Key stats:** +200.72 USDC (+200.72%), max drawdown 66.11 (31.76%), 70 of 85
  profitable (82.35%), profit factor 2.629.

## The files

| File | What |
|---|---|
| `list_of_trades.tradingview.csv` | The admin's export, byte for byte, Persian filename and all — `docs/TradingView_data/` holds the same bytes beside the screenshots. |
| `list_of_trades.csv` | The same list in UTC, one row per trade, as `apps/bots/tvimport.py` writes it. `test_tvimport.py` regenerates it from the raw file and compares, so the conversion cannot drift into a second source of truth. |
| `bars_hl_perp_zec_30m.csv` | Hyperliquid `candleSnapshot` for `ZEC` 30m, as served — the venue's own precision, nothing rounded, nothing dropped. |

TradingView's own columns for excursion and duration are not carried across:
nothing reads them, and a column in a fixture is a claim the tests do not check.

## The clock

A List of Trades export is stamped in the chart's timezone and never says which
one. Guessing costs everything — at the wrong offset every bar disagrees and the
engine takes the blame — so `tvimport.chart_offset` **derives** it: the script
runs `process_orders_on_close`, so every fill price is some bar's close, and
+03:30 is the only offset of the 105 TradingView offers at which that is true.
It refuses rather than picks when no offset explains the prices, or when two do.

## What is replayed, and what is not

Hyperliquid serves the **latest 5000 bars** and no more, which at 30m is 104
days. That is the venue's own documented limit ("Only the most recent 5000
candles are available"), and its S3 archive does not fill the gap either — it
carries L2 book snapshots and asset contexts, and says in as many words that no
candles are published there. So this is not a fetch that could be written
better. The file therefore starts on **2026-06-04 13:30 UTC**, and **60 of
TradingView's 86 trades are older than any bar this venue will still sell**.
They are kept in `list_of_trades.csv` anyway: they are the record of what the
strategy did over a year, and they become replayable the moment bars for them
exist. `apps/exchanges/candlestore.py` is why that is a question of *when* —
every closed bar the platform sees is archived and never deleted, and
`manage.py import_tradingview` downloads through `backtest.load_bars`, so each
run reaches back at least as far as the last one did. A TradingView chart-data
export of the same series would close the gap today.

The replay starts on **2026-06-19 04:00 UTC**, the first bar inside that history
on which TradingView both closed a campaign and opened one. That matters
because the engine starts flat and TradingView, on this script, never is: begun
anywhere else the engine opens a campaign of its own and every size after that
is a percentage of a different equity. That is the script, not a fault: its
entry is guarded by `strategy.position_size <= 0` (line 302), and
`ta.crossover(flowTrail, flowTrail[2])` fires more than once inside a trend — so
the repeat that TradingView ignores because it is already long is an entry to
anything that is flat. **It is also what a bot going live mid-trend will do**,
which is worth knowing before starting one. Begun on a
reversal, the two start in the same position, on the same bar, at the same
price, from TradingView's own equity — 169.74, which is 100 plus the cumulative
PnL its list prints for everything closed by then.

From there, all **21 closed trades and the one still open** match: side, entry
bar, entry price, exit bar, exit price, quantity to the lot, and PnL to the
cent. The engine's list is longer than TradingView's because it keeps running
past the export.

## Discrepancies, recorded rather than smoothed over

- **The Key stats panel and the trade list disagree with each other**, before
  this platform is involved at all: the panel says +200.72, the list's own
  cumulative column ends at 200.40, and its 86 PnL figures sum to 200.59. The
  last trade was open when the export was taken, so the panel marks it at a
  price the list does not print, and the 19-cent gap between the other two is 86
  rows rounded to cents. The parity test compares trades, not the panel.
- **"2 ticks" is not a fixed distance.** TradingView counts slippage in the
  chart's `mintick`, 0.0001 for this symbol; Hyperliquid quotes to five
  significant figures, so the tick the platform would read off its own listing
  is 0.01 at this price — a hundred times further. The test passes 0.0001
  explicitly, and the backtest report prints the tick beside the count instead
  of "2 tick(s)" alone. Left to the listing it is a different run: measured over
  these 21 trades it books **145.62 against 145.79**, where TradingView printed
  145.80. Small, and not nothing — which is why the backtest form takes the
  chart tick (`chart_tick`, blank meaning the venue's) rather than leaving the
  panel unable to reproduce this file.
- **The last row of the replay is a mark, not a fill.** The replay runs out of
  bars with a position open and books it at the last close with no slippage,
  labelled `end of window`. TradingView leaves its equivalent open. Neither is
  wrong; they are different questions, and the test asserts the difference
  rather than papering over it.
- **The first 60 trades are unverified.** Not "assumed correct" — unverified.
  Ten months of this year's signals have never been compared against anything.

## Regenerating it

```
python manage.py import_tradingview <export.csv> --symbol ZECUSDC --interval 30m \
    --into backend/tests/fixtures/pine/tradingview/mcg_t3_flow_perp
```

The bars come down through the platform's own loader, so they land in the
archive on the way past.
