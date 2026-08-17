# TP/SL Enforcement & Close Position Verification

## Problem

Three gaps in the current TP/SL and close-position lifecycle:

1. **Chart lines after trade entry** — TP/SL lines are drawn from the `order` store percentages, but need verification that they persist and show correct server-side values after fill.
2. **No panel-level TP/SL enforcement** — TP/SL are delegated entirely to exchange-side conditional orders. If an exchange fails to place them, or they get cancelled, the position is unprotected. The panel has no redundant safety net.
3. **Close position correctness unverified** — Each adapter's `close_position` needs audit against the exchange's actual API documentation.

## Design

### 1. Chart TP/SL Lines After Trade Entry

**Current flow:** `chart.vue` calls `syncChartLines()` which reads `order.priceFor('sl')` and `order.priceFor('tp')`. These depend on `order.slPct`/`order.tpPct` + `order.entryPrice`. After a trade fills, `order.hydrateFromTrade(trade)` should restore state from the server.

**Verification:** Trace the data flow from `route_open()` → `_persist_open()` → WebSocket `leg_result` → `positions.load()` → `order.hydrateFromTrade()` → `syncChartLines()`. Fix any gaps where the chart doesn't reflect the server-side SL/TP.

**Key check:** `hydrateFromTrade()` must set `slPct`, `tpPct`, `entryPrice`, `basis`, `leverage`, and `side` from the trade data so `priceFor()` computes the correct absolute prices.

### 2. Panel-Level TP/SL Enforcement (PriceGuard)

A server-side price monitor that acts as a redundant safety net alongside exchange-side orders.

**Architecture:**

```
StreamHub (existing candle WebSocket) → PriceGuard → route_close() → fan_out(close_position)
```

**Components:**

- **`apps/trading/price_guard.py`** — The PriceGuard class:
  - Maintains a dict of active guards: `{symbol: TradeGuard}` where `TradeGuard` holds `trade_id`, `side`, `stop_loss` (Decimal), `take_profit` (Decimal), `accounts` (adapter list)
  - `register(trade_id, symbol, side, sl, tp, accounts)` — called after trade fill
  - `unregister(trade_id)` — called when trade closes
  - `on_bar(symbol, bar)` — called by StreamHub on each candle update; checks high/low against SL/TP
  - `check_and_close(symbol, trigger_type)` — fans out `close_trade()` and sends notification

**Trigger logic (per candle OHLCV):**

| Position Side | Condition | Action |
|---|---|---|
| LONG | `bar.low <= stop_loss` | Close all accounts |
| LONG | `bar.high >= take_profit` | Close all accounts |
| SHORT | `bar.high >= stop_loss` | Close all accounts |
| SHORT | `bar.low <= take_profit` | Close all accounts |

**Registration points:**
- **Register:** In `_persist_open()` after the Trade row is created, register with PriceGuard
- **Unregister:** In `route_close()` after fan-out completes, and in `_close_trade_callback` when trade status changes to CLOSED

**Integration with StreamHub:**
- PriceGuard hooks into `streamhub.py`'s bar delivery — when a bar arrives for a symbol with an active guard, call `guard.on_bar(symbol, bar)`
- Uses the same candle data the chart already receives — no new WebSocket connections

**Detection latency caveat:** PriceGuard checks on candle updates from StreamHub. Exchange kline streams push updates on every trade (intra-candle), so the guard sees high/low as the candle forms — not just at close. However, if the stream delivers only completed candles, detection is delayed by the candle interval. This is acceptable for a redundant safety net: exchange-side conditional orders handle real-time enforcement; PriceGuard catches cases where those orders fail or were never placed.

**Coexistence with exchange-side orders:**
- Exchange fires its conditional order → position closes → PriceGuard's next `on_bar` finds no position (or `route_close` sees no open trade) → no-op
- Exchange fails → PriceGuard fires → position closes → notification sent
- Race condition (both fire simultaneously): `close_trade()` fans out to all adapters; adapters that already closed raise `AdapterError("no open position")` → caught and ignored per adapter

**Edge cases:**
- **Partial TP/SL:** If only some legs have SL/TP attached (sltp_verified=False on some), PriceGuard still closes ALL accounts — spec §4 says one account's failure must not block another
- **Kill switch:** PriceGuard's `route_close()` passes `respect_stop_all=False` — same as the close button, closing must work while halted
- **Multiple guards on same symbol:** Only one trade per account at a time (spec §6), so at most one guard per symbol
- **Guard survives tab close:** Runs server-side in the ASGI process; if the process restarts, guards are lost but exchange-side orders remain active

### 3. Close Position Audit

Verify each adapter's `close_position` against exchange API docs:

| Adapter | Endpoint | Verification |
|---|---|---|
| Binance | `POST /fapi/v1/order` | hedge mode `positionSide` vs one-way `reduceOnly`, `newOrderRespType: RESULT` for fill data |
| Toobit | `POST /api/v1/futures/flashClose` | side is position side (LONG/SHORT), not order side; no quantity param |
| Bybit | `POST /v5/order/create` | `category: linear`, `reduceOnly: true`, Market order type |
| OKX | `POST /api/v5/trade/close-position` | dedicated endpoint, `mgnMode: cross`, `autoCxl: true`, no side/qty needed |
| Gate.io | `POST /api/v4/futures/usdt/orders` | `close: true`, `size: 0`, `tif: ioc`, `price: "0"` |
| KuCoin | `POST /api/v1/orders` | `closeOrder: true`, no size, `_fill` readback for fill data |
| Hyperliquid | SDK `order` | IOC limit 5% crossing, `reduce_only=True`, parse `statuses` array |
| LBank | `POST /v2/supplement/create_order.do` | spot-only, `sell_market`, amount = min(filled, free_balance) |
| Paper | in-memory | no exchange, clears position + SL/TP state |

Cross-reference against vendored docs in `reference/` and Hyperliquid MCP server.

## Testing

- **Unit tests for PriceGuard:** Register guard, simulate candle that crosses SL → verify `close_trade` called. Simulate candle that doesn't cross → no-op. Unregister → no more checks.
- **Integration test:** Paper adapter + PriceGuard → open trade, push bar that crosses SL → verify position closed
- **Chart line test:** Open trade via paper adapter → verify `hydrateFromTrade` correctly restores `slPct`/`tpPct` → verify chart shows correct lines

## Files to Create/Modify

| File | Action |
|---|---|
| `apps/trading/price_guard.py` | **Create** — PriceGuard class |
| `apps/trading/streamhub.py` | **Modify** — hook PriceGuard into bar delivery |
| `apps/trading/services.py` | **Modify** — register/unregister guard on trade open/close |
| `apps/trading/executor.py` | **Modify** — unregister guard on close_trade |
| `apps/trading/test_price_guard.py` | **Create** — unit tests |
| `frontend/composables/useChartAdapter.ts` | **Verify** — ensure showSLTP works after trade entry |
| `frontend/stores/order.ts` | **Verify** — ensure hydrateFromTrade restores correctly |
| All exchange adapters | **Audit** — verify close_position per exchange docs |
