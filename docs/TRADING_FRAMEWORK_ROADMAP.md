# Trading Framework Roadmap — Hyperliquid

Living document for the TradeBot algorithmic trading framework.

**Build order:** Data → Backtest → Strategy → Risk → Paper → Live → Dashboard → Optimizer → AI

Legend: ✅ done · 🟡 partial · ⬜ missing

---

## Phase 1 — Core

### Data Management
| Feature | Status | Code |
|---------|--------|------|
| Historical Downloader | ✅ | `apps/exchange/history_download.py` |
| Incremental Sync | ✅ | `history_download._effective_start_ms` |
| PG + Parquet storage | ✅ | `apps/exchange/candle_store.py` |
| Multi-timeframe | ✅ | interval-keyed store |
| Data validation | ✅ | `apps/exchange/data_quality.py` |
| Gap detection | ✅ | `GET /api/history/gaps/` |
| Network isolation | ✅ | `candle_path(network/...)` |

### Backtesting
| Feature | Status | Code |
|---------|--------|------|
| Candle backtest | ✅ | `apps/transpiler/engine.py` |
| Fee + slippage | ✅ | `SimBroker` |
| Funding simulation | ✅ | `SimBroker.apply_funding` |
| Leverage + margin | ✅ | `SimBroker` leverage param |
| Liquidation | ✅ | `SimBroker.check_liquidation` |
| SL/TP intrabar | ✅ | `SimBroker.check_stops` |
| Partial close / pyramiding | ✅ | `close(qty_pct=)`, `allow_pyramiding` |
| Rich metrics | ✅ | `apps/transpiler/metrics.py` |

### Strategy Engine
| Feature | Status | Code |
|---------|--------|------|
| Pine transpiler | ✅ | `apps/transpiler/` |
| Plugin registry | ✅ | `apps/strategies/plugins/` |
| Signal bus | ✅ | `apps/strategies/signals.py` |

### Risk Management
| Feature | Status | Code |
|---------|--------|------|
| Config schema | ✅ | `apps/risk/config.py` |
| Gates (backtest/paper/live) | ✅ | `apps/risk/manager.py` |
| Position sizing | ✅ | `apps/risk/sizing.py` |

---

## Phase 2 — Paper Trading
| Feature | Status | Code |
|---------|--------|------|
| Paper account | ✅ | `apps/paper/models.py` |
| Paper broker | ✅ | `apps/paper/broker.py` |
| Live feed wire | ✅ | `apps/paper/tasks.py` |
| Paper UI | ✅ | `frontend/src/modules/paper/` |

---

## Phase 3 — Live Trading
| Feature | Status | Code |
|---------|--------|------|
| HL orders | ✅ | `LiveBroker` |
| Risk enforcement | ✅ | `apps/risk/manager.py` + `LiveBroker` |
| Leverage API | ✅ | `hl_client.update_leverage` |
| Positions UI | ✅ | `PositionsPanel.vue` |

---

## Phase 4 — Optimization
| Feature | Status | Code |
|---------|--------|------|
| Grid search | ✅ | `apps/optimizer/grid.py` |
| Walk-forward | ✅ | `apps/optimizer/walk_forward.py` |
| Monte Carlo | ✅ | `apps/optimizer/monte_carlo.py` |

---

## Phase 5 — Portfolio
| Feature | Status | Code |
|---------|--------|------|
| Portfolio backtest | ✅ | `apps/optimizer/portfolio.py` |

---

## Phase 6 — AI
| Feature | Status | Code |
|---------|--------|------|
| Rule-based signal engine | ✅ | `apps/strategies/plugins/ai.py` |
| Regime detection | ✅ | `apps/strategies/ai_regime.py` |

---

## Phase 7 — Dashboard
| Feature | Status | Code |
|---------|--------|------|
| Overview | ✅ | `OverviewView.vue` |
| Equity curve | ✅ | `EquityCurve.vue` |
| Analytics | ✅ | `AnalyticsView.vue` |
| Visual backtest SL/TP | ✅ | `TradingChart.vue` markers |

---

## Phase 8 — Pro
| Feature | Status | Code |
|---------|--------|------|
| Strategy versioning | ✅ | `apps/pro/models.py` — `StrategyVersion` |
| Event replay | ✅ | `apps/pro/models.py` — `ReplaySession` |
| Trade journal | ✅ | `apps/pro/models.py` — `TradeJournal` |
| Marketplace | ✅ | `apps/pro/models.py` — `MarketplacePackage` |

---

## Sprint acceptance criteria

### S1.1 Data Quality
- `GET /api/history/gaps/?coin=BTC&interval=1h` returns gap list
- StoredDataTable shows healthy/unhealthy badge

### S1.2 Backtest Realism
- Backtest with `leverage=5` and funding series applies funding PnL
- Liquidation forces close when margin breached

### S1.3 Metrics
- Backtest metrics include sharpe_ratio, profit_factor, avg_trade, risk_reward
- equity_series stored on Backtest row

### S1.5 Risk Manager
- `max_daily_loss_pct` blocks new entries after daily loss exceeded

### M2 Paper
- Strategy runs on live feed without credential; virtual balance updates

---

## Quick start

```bash
docker compose up -d postgres redis web celery celery-beat frontend market-feed candle-consumer
docker compose exec web python manage.py migrate
```

- `/data` — download history
- `/strategies/:id` — backtest / paper / live tabs
- `/analytics` — performance dashboard
