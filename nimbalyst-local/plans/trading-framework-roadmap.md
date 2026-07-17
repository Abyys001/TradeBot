---
title: Trading Framework Roadmap (Hyperliquid)
status: active
created: 2026-06-24
---

# Trading Framework Roadmap

Goal: not a single bot — a **framework** where many strategies plug in.
Source: user feature spec (8 phases). Below = every feature mapped to current
codebase state so we build gaps, not duplicates.

Legend: ✅ done · 🟡 partial · ⬜ missing

---

## Phase 1 — Core (Must Have)

### Data Management
- ✅ Historical Data Downloader — `history.py` (OHLCV/funding/OI), `/data` panel
- ✅ Incremental Sync — dedup-merge in `candle_store._save_parquet`
- 🟡 Data Validation — basic normalize; no explicit integrity report
- ⬜ Missing Candle Detection — gap scan over stored parquet
- ✅ Local Data Storage — parquet store
- 🟡 Data Compression — parquet default; no tuning
- ✅ Multi-Timeframe Support — interval-keyed store

### Backtesting Engine
- ✅ Candle-Based Backtest — `transpiler/engine.py` + `Backtest` model
- ⬜ Funding Simulation — funding data exists (`load_funding`), not wired to PnL
- ✅ Fee Simulation — `SimBroker.commission`
- ✅ Slippage Simulation — `SimBroker.slippage`
- ⬜ Leverage Simulation — no margin/leverage in sim
- ⬜ Liquidation Simulation — no liq price/forced-close
- 🟡 Multi-Asset Backtesting — per-symbol; no joint portfolio run

### Strategy Engine
- ✅ Plugin strategies — Pine transpiler → runtime; `Strategy` model
- ✅ Signal output LONG/SHORT/CLOSE/HOLD — order_router emits

### Position Management
- 🟡 Open/Close — live order_router; ⬜ Partial Close, Scale In/Out, Move SL/TP

### Risk Management
- 🟡 pre_trade_gate margin check (`exchange/risk.py`)
- ⬜ Fixed Risk · Percentage Risk · Daily Loss Limit · Max Drawdown Protect
- ⬜ Max Open Trades · Max Exposure · Leverage Limits

## Phase 2 — Paper Trading
- ⬜ Paper Account (virtual balance, simulated orders/PnL)
- ⬜ Performance Tracking: Win Rate ✅(backtest only), Profit Factor ⬜,
  Sharpe ⬜, Drawdown ✅(backtest), Avg Trade ⬜, Risk/Reward ⬜

## Phase 3 — Live Trading
- ✅ HL integration place/cancel/leverage (`hl_client`, `order_router` live)
- 🟡 Order types: Market/Limit ✅; Stop Market/Stop Limit/TP ⬜
- 🟡 Position monitoring: realtime PnL ✅; liq price ⬜, margin usage 🟡,
  funding cost ⬜

## Phase 4 — Optimization
- ⬜ Parameter Optimization (grid sweep)
- ⬜ Walk-Forward Testing
- ⬜ Monte Carlo Simulation

## Phase 5 — Portfolio Management
- ⬜ Multi-Asset concurrent run
- ⬜ Portfolio metrics: exposure, correlation, drawdown, Sharpe

## Phase 6 — AI
- ⬜ AI Signal Engine (price/volume/funding/OI → LONG/SHORT/NO TRADE)
- ⬜ Market Regime Detection (trend/range/vol)

## Phase 7 — Dashboards
- 🟡 Trading dashboard (equity curve ⬜, positions ✅, trades ✅, PnL ✅)
- ⬜ Analytics dashboard (best/worst strat, monthly perf, funding cost, win by asset)

## Phase 8 — Pro Features
- ⬜ Strategy Marketplace (package per strategy)
- 🟡 Strategy Versioning (Strategy.source exists; no version chain)
- ⬜ Event Replay (TradingView-style)
- 🟡 Visual Backtest (chart markers exist; no SL/TP overlay)
- ⬜ Journal System (entry/exit reason, screenshot, result)

---

## Build order (user priority)

1. **Backtest realism**: funding sim + leverage + liquidation + richer metrics
   (Sharpe, profit factor, avg trade, R:R) — biggest leverage, data already local.
2. **Risk Manager**: config model + gates (%-risk, daily loss, max DD, max open,
   max exposure, leverage cap) — shared by backtest/paper/live.
3. **Paper Trading**: virtual account reusing SimBroker + live feed.
4. **Performance/Analytics**: metrics module + dashboard.
5. **Optimizer**: grid → walk-forward → monte carlo.
6. **Portfolio**, **AI**, **Pro** features.

Each slice = own plan doc + migration + tests, no architecture rewrite.
