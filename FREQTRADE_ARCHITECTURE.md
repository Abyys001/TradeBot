# Freqtrade Complete Architecture & Codebase Analysis

> **Version**: 2026.7-dev (Python 3.11+ | GPLv3)
> **Generated**: July 2026
> **Purpose**: Exhaustive documentation of every subsystem, designed as a reference for building a custom high-frequency trading bot targeting Tabdeal Futures API (FAPI).

---

## Table of Contents

1. [Executive Overview & Core Philosophy](#1-executive-overview--core-philosophy)
2. [Directory Structure & Module Map](#2-directory-structure--module-map)
3. [Entry Points & CLI System](#3-entry-points--cli-system)
4. [The Trading Engine (Worker + FreqtradeBot)](#4-the-trading-engine-worker--freqtradbot)
5. [Strategy Framework (IStrategy)](#5-strategy-framework-istrategy)
6. [Data Layer & Market Data Pipeline](#6-data-layer--market-data-pipeline)
7. [Exchange Abstraction Layer](#7-exchange-abstraction-layer)
8. [Risk Management & Stoploss](#8-risk-management--stoploss)
9. [Position Sizing & Wallet Management](#9-position-sizing--wallet-management)
10. [Backtesting Engine](#10-backtesting-engine)
11. [Hyperparameter Optimization (Hyperopt)](#11-hyperparameter-optimization-hyperopt)
12. [UI, API & RPC Layer](#12-ui-api--rpc-layer)
13. [Telegram Bot Integration](#13-telegram-bot-integration)
14. [Persistence & Database](#14-persistence--database)
15. [Plugin System](#15-plugin-system)
16. [FreqAI: Machine Learning Module](#16-freqai-machine-learning-module)
17. [Configuration System](#17-configuration-system)
18. [Dependencies & Tech Stack](#18-dependencies--tech-stack)
19. [Gap Analysis: Freqtrade vs Custom Tabdeal Bot Requirements](#19-gap-analysis-freqtrade-vs-custom-tabdeal-bot-requirements)
20. [What to Borrow vs What to Build Fresh](#20-what-to-borrow-vs-what-to-build-fresh)
21. [Recommendations for Custom Build](#21-recommendations-for-custom-build)

---

## 1. Executive Overview & Core Philosophy

### What is Freqtrade?

Freqtrade is a free, open-source cryptocurrency trading bot written in Python. It supports:

- **Trading modes**: Spot, margin (cross/isolated), and futures
- **20+ exchanges** via CCXT (Binance, Bybit, OKX, Kraken, Gate, Bitget, Hyperliquid, etc.)
- **Automated strategy execution** with custom Python strategies
- **Backtesting** against historical data with high fidelity
- **Hyperparameter optimization** using Optuna
- **Machine learning strategies** via FreqAI (LightGBM, XGBoost, PyTorch, reinforcement learning)
- **Multiple control interfaces**: CLI, Telegram bot, REST API, WebSocket, FreqUI (Vue.js web dashboard)

### Core Architecture Philosophy

Freqtrade follows a **monolithic-but-modular** design:

```
┌─────────────────────────────────────────────────────────┐
│                    CLI (argparse)                         │
├─────────────────────────────────────────────────────────┤
│                     Worker (state machine)                │
├─────────────────────────────────────────────────────────┤
│                  FreqtradeBot (core engine)               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Strategy │  │ Exchange │  │ Data     │  │ Wallets│ │
│  │ Interface│  │ (CCXT)   │  │ Provider │  │        │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘ │
├─────────────────────────────────────────────────────────┤
│                  Persistence (SQLAlchemy)                 │
├─────────────────────────────────────────────────────────┤
│            RPC Layer (Telegram | REST API | WS)          │
├─────────────────────────────────────────────────────────┤
│              Plugins (Pairlists | Protections)           │
└─────────────────────────────────────────────────────────┘
```

**Key design patterns used throughout**:
- **Abstract Base Classes** (ABC) for extensibility (IStrategy, IPairList, IProtection, IDataHandler)
- **Resolver pattern** for dynamic plugin loading from filesystem
- **Chain of Responsibility** for pairlist filter pipelines
- **Middleware pattern** for persistence abstraction (DB vs in-memory)
- **Observer/Broadcast** pattern for RPC notifications
- **State Machine** for bot lifecycle management

---

## 2. Directory Structure & Module Map

### Top-Level Layout

```
freqtrade/
├── freqtrade/                    # Core Python package (31 submodules)
│   ├── main.py                   # Root entry point
│   ├── worker.py                 # Main event loop (state machine)
│   ├── freqtradebot.py           # Core trading engine (~2665 lines)
│   ├── wallets.py                # Balance & position tracking
│   ├── constants.py              # Project-wide constants
│   ├── exceptions.py             # Exception hierarchy
│   ├── misc.py                   # Miscellaneous helpers
│   ├── commands/                 # CLI subcommands (30+ commands)
│   ├── exchange/                 # Exchange abstraction (31 files, ~4157 lines base)
│   ├── strategy/                 # Strategy framework (9 files)
│   ├── optimize/                 # Backtesting + Hyperopt (10 entries)
│   ├── freqai/                   # Machine learning module (10 entries)
│   ├── data/                     # Data management (7 files)
│   ├── persistence/              # Database/ORM (12 files)
│   ├── rpc/                      # RPC + API server (10 entries)
│   ├── plugins/                  # Pairlists + Protections
│   ├── configuration/            # Config loading & validation
│   ├── resolvers/                # Dynamic class loading
│   ├── leverage/                 # Leverage & margin calculations
│   ├── templates/                # Strategy/config templates
│   ├── enums/                    # All enumerations (15 files)
│   ├── util/                     # Utilities (15 files)
│   ├── loggers/                  # Logging setup (7 files)
│   ├── config_schema/            # JSON Schema for validation
│   ├── system/                   # System setup (asyncio, GC, multiprocessing)
│   ├── ft_types/                 # Custom type definitions
│   ├── mixins/                   # Logging mixin
│   └── vendor/                   # Vendored code (qtpylib)
├── ft_client/                    # Separate REST API client package
├── tests/                        # Comprehensive test suite
├── config_examples/              # Example configurations
├── user_data/                    # Runtime data (backtest results, OHLCV, logs)
├── docs/                         # MkDocs documentation sources
├── docker/                       # Specialized Dockerfiles
├── build_helpers/                # CI/CD utilities
├── scripts/                      # Utility scripts
├── pyproject.toml                # Package metadata & dependencies
├── requirements.txt              # Production dependencies (63 lines)
├── Dockerfile                    # Multi-stage build (python:3.14-slim)
├── docker-compose.yml            # Production compose
├── setup.sh / setup.ps1          # Installation scripts
└── freqtrade.service             # systemd service unit
```

### The 31 Core Submodules

| Module | Files | Purpose |
|--------|-------|---------|
| `exchange/` | 31 | Exchange abstraction via CCXT, per-exchange subclasses, WebSocket |
| `strategy/` | 9 | Strategy base class, hyperopt parameters, informative decorator |
| `optimize/` | 10 | Backtesting engine, hyperopt (Optuna), loss functions, reports |
| `freqai/` | 10 | ML models (LightGBM, XGBoost, PyTorch, RL), data kitchen |
| `data/` | 7 | OHLCV download/storage, DataProvider, converter, metrics |
| `persistence/` | 12 | SQLAlchemy ORM (trades, orders, locks, custom data, wallets) |
| `rpc/` | 10 | Telegram, REST API (FastAPI), WebSocket, webhooks, Discord |
| `plugins/` | 5+ | Pairlist handlers (22), protection handlers (4) |
| `configuration/` | 12 | Config loading, merging, validation, env var overrides |
| `resolvers/` | 8 | Dynamic class loading for strategies, exchanges, plugins |
| `commands/` | 20+ | CLI subcommands for all operations |
| `enums/` | 15 | State, TradingMode, ExitType, CandleType, SignalDirection, etc. |
| `util/` | 15 | Datetime, formatters, caching, progress, CoinGecko |
| `loggers/` | 7 | Rich console, JSON formatter, Telegram buffer |
| `templates/` | 10 | Sample strategies, configs, Jupyter notebooks |
| `leverage/` | 3 | Liquidation price, interest calculations |
| `system/` | 5 | asyncio setup, GC tuning, version display |
| `config_schema/` | 2 | JSON Schema generation for config validation |
| `ft_types/` | 4 | Backtest result types, plot types |
| `mixins/` | 2 | Logging mixin for spam prevention |
| `vendor/` | 2 | Vendored qtpylib (quantitative helpers) |

---

## 3. Entry Points & CLI System

### Primary Entry Point

Defined in `pyproject.toml`:
```
freqtrade = "freqtrade.main:main"
```

Execution flow:
1. `freqtrade/main.py:main()` — sets up logging, asyncio event loop, parses CLI args
2. `freqtrade/commands/Arguments` — argparse-based routing to 30+ subcommand handlers
3. Each subcommand maps to a dedicated module in `freqtrade/commands/`

### Key CLI Commands

| Command | Handler File | Function |
|---------|-------------|----------|
| `freqtrade trade` | `trade_commands.py` | **Primary** — creates `Worker`, calls `worker.run()` |
| `freqtrade backtesting` | `optimize_commands.py` | Runs backtest against historical data |
| `freqtrade hyperopt` | `optimize_commands.py` | Hyperparameter optimization |
| `freqtrade download-data` | `data_commands.py` | Downloads historical OHLCV |
| `freqtrade new-config` | `build_config_commands.py` | Interactive config builder |
| `freqtrade new-strategy` | `deploy_commands.py` | Creates strategy template |
| `freqtrade install-ui` | `deploy_commands.py` | Installs FreqUI web dashboard |
| `freqtrade list-exchanges` | `list_commands.py` | Lists supported exchanges |
| `freqtrade list-strategies` | `list_commands.py` | Lists available strategies |
| `freqtrade webserver` | `webserver_commands.py` | Standalone API server mode |
| `freqtrade convert-db` | `db_commands.py` | Database migration |
| `freqtrade plot-dataframe` | `plot_commands.py` | Strategy visualization |
| `freqtrade lookahead-analysis` | `optimize_commands.py` | Lookahead bias detection |
| `freqtrade recursive-analysis` | `optimize_commands.py` | Recursive feature analysis |
| `freqtrade test-pairlist` | `pairlist_commands.py` | Tests pairlist configuration |

---

## 4. The Trading Engine (Worker + FreqtradeBot)

### 4.1 The Worker (State Machine)

**File**: `freqtrade/worker.py`

The `Worker` class manages the bot's lifecycle as a state machine:

```
States: STOPPED → RUNNING ⇄ PAUSED → RELOAD_CONFIG → RUNNING
                                    ↘ STOPPED
```

```python
class Worker:
    def __init__(self, config, freqtradebot):
        self._state = State.STOPPED
        self._heartbeat_count = 0

    def run(self):
        """Main infinite loop."""
        while True:
            self._worker()
            self._throttle()  # Sleep aligned to candle close + 1s offset

    def _worker(self):
        """State machine dispatch."""
        if self._state == State.STOPPED:
            return  # Do nothing
        elif self._state == State.RUNNING:
            self._process_running()
        elif self._state == State.PAUSED:
            self._process_running()  # Still processes open trades, no new entries
        elif self._state == State.RELOAD_CONFIG:
            self._reload_config()

    def _process_running(self):
        self._freqtrade.process()
```

**Throttling**: The `_throttle()` method calculates sleep time aligned to the next candle close, with a 1-second offset to ensure the exchange has emitted the new candle. Default throttle: 5 seconds (`PROCESS_THROTTLE_SECS`).

**systemd Integration**: Uses `sdnotify` for proper service lifecycle management (`freqtrade.service`).

### 4.2 The Core Engine (FreqtradeBot.process())

**File**: `freqtrade/freqtradebot.py` (~2665 lines)

Each processing iteration executes a **12-step pipeline**:

```
┌─────────────────────────────────────────────────────┐
│           FreqtradeBot.process() — One Iteration     │
├─────────────────────────────────────────────────────┤
│ Step 1:  reload_markets()                            │
│ Step 2:  update_trades_without_assigned_fees()       │
│ Step 3:  Trade.get_open_trades()                     │
│ Step 4:  PairListManager.refresh_pairlist()           │
│ Step 5:  DataProvider.refresh() — fetch OHLCV        │
│ Step 6:  strategy.bot_loop_start()                   │
│ Step 7:  strategy.analyze(pairs) — indicators+signals│
│ Step 8:  manage_open_orders() — timeout/replacement  │
│ Step 9:  exit_positions(trades) — ROI/SL/trailing    │
│ Step 10: process_open_trade_positions() — DCA        │
│ Step 11: enter_positions() — new entries              │
│ Step 12: scheduled tasks + commit + RPC queue        │
└─────────────────────────────────────────────────────┘
```

**Detailed Pipeline**:

**Step 1 — Reload Markets**: Ensures exchange market metadata (tick sizes, lot sizes, fees) is fresh. Rate-limited to avoid hammering the API.

**Step 2 — Update Fees**: Backfills missing fee data for trades where the exchange didn't return fee information in the initial order response.

**Step 3 — Get Open Trades**: Queries `Trade.get_open_trades()` from the database (SQLAlchemy/SQLite or PostgreSQL).

**Step 4 — Refresh Pairlist**: `PairListManager` runs the configured chain of pairlist handlers (generator → filter → filter → ... → blacklist). Returns the active whitelist of tradable pairs.

**Step 5 — Refresh Candle Data**: `DataProvider.refresh()` fetches OHLCV for all whitelisted pairs plus any informative pairs (multi-timeframe) at the strategy's configured timeframe.

**Step 6 — Strategy Loop Start**: Calls `strategy.bot_loop_start(current_time)` — a hook for strategy-level per-iteration work (e.g., log custom metrics, reset counters).

**Step 7 — Strategy Analysis**: For each pair in the whitelist:
1. `populate_indicators(dataframe, metadata)` — compute technical indicators
2. `populate_entry_trend(dataframe, metadata)` — set `enter_long`/`enter_short` columns
3. `populate_exit_trend(dataframe, metadata)` — set `exit_long`/`exit_short` columns

If `process_only_new_candles=True` and the last candle hasn't changed, analysis is skipped entirely.

**Step 8 — Manage Open Orders**: Checks all open trades for unfilled orders:
- If timeout exceeded → cancel the order
- If exit order timeout exceeded → emergency market exit
- On new candles → optionally re-price unfilled orders via `strategy.adjust_entry_price()` / `adjust_exit_price()`

**Step 9 — Exit Positions**: For each open trade, checks exit conditions in priority order:
1. Exit signal from strategy (`populate_exit_trend` / `custom_exit`)
2. Stop loss (fixed, custom, or on-exchange)
3. ROI target (time-based from `minimal_roi` table)
4. Trailing stop loss
5. Liquidation price (futures)
6. Emergency exit (if stoploss placement failed)

A threading lock (`_exit_lock`) protects exit logic from race conditions with force-sell commands arriving via RPC.

**Step 10 — Position Adjustment (DCA)**: If `position_adjustment_enable=True`, calls `strategy.adjust_trade_position()` for every open trade. Positive return = add to position. Negative return = partially exit. Respects `max_entry_position_adjustment` limit.

**Step 11 — Enter New Positions**: If the bot is `RUNNING` and free trade slots exist (`max_open_trades`), iterates the whitelist and calls `create_trade()` for each pair with a valid entry signal.

**Step 12 — Commit & RPC**: Flushes all trade/order changes to the database via `Trade.commit()`, then processes the RPC message queue (Telegram notifications, API broadcasts, webhooks).

### 4.3 Order Placement Flow

```
create_trade(pair, stake_amount, is_short)
  │
  ├── wallet.validate_stake_amount()       # Check min/max limits
  ├── strategy.custom_stake_amount()       # Override stake size
  ├── strategy.confirm_trade_entry()       # Veto check
  ├── strategy.leverage()                  # Set leverage (futures)
  ├── strategy.custom_entry_price()        # Override entry price
  │
  ├── Exchange.create_order()              # Place order
  │     ├── create_dry_run_order()         # Dry run: simulate fill
  │     └── ccxt.create_order()            # Live: send to exchange
  │
  ├── Trade.query_trade_id()               # Create DB record
  ├── order_filled_callback()              # Post-fill hook
  └── RPCManager.send_msg(ENTRY)           # Notify
```

---

## 5. Strategy Framework (IStrategy)

### 5.1 Base Class

**File**: `freqtrade/strategy/interface.py` (~1903 lines)

`IStrategy` is an Abstract Base Class mixed with `HyperStrategyMixin` for hyperopt support. Every user strategy must inherit from it.

### 5.2 Three Mandatory Methods

```python
class IStrategy(ABC):
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Compute technical indicators on OHLCV data.
        Must return the modified DataFrame."""
        raise NotImplementedError

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Set enter_long and/or enter_short columns to 1 for signal candles.
        Must return the modified DataFrame."""
        raise NotImplementedError

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Set exit_long and/or exit_short columns to 1 for signal candles.
        Must return the modified DataFrame."""
        raise NotImplementedError
```

### 5.3 Key Class Attributes

```python
class IStrategy:
    # Required
    timeframe = "5m"                    # Candle timeframe (1m, 5m, 1h, 1d, etc.)

    # Stoploss
    stoploss = -0.10                    # Hard stoploss (-10%)
    trailing_stop = False               # Enable trailing stoploss
    trailing_stop_positive = 0.01       # Trailing stop level when profitable
    trailing_stop_positive_offset = 0.02  # Offset before trailing activates
    trailing_only_offset_is_reached = False
    use_custom_stoploss = False         # Use custom_stoploss() callback

    # ROI (Return on Investment)
    minimal_roi = {
        "60": 0.01,    # After 60 minutes: 1% profit target
        "30": 0.02,    # After 30 minutes: 2%
        "0": 0.04,     # Immediately: 4%
    }

    # Short selling
    can_short = False                   # Whether strategy supports shorts

    # Signals
    use_exit_signal = True              # Use exit signals from populate_exit_trend
    exit_profit_only = False            # Only exit when in profit
    exit_profit_offset = 0.0            # Minimum profit ratio to exit

    # Performance
    process_only_new_candles = True     # Skip re-analysis on same candle
    startup_candle_count = 0            # Extra candles for indicator warmup

    # Orders
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "limit",
        "stoploss_on_exchange": False,
        "stoploss_on_exchange_interval": 60,
        "stoploss_on_exchange_limit_ratio": 0.99,
    }
    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC",
    }
```

### 5.4 Signal Flow

```
DataProvider.refresh() fetches OHLCV
         │
         ▼
IStrategy.analyze_pair(pair)
         │
         ├── _analyze_ticker_internal()
         │     ├── Check: is last candle new? (skip if process_only_new_candles)
         │     │
         │     ├── advise_indicators()
         │     │     ├── Process @informative-decorated methods
         │     │     └── Call populate_indicators(dataframe, metadata)
         │     │
         │     ├── advise_entry()
         │     │     └── Call populate_entry_trend(dataframe, metadata)
         │     │         Ensures enter_long/enter_short columns exist (default 0)
         │     │
         │     └── advise_exit()
         │           └── Call populate_exit_trend(dataframe, metadata)
         │               Ensures exit_long/exit_short columns exist (default 0)
         │
         └── Cache result in DataProvider
```

### 5.5 Signal Columns

| Column | Values | Meaning |
|--------|--------|---------|
| `enter_long` | 0 or 1 | Enter long position at this candle |
| `enter_short` | 0 or 1 | Enter short position at this candle |
| `exit_long` | 0 or 1 | Exit long position at this candle |
| `exit_short` | 0 or 1 | Exit short position at this candle |
| `enter_tag` | string | Label for the entry reason (for analytics) |
| `exit_tag` | string | Label for the exit reason |

**Mutual Exclusivity**: `get_entry_signal()` enforces that you cannot enter long and short simultaneously on the same candle. Entering is also blocked if an exit signal fires on the same candle.

### 5.6 Callback Hooks (15+ hooks)

| Callback | When Called | Returns | Purpose |
|----------|-----------|---------|---------|
| `bot_start()` | Once after bot instantiation | None | Initialize strategy-wide state |
| `bot_loop_start(current_time)` | Start of every processing iteration | None | Per-iteration work |
| `confirm_trade_entry(pair, order_type, amount, rate, ...)` | Before placing entry order | bool (True=allow) | Veto entry decisions |
| `confirm_trade_exit(pair, trade, order_type, ...)` | Before placing exit order | bool (True=allow) | Veto exit decisions |
| `order_filled(pair, trade, order, current_time)` | After any order fills | None | React to fills |
| `custom_entry_price(pair, trade, proposed_rate, ...)` | Override entry limit price | float | Custom entry price |
| `custom_exit_price(pair, trade, proposed_rate, ...)` | Override exit limit price | float | Custom exit price |
| `custom_stoploss(pair, trade, current_rate, current_profit, after_fill)` | Dynamic stoploss | float (ratio) | Dynamic SL (cannot go below hard SL) |
| `custom_exit(pair, trade, current_rate, current_profit)` | Programmatic exit signal | str/bool (reason or False) | Programmatic exits |
| `custom_roi(pair, trade, trade_duration, ...)` | Dynamic ROI threshold | float | Dynamic ROI target |
| `custom_stake_amount(pair, proposed_stake, min_stake, max_stake, ...)` | Customize stake size | float | Per-trade stake override |
| `adjust_trade_position(trade, current_profit, ...)` | DCA/position adjustment | float (+add, -reduce) | Position averaging |
| `adjust_entry_price(trade, order, proposed_rate, ...)` | Re-price unfilled entry | float | Order book walking |
| `adjust_exit_price(trade, order, proposed_rate, ...)` | Re-price unfilled exit | float | Order book walking |
| `leverage(pair, proposed_leverage, max_leverage, ...)` | Set leverage per trade | float | Futures leverage |
| `check_entry_timeout(pair, trade, order, ...)` | Custom entry timeout | bool (True=cancel) | Timeout override |
| `check_exit_timeout(pair, trade, order, ...)` | Custom exit timeout | bool (True=cancel) | Timeout override |

All callbacks are wrapped by `strategy_safe_wrapper()` (`freqtrade/strategy/strategy_wrapper.py`) which:
- **Deep-copies** the `trade` object to prevent accidental mutation
- **Catches all exceptions** and returns a default value (or raises `StrategyError` for critical hooks)
- Logs warnings for strategy errors without crashing the bot

### 5.7 Hyperopt Parameters

Strategies can declare hyperoptable parameters using typed parameter classes:

```python
from freqtrade.strategy import IntParameter, DecimalParameter, BooleanParameter, CategoricalParameter

class MyStrategy(IStrategy):
    # Hyperoptable parameters
    buy_rsi = IntParameter(20, 40, default=30, space="buy", optimize=True)
    sell_rsi = IntParameter(60, 80, default=70, space="sell", optimize=True)
    buy_ema_short = DecimalParameter(5.0, 20.0, default=9.0, space="buy")
    buy_ema_long = DecimalParameter(20.0, 50.0, default=21.0, space="buy")
    use_macd = BooleanParameter(default=True, space="buy")
    exit_mode = CategoricalParameter(["rsi", "trailing", "roi"], default="rsi", space="sell")

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["rsi"] < self.buy_rsi.value) &
            (dataframe["ema_short"] < dataframe["ema_long"]),
            "enter_long"
        ] = 1
        return dataframe
```

**Parameter Spaces**: `buy`, `sell`, `exit`, `roi`, `stoploss`, `trailing`, `protection`

### 5.8 Informative Timeframe Decorator

The `@informative` decorator simplifies multi-timeframe analysis:

```python
@informative("1h")
def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
    return dataframe
```

This automatically merges the 1-hour indicators into the main timeframe DataFrame.

---

## 6. Data Layer & Market Data Pipeline

### 6.1 Data Fetching Pipeline

```
Exchange.fetch_ohlcv()  ←──  ccxt.fetchOHLCV()
        │
        ▼
history_utils._download_pair_history()
        │
        ├── _load_cached_data_for_updating()  # Check existing cache
        ├── exchange.get_historic_ohlcv()       # Async batch download (100 candles/request)
        └── clean_ohlcv_dataframe()             # Deduplicate & merge
                │
                ▼
DataHandler.ohlcv_store()  →  Disk (Feather/Parquet/JSON)
```

**Download Modes**:
- **OHLCV-based** (default): Fetches candle data using `fetchOHLCV`-equivalent async methods. Batched in 100-candle chunks. Concurrent via asyncio gather.
- **Trade-based**: Fetches raw trade data for exchanges that don't provide historic klines. Trades are then converted to OHLCV via `trades_to_ohlcv()`.

### 6.2 Data Storage (Pluggable Handlers)

**File**: `freqtrade/data/history/datahandlers/`

| Handler | Format | Default | Compression | Notes |
|---------|--------|---------|-------------|-------|
| `FeatherDataHandler` | Apache Arrow Feather | **Yes** | LZ4 (level 9) | Best performance |
| `ParquetDataHandler` | Apache Parquet | No | Configurable | Columnar, good compression |
| `JsonDataHandler` | JSON | No | None | Human readable |
| `JsonGzDataHandler` | JSON + gzip | No | gzip | Compressed JSON |

**File naming**: `{pair}-{timeframe}[-{candle_type}].{extension}`
- Example: `BTC_USDT-5m.feather` (spot)
- Futures: `BTC_USDT_USDT-5m.feather` under `futures/` subdirectory
- Mark price: `BTC_USDT_USDT-5m-mark.feather`

**Arrow Performance Optimization**: `ArrowDataHandler` (base for Feather/Parquet) uses pyarrow's `dataset()` API with **predicate pushdown** to filter only the needed time range when loading, avoiding full file reads. The `_build_arrow_ohlcv_filter()` method constructs Arrow filter expressions on the "date" column.

### 6.3 OHLCV Conversion & Cleaning

**File**: `freqtrade/data/converter/converter.py`

```python
def ohlcv_to_dataframe(data, timeframe, df_append=False, ...
    # 1. Raw exchange data → DataFrame [date, open, high, low, close, volume]
    # 2. Floor dates to timeframe precision
    # 3. Cast all values to float
    # 4. clean_ohlcv_dataframe()
)

def clean_ohlcv_dataframe(dataframe, timeframe, ...
    # 1. Group by date → aggregate (first open, max high, min low, last close, max volume)
    # 2. Optionally drop last candle (may be incomplete)
    # 3. Optionally fill missing data via ohlcv_fill_up_missing_data()
)

def ohlcv_fill_up_missing_data(dataframe, timeframe, ...
    # 1. pandas resample() to detect gaps
    # 2. Missing candles filled with previous close (OHLC) and 0 (volume)
    # This is a "forward-fill" — no quality tagging!
)
```

### 6.4 Candle Types

**Enum**: `freqtrade/enums/candletype.py`

| Type | Purpose |
|------|---------|
| `SPOT` | Standard spot market candles |
| `FUTURES` | Futures market candles (default funding rate timeframe) |
| `MARK` | Mark price candles (for liquidation calculations) |
| `INDEX` | Index price candles |
| `PREMIUM_INDEX` | Premium index (mark - index) |
| `FUNDING_RATE` | Funding rate candles |

### 6.5 Trades-to-OHLCV Conversion

**File**: `freqtrade/data/converter/trade_converter.py`

```python
def trades_to_ohlcv(trades, timeframe):
    # 1. Set trade date as index
    # 2. pandas resample() + .ohlc() on price column → open/high/low/close
    # 3. Sum trade amounts within each period → volume
    # 4. Drop zero-volume rows
```

### 6.6 Orderflow Analysis

**File**: `freqtrade/data/converter/orderflow.py`

Provides orderflow analysis from public trades:
- Groups trades by candle start time
- Creates volume profiles with bid/ask delta at price levels
- Calculates imbalances (diagonal bid vs ask comparisons at price levels)
- Detects stacked imbalances (consecutive price levels with same imbalance direction)

### 6.7 DataProvider

**File**: `freqtrade/data/dataprovider.py`

The central data access interface used by strategies:

- **Live/Dry-run**: Serves real-time OHLCV from exchange kline cache (`exchange.klines()`)
- **Backtesting**: Loads cached historical data from disk via `load_pair_history()`
- Manages **informative pairs** and **producer data** for multi-bot architectures
- Supports **slice-based access** (`_set_dataframe_max_index`) to prevent lookahead bias — strategies only see data up to the current simulation point

---

## 7. Exchange Abstraction Layer

### 7.1 Architecture

**File**: `freqtrade/exchange/exchange.py` (~4157 lines)

The `Exchange` class wraps **ccxt** (synchronous `_api`) and **ccxt.pro** (async `_api_async`) with optional WebSocket support via `ExchangeWS`.

```
Exchange (base class)
├── Binance
├── Bybit
├── OKX
├── Kraken
├── Gate
├── Bitget
├── BingX
├── HTX
├── Hyperliquid (DEX)
├── BitMart
├── Bitvavo
├── KuCoin
├── Crypto.com
├── HitBTC
├── LBank
├── CoinEx
├── Kraken Futures
├── Bitpanda
├── Luno
├── ModeTrade
└── IDEX
```

### 7.2 Exchange-Specific Customization

Each exchange subclass overrides `_ft_has` to customize behavior:

```python
class Binance(Exchange):
    _ft_has = {
        "stoploss_order_types": {
            "stoploss": "stop_market",
            "stoploss_limit": "stop",
        },
        "stoploss_on_exchange_limit_ratio": 0.99,
        "timeframe_to_seconds": {
            "1m": 60, "5m": 300, "15m": 900, "1h": 3600, ...
        },
        "leverage_tiers": True,
        "exchange_ccxt_config": {"options": {"defaultType": "future"}},
    }
```

### 7.3 Key Exchange Operations

| Method | Purpose | Notes |
|--------|---------|-------|
| `create_order(pair, ordertype, side, amount, rate, leverage, time_in_force, reduceOnly)` | Place an order | Dry-run: simulates fill. Live: sends to exchange |
| `create_stoploss(pair, amount, stop_price, order_types, side, leverage)` | Place SL on exchange | Exchange-specific order type mapping |
| `fetch_order(order_id, pair)` | Get order status | |
| `fetch_stoploss_order(order_id, pair)` | Get SL order status | |
| `cancel_order_with_result(order_id, pair, amount)` | Cancel an order | Returns final state |
| `cancel_stoploss_order_with_result(order_id, pair, amount)` | Cancel SL order | |
| `get_rate(pair, side, is_short)` | Get entry/exit rate | Bid for buy, ask for sell |
| `fetch_ohlcv(pair, timeframe, since, limit)` | Fetch candle data | Rate-limited batching |
| `fetch_l2_order_book(pair, limit)` | Get order book | |
| `get_balances()` | Account balances | |
| `fetch_positions()` | Open futures positions | |
| `get_funding_fees(pair, amount, is_short, open_date)` | Accumulated funding fees | |
| `get_liquidation_price(...)` | Calculate liquidation | |
| `get_max_leverage(pair, stake_amount)` | Max allowed leverage | From leverage tiers |
| `get_min_pair_stake_amount(pair, rate, stoploss, leverage)` | Minimum trade size | |

### 7.4 Dry Run Mode

When `dry_run=True`, `create_order()` delegates to `create_dry_run_order()`:
- **Market orders**: Filled immediately at current bid/ask + slippage
- **Limit orders**: May be filled on subsequent iterations when the candle's price range crosses the limit price
- Simulated fills are tracked in-memory with fake order IDs

### 7.5 WebSocket Support

If the exchange supports `watchOHLCV` and WS is enabled, an `ExchangeWS` instance runs in a background thread, pushing candle updates directly to DataProvider. This reduces API calls and provides sub-second candle updates.

---

## 8. Risk Management & Stoploss

### 8.1 Fixed Stoploss

Set via `strategy.stoploss = -0.10` (e.g., -10%). Applied at trade creation:

```python
trade.adjust_stop_loss(trade.open_rate, stoploss, initial=True)
# Sets initial_stop_loss, initial_stop_loss_pct
# For leveraged trades: stoploss_pct = stoploss_pct / leverage
```

### 8.2 Trailing Stoploss

Configuration:
```python
trailing_stop = True
trailing_stop_positive = 0.01          # Tighten to 1% when profitable
trailing_stop_positive_offset = 0.02   # Activate after 2% profit
trailing_only_offset_is_reached = False  # Start trailing immediately
```

**Behavior**: The stoploss only moves in the profitable direction:
- Long: stoploss only goes UP (never down)
- Short: stoploss only goes DOWN (never up)

When profit exceeds `trailing_stop_positive_offset`, the stoploss tightens to `trailing_stop_positive` ratio from current price.

### 8.3 Custom Stoploss

When `use_custom_stoploss=True`, calls `strategy.custom_stoploss()` on every candle:

```python
def custom_stoploss(self, pair: str, trade, current_time, current_rate,
                    current_profit, after_fill=False) -> Optional[float]:
    """Return a new stoploss ratio relative to current price.
    Must be >= self.stoploss (hard floor).
    Return None to keep current stoploss."""
    if current_profit > 0.05:
        return 0.01  # Tight 1% stop when >5% profit
    return None  # Keep default
```

Called both during candle analysis and after order fills (when `_ft_stop_uses_after_fill=True`).

### 8.4 Stoploss on Exchange

When `stoploss_on_exchange=True`:
1. Places an actual stoploss order on the exchange (limit or market)
2. Supports trailing: when stoploss price changes, old order is cancelled and new one placed
3. Rate-limited by `stoploss_on_exchange_interval` (default 60s between updates)
4. If all SL orders get cancelled externally, a new one is automatically recreated

The effective stop price is:
- Long: `min(stop_loss, liquidation_price)` — whichever is higher (worse for the trader)
- Short: `max(stop_loss, liquidation_price)` — whichever is lower

### 8.5 Exit Conditions (Priority Order)

Evaluated in `IStrategy.should_exit()`:

| Priority | Exit Type | Trigger |
|----------|-----------|---------|
| 1 | Exit Signal | From `populate_exit_trend()` or `custom_exit()` |
| 2 | Stop Loss | Fixed or custom stoploss breached |
| 3 | ROI | Time-based profit target reached |
| 4 | Trailing Stop | Trailing stop triggered |

Additional exit types: `FORCE_EXIT`, `EMERGENCY_EXIT`, `SOLD_ON_EXCHANGE`, `LIQUIDATION`, `PARTIAL_EXIT`, `STOPLOSS_ON_EXCHANGE`.

### 8.6 Liquidation Price Protection

For futures positions:
- Tracked for every position via `trade.liquidation_price`
- In **cross-margin mode**: recalculated every 30 minutes for ALL open trades
- In **isolated mode**: calculated per-trade when entry order fills
- Trades can be closed via `ExitType.LIQUIDATION` if price hits the liquidation level
- The effective stop is always the worst of stoploss vs liquidation

### 8.7 Protection System

**File**: `freqtrade/plugins/protections/`

| Protection | Scope | Behavior |
|------------|-------|----------|
| `CooldownPeriod` | Per-pair | Locks pair for cooldown duration after trade closes |
| `StoplossGuard` | Per-pair + Global | If N stoplosses hit within lookback period, locks pair or all pairs |
| `MaxDrawdown` | Global only | If drawdown exceeds threshold, locks all pairs |
| `LowProfitPairs` | Per-pair | If cumulative profit for pair below threshold, locks it |

Each protection uses `PairLocks` to prevent new entries. Protections are evaluated after every trade close via `handle_protections()`. Auto-locks the pair for one candle to prevent immediate re-entry.

---

## 9. Position Sizing & Wallet Management

### 9.1 Wallets Class

**File**: `freqtrade/wallets.py`

```python
class Wallets:
    def update(self):
        """Refresh balances. Throttled to once per hour."""
        if self._config["trading_mode"] == "dry_run":
            self._update_dry()
        else:
            self._update_live()

    def _update_dry(self):
        """Dry run: compute from trade DB."""
        # balance = starting_balance + total_closed_profit + realized_profit - total_in_trades

    def _update_live(self):
        """Live: query exchange."""
        balances = self._exchange.get_balances()
        positions = self._exchange.fetch_positions()
```

**Data Structures**:
```python
Wallet = NamedTuple("Wallet", ["currency", "free", "used", "total"])
PositionWallet = NamedTuple("PositionWallet", ["symbol", "position", "leverage", "collateral", "side"])
```

### 9.2 Stake Amount Calculation

Three modes:

1. **Fixed stake**: `config["stake_amount"] = 100` (always stake 100 USDT)
2. **Unlimited stake**: `config["stake_amount"] = "unlimited"`
   ```
   possible_stake = (available_amount + tied_up) / max_open_trades
   stake = min(possible_stake, available_amount)
   ```
3. **Custom stake**: `strategy.custom_stake_amount()` overrides the calculated amount

### 9.3 Stake Validation

```python
def validate_stake_amount(self, pair, amount, leverage, side):
    """Enforces exchange min/max limits."""
    min_stake = exchange.get_min_pair_stake_amount(pair, rate, stoploss, leverage)
    max_stake = exchange.get_max_pair_stake_amount(pair, rate, leverage)

    if amount < min_stake:
        if amend_last_stake_amount and (min_stake - amount) / min_stake < 0.30:
            amount = min_stake  # Adjust if <30% adjustment needed
        else:
            return None  # Skip trade

    return min(amount, max_stake)
```

### 9.4 Available Balance Calculation

```
total_stake_amount = (open_stakes + free_balance) * tradable_balance_ratio
available = min(total_stake_amount - open_trade_stakes, free_balance)
```

With `available_capital` config: `total_stake_amount = available_capital` (fixed starting capital).

---

## 10. Backtesting Engine

### 10.1 Initialization

**File**: `freqtrade/optimize/backtesting.py` (~1979 lines)

```python
class Backtesting:
    def __init__(self, config):
        self._exchange = ExchangeResolver.load_exchange(config)
        self._strategy = StrategyResolver.load_strategy(config)
        self.dataprovider = DataProvider(config, self._exchange)
        self.pairlists = PairListManager(config, self._exchange, self.dataprovider)
        self.wallets = Wallets(config, self._exchange, self.dataprovider, realtime=False)
        self.fee = self._exchange.get_ticker_fee()  # Worst-case taker fee
```

### 10.2 Data Loading

```python
def load_bt_data(config, exchange):
    # 1. Load OHLCV from disk for all whitelist pairs
    data = history.load_data(datadir=config["datadir"], pairs=..., timeframe=...)

    # 2. Compute timerange across all pairs
    min_date = min(candle["date"] for pair_data in data.values() for candle in pair_data)
    max_date = max(...)

    # 3. Load detail timeframe data if configured
    # 4. Load futures data (funding rates, mark prices)
    # 5. Return data dict + timerange
```

### 10.3 Signal Generation (Critical Preprocessing)

```python
def _get_ohlcv_as_lists(self, processed):
    """Convert DataFrames to lists of tuples for performance."""
    for pair, df in processed.items():
        # 1. Generate signals via strategy
        self.strategy.ft_advise_signals(df, {"pair": pair})

        # 2. SHIFT ALL SIGNALS BY 1 CANDLE (anti-lookahead bias!)
        # Decision at candle N is applied at candle N+1
        df['enter_long'] = df['enter_long'].shift(1)
        df['enter_short'] = df['enter_short'].shift(1)
        df['exit_long'] = df['exit_long'].shift(1)
        df['exit_short'] = df['exit_short'].shift(1)

        # 3. Trim startup period
        # 4. Convert to list of tuples:
        #    [date, open, high, low, close, enter_long, exit_long,
        #     enter_short, exit_short, enter_tag, exit_tag]
```

### 10.4 Main Backtest Loop

```
backtest(processed, start_date, end_date)
    │
    ├── reset_backtest()
    ├── _get_ohlcv_as_lists()     # Convert DataFrames + generate signals
    │
    └── time_pair_generator()     # Generator yielding (time, pair, row, trade_dir)
         │
         └── for each main candle:
              for each detail candle (if configured):
                   for each pair:
                        backtest_loop(row, pair, time, trade_dir, can_enter)
```

### 10.5 Per-Candle Processing

```python
def backtest_loop(self, row, pair, time, trade_dir, can_enter):
    # 1. Manage open orders: check timeout, re-price unfilled orders

    # 2. Process entries:
    if trade_signal_exists and pair_not_locked and trade_slot_available:
        self._enter_trade(pair, row, trade_dir)

    # 3. Fill entry orders:
    #    Order fills if price is within candle range: LOW <= rate <= HIGH

    # 4. Check for exits:
    self._check_trade_exit(trade, row)
    #    Checks: stoploss, ROI, trailing, custom exit, exit signals

    # 5. Fill exit orders
```

### 10.6 Order Fill Simulation

```python
def _get_order_filled(self, rate, row):
    """Order fills if its price falls within the candle's high-low range."""
    return row[LOW_IDX] <= rate <= row[HIGH_IDX]
```

**Key simulation details**:
- Orders fill **instantly** within the same candle if the price is reachable
- Entry prices clamped: `min(proposed_rate, HIGH)` for longs, `max(proposed_rate, LOW)` for shorts
- All prices go through `price_to_precision()` for tick size compliance
- A single fee rate (worst-case taker) applied to both entry and exit

### 10.7 Exit Price Determination

Different exit types use different pricing:

| Exit Type | Price Used |
|-----------|-----------|
| Stoploss / Trailing Stop | The stoploss value itself (if within candle range, otherwise open price) |
| ROI | Calculated via `trade.calc_close_rate_for_roi()`, clamped to H-L range |
| Exit Signal / Custom Exit | Open price by default, custom via `strategy.custom_exit_price()` |

**Special case — Same-candle trailing stop**: Worst-case: arm trailing on this candle AND immediately hit it. Uses open price as fill.

### 10.8 Detail Timeframe Processing

When a detail timeframe is configured (e.g., main=1h, detail=5m):
- Each main candle is split into sub-candles
- Trade signals come from the main candle
- Entry/exit timing uses detail candle granularity
- `strategy.ignore_expired_candle()` can suppress late entries on detail candles

### 10.9 Left-Open Trade Handling

At backtesting end, `handle_left_open()` force-exits any remaining open trades at the open price of the last candle, marking them as `FORCE_EXIT`.

### 10.10 Funding Fees (Futures)

`_run_funding_fees()` calculates funding fees at each funding fee interval by calling `exchange.calculate_funding_fees()` with stored futures data (combined funding rates and mark prices).

---

## 11. Hyperparameter Optimization (Hyperopt)

### 11.1 Architecture

```
Hyperopt (orchestrator)
    │
    ├── HyperOptimizer (worker)
    │     ├── Optuna backend (ask/tell interface)
    │     ├── Joblib Parallel (multi-process)
    │     └── Backtesting engine
    │
    ├── HyperOptAuto (auto-discover parameters from strategy)
    │
    └── Loss Functions (13 built-in)
```

### 11.2 Optimization Spaces

| Space | What's Optimized | Source |
|-------|-----------------|--------|
| `buy` | Strategy buy parameters | `IntParameter`, `DecimalParameter` in strategy |
| `sell` | Strategy sell parameters | Same |
| `roi` | ROI table entries | `minimal_roi` |
| `stoploss` | Stoploss percentage | `stoploss` |
| `trailing` | Trailing stop parameters | trailing_stop, trailing_stop_positive, offset |
| `trades` | Max open trades | `max_open_trades` |
| `protection` | Protection parameters | Protection configs |

### 11.3 Epoch Execution Flow

```
1. Optimizer proposes parameter values (Optuna ask)
2. Set strategy parameters from proposed values
3. Generate ROI table, set stoploss, trailing, max_open_trades
4. Load pre-processed data from pickle (hyperopt_tickerdata.pkl)
5. If analyze_per_epoch: re-run indicator calculation
6. Call backtesting.backtest() → get results
7. Compute loss function value
8. Report result to optimizer (Optuna tell)
```

### 11.4 Loss Functions (13 Built-in)

| Function | Metric | Optimization Direction |
|----------|--------|----------------------|
| `SharpeHyperOptLoss` | Sharpe Ratio | Maximize (returns negative) |
| `SharpeHyperOptLossDaily` | Daily Sharpe | Maximize |
| `SortinoHyperOptLoss` | Sortino Ratio | Maximize |
| `SortinoHyperOptLossDaily` | Daily Sortino | Maximize |
| `CalmarHyperOptLoss` | Calmar Ratio | Maximize |
| `MaxDrawDownHyperOptLoss` | Max Drawdown | Minimize |
| `MaxDrawDownRelativeHyperOptLoss` | Relative Max DD | Minimize |
| `ProfitDrawDownHyperOptLoss` | Profit/Drawdown ratio | Maximize |
| `MultiMetricHyperOptLoss` | Combined metrics | Maximize |
| `OnlyProfitHyperOptLoss` | Raw profit | Maximize |
| `ShortTradeDurHyperOptLoss` | Short trade duration | Maximize (penalize short trades) |
| `ProfitDrawDownHyperOptLoss` | Profit vs DD | Maximize |
| `CalmarHyperOptLoss` | Calmar ratio | Maximize |

All return a float where **smaller is better** (the optimizer minimizes).

### 11.5 Samplers

Supported Optuna samplers:
- **TPESampler** (default) — Tree-structured Parzen Estimator
- **GPSampler** — Gaussian Process
- **CmaEsSampler** — CMA-ES (Covariance Matrix Adaptation)
- **NSGAIISampler** — Non-dominated Sorting Genetic Algorithm II
- **NSGAIIISampler** — NSGA-III
- **QMCSampler** — Quasi-Monte Carlo

### 11.6 Caching

`get_strategy_run_id()` generates a SHA1 hash from strategy file + config (excluding non-impacting keys). This allows reusing backtest results when the same configuration is re-run.

### 11.7 Early Stopping

Supported via Optuna's `Terminator` with `BestValueStagnationEvaluator`.

---

## 12. UI, API & RPC Layer

### 12.1 Three-Layer Architecture

```
FreqtradeBot (Trading Engine)
       │
       ▼
     RPC (Business Logic — freqtrade/rpc/rpc.py, 1837 lines)
       │
       ▼
  RPCManager (Dispatcher — freqtrade/rpc/rpc_manager.py)
       │
       ▼
  RPCHandler subclasses (Output Channels):
    ├── Telegram     (freqtrade/rpc/telegram.py, 2285 lines)
    ├── ApiServer    (freqtrade/rpc/api_server/webserver.py, FastAPI)
    ├── Webhook      (freqtrade/rpc/webhook.py, HTTP POST)
    └── Discord      (freqtrade/rpc/discord.py, Discord embeds)
```

### 12.2 REST API (FastAPI)

**File**: `freqtrade/rpc/api_server/webserver.py`

- Built on **FastAPI** with **Uvicorn** ASGI server
- Runs in a **separate thread** via `UvicornServer.run_in_thread()`
- Uses **orjson** for high-performance JSON (handles NaN, numpy arrays)
- JWT authentication: access tokens (15min) + refresh tokens (30 days)
- OpenAPI docs at `/docs` when `enable_openapi=true`
- CORS middleware configurable per origin

### 12.3 Complete API Endpoint Catalog

#### Public Endpoints
| Method | Path | Function |
|--------|------|----------|
| GET | `/api/v1/ping` | Health check → `{"status": "pong"}` |

#### Info Endpoints
| Method | Path | Function |
|--------|------|----------|
| GET | `/api/v1/version` | Bot version |
| GET | `/api/v1/show_config` | Sanitized config (no secrets) |
| GET | `/api/v1/logs` | Log buffer |
| GET | `/api/v1/sysinfo` | CPU load, RAM usage |
| GET | `/api/v1/health` | Last process timestamp, bot start |
| GET | `/api/v1/markets` | Exchange market listing |

#### Trading Mode Endpoints
| Method | Path | Function |
|--------|------|----------|
| POST | `/api/v1/start` | Start trader |
| POST | `/api/v1/stop` | Stop trader |
| POST | `/api/v1/pause` | Pause entries |
| POST | `/api/v1/reload_config` | Reload config |
| GET | `/api/v1/balance` | Full balance + fiat |
| GET | `/api/v1/count` | Trade count vs max |
| GET | `/api/v1/status` | All open trades with live P&L |
| GET | `/api/v1/trades` | Closed trade history (paginated) |
| GET | `/api/v1/trade/{tradeid}` | Single trade details |
| DELETE | `/api/v1/trades/{tradeid}` | Delete trade |
| DELETE | `/api/v1/trades/{tradeid}/open-order` | Cancel open orders |
| POST | `/api/v1/trades/{tradeid}/reload` | Reload from exchange |
| GET | `/api/v1/profit` | Cumulative profit statistics |
| GET | `/api/v1/profit_all` | All/long/short breakdown |
| GET | `/api/v1/daily` | Daily profit |
| GET | `/api/v1/weekly` | Weekly profit |
| GET | `/api/v1/monthly` | Monthly profit |
| GET | `/api/v1/stats` | Exit reason stats + durations |
| GET | `/api/v1/performance` | Performance by pair |
| GET | `/api/v1/entries` | Performance by entry tag |
| GET | `/api/v1/exits` | Performance by exit reason |
| GET | `/api/v1/mix_tags` | Combined tag performance |
| GET | `/api/v1/whitelist` | Active whitelist |
| GET/POST/DELETE | `/api/v1/blacklist` | Blacklist management |
| GET | `/api/v1/locks` | Active pair locks |
| POST | `/api/v1/locks` | Add locks |
| DELETE | `/api/v1/locks/{lockid}` | Delete lock |
| POST | `/api/v1/forceenter` | Force entry |
| POST | `/api/v1/forceexit` | Force exit |
| GET | `/api/v1/pair_candles` | Live analyzed candle data |
| GET | `/api/v1/historic_balance` | Historical wallet balance |

#### Backtest Endpoints
| Method | Path | Function |
|--------|------|----------|
| POST | `/api/v1/backtest` | Start backtest (background) |
| GET | `/api/v1/backtest` | Get results |
| DELETE | `/api/v1/backtest` | Reset |
| GET | `/api/v1/backtest/abort` | Abort |
| GET | `/api/v1/backtest/history` | List historical results |
| GET | `/api/v1/backtest/history/result` | Load specific result |
| DELETE | `/api/v1/backtest/history/{file}` | Delete result |
| PATCH | `/api/v1/backtest/history/{file}` | Update metadata |

#### Data & Analysis Endpoints
| Method | Path | Function |
|--------|------|----------|
| POST | `/api/v1/download_data` | Download historical data |
| POST | `/api/v1/recursive_analysis` | Recursive analysis |
| POST | `/api/v1/lookahead_analysis` | Lookahead analysis |
| GET | `/api/v1/pairlists/available` | List pairlist filters |
| POST | `/api/v1/pairlists/evaluate` | Evaluate pairlist |

#### WebSocket
| Path | Function |
|------|----------|
| `WS /api/v1/message/ws` | Real-time bidirectional message stream |

### 12.4 WebSocket System

**Files**: `freqtrade/rpc/api_server/ws/`

- **`channel.py`** — Manages single WebSocket connection: send/recv, subscription tracking, adaptive send throttling
- **`message_stream.py`** — Pub/sub message bus using `asyncio.Future` chaining
- **`serializer.py`** — Custom JSON encoding for pandas DataFrames (with `__type__`/`__value__` markers)
- **`proxy.py`** — Unifies FastAPI WebSocket and `websockets` client

**Request Types** (Consumer → Server):
| Request | Purpose |
|---------|---------|
| `SUBSCRIBE` | Subscribe to message types (WHITELIST, ANALYZED_DF, etc.) |
| `WHITELIST` | Request current whitelist |
| `ANALYZED_DF` | Request analyzed dataframes |

### 12.5 External Message Consumer (Multi-Bot)

**File**: `freqtrade/rpc/external_message_consumer.py` (~393 lines)

Enables **multi-bot coordination** — one bot can consume analyzed dataframes and whitelists from another:
- Connects as WebSocket client to "producer" bots
- Subscribes to `WHITELIST` and `ANALYZED_DF` messages
- Consumed data fed into local `DataProvider`
- Handles reconnection with configurable timeouts
- Message size limits (default 8MB)

### 12.6 Background Task System

**File**: `freqtrade/rpc/api_server/webserver_bgwork.py`

`ApiBG` static class manages:
- Backtesting (cached instance + data)
- Pairlist evaluation
- Data download
- Analysis (lookahead + recursive)

Jobs tracked in `jobs: dict[str, JobsContainer]` with status, progress, error fields.

---

## 13. Telegram Bot Integration

**File**: `freqtrade/rpc/telegram.py` (2285 lines)

### Architecture
- Runs in a **dedicated thread** with async polling
- Uses `python-telegram-bot` library (`Application` class)
- Authorization via `chat_id` + optional `topic_id` + `authorized_users`
- All commands protected by `@authorized_only` decorator

### Complete Command Reference

#### Bot Control
| Command | Function |
|---------|----------|
| `/start` | Start the trader |
| `/stop` | Stop the trader |
| `/pause` | Pause entries, handle open trades |
| `/reload_config` | Reload config file |
| `/show_config` | Display running configuration |
| `/help` | Show all commands |
| `/version` | Show bot + strategy version |

#### Trade Management
| Command | Function |
|---------|----------|
| `/status [trade_id]` | Show open trades |
| `/status table` | Compact table view |
| `/order [trade_id]` | Show order details |
| `/trades [limit]` | List recent closed trades |
| `/forceexit [id]` | Force exit trade |
| `/forcelong [pair] [price]` | Force long entry |
| `/forceshort [pair] [price]` | Force short entry |
| `/delete [trade_id]` | Delete trade |
| `/reload_trade [trade_id]` | Reload from exchange |
| `/coo [trade_id]` | Cancel open orders |

#### Statistics & Monitoring
| Command | Function |
|---------|----------|
| `/profit [n]` | Cumulative profit |
| `/profit_long [n]` | Long-only profit |
| `/profit_short [n]` | Short-only profit |
| `/balance [full]` | Balance breakdown |
| `/daily [n]` | Daily profit table |
| `/weekly [n]` | Weekly profit |
| `/monthly [n]` | Monthly profit |
| `/performance` | Pair performance ranking |
| `/entries [pair]` | Entry tag performance |
| `/exits [pair]` | Exit reason performance |
| `/mix_tags [pair]` | Combined tag stats |
| `/count` | Trade count vs max |
| `/stats` | Win/loss by exit reason |
| `/health` | Bot health check |

#### Pairlist & Locks
| Command | Function |
|---------|----------|
| `/whitelist` | Show active whitelist |
| `/blacklist [pairs]` | Add to blacklist |
| `/bl_delete [pairs]` | Remove from blacklist |
| `/locks` | Show active pair locks |
| `/unlock [pair/id]` | Delete lock |

### Interactive Features
- **Inline keyboards** for `/forceexit` (shows trade buttons), `/forcelong`/`/forceshort` (pair grid)
- **Callback-based refresh** on status, profit, balance, performance views
- Per-exit-reason notification granularity (different notification for SL vs ROI)
- Configurable notification loudness: `on`, `silent`, or `off` per message type
- Custom keyboard layout configurable via `config["telegram"]["keyboard"]`

---

## 14. Persistence & Database

### 14.1 ORM Architecture

**File**: `freqtrade/persistence/`

Uses **SQLAlchemy** with `DeclarativeBase`. Supports SQLite (default) and PostgreSQL.

```python
# Initialization
engine = create_engine(db_url, connect_args={"check_same_thread": False} for SQLite)
session_factory = scoped_session(sessionmaker(bind=engine))
```

### 14.2 Database Schema

#### `trades` Table (Trade model, ~50 columns)

| Column | Type | Key Fields |
|--------|------|------------|
| `id` | Integer PK | Auto-increment |
| `exchange` | String(25) | Exchange name |
| `pair` | String(25), indexed | Trading pair (e.g., "BTC/USDT") |
| `base_currency` | String(25) | Base currency |
| `stake_currency` | String(25) | Quote currency |
| `is_open` | Boolean, indexed | Trade open status |
| `fee_open` / `fee_close` | Float | Entry/exit fee rates |
| `fee_open_cost` / `fee_close_cost` | Float | Fee costs in quote |
| `open_rate` | Float | Average entry price |
| `close_rate` | Float | Average exit price |
| `realized_profit` | Float | Realized profit (DCA) |
| `close_profit` | Float | Relative profit ratio |
| `close_profit_abs` | Float | Absolute profit |
| `stake_amount` | Float | Amount staked |
| `max_stake_amount` | Float | Maximum stake (DCA) |
| `amount` | Float | Base currency amount |
| `open_date` / `close_date` | DateTime | Timestamps |
| `stop_loss` | Float | Current SL price |
| `initial_stop_loss` | Float | Initial SL price |
| `is_stop_loss_trailing` | Boolean | Trailing SL active |
| `max_rate` / `min_rate` | Float | Price extremes |
| `exit_reason` | String(255) | Exit type |
| `strategy` | String(100) | Strategy name |
| `enter_tag` | String(255) | Entry signal tag |
| `timeframe` | Integer | Candle timeframe |
| `trading_mode` | Enum | SPOT/MARGIN/FUTURES |
| `leverage` | Float | Leverage multiplier |
| `is_short` | Boolean | Short trade flag |
| `liquidation_price` | Float | Liquidation price |
| `funding_fees` | Float | Cumulative funding fees |
| `contract_size` | Float | Contract size (futures) |

**Relationships**:
- `orders`: One-to-many with `Order` (cascade delete, lazy="selectin")
- `custom_data`: One-to-many with `_CustomData` (cascade delete, lazy="raise")

#### `orders` Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `ft_trade_id` | Integer FK → trades.id | Parent trade |
| `ft_order_side` | String(25) | "buy", "sell", or "stoploss" |
| `order_id` | String(255) | Exchange order ID |
| `status` | String(255) | Order status |
| `order_type` | String(50) | limit, market |
| `side` | String(25) | buy/sell |
| `price` | Float | Order price |
| `average` | Float | Average fill price |
| `amount` | Float | Order amount |
| `filled` | Float | Filled amount |
| `remaining` | Float | Remaining amount |
| `cost` | Float | Total cost |
| `stop_price` | Float | Stop price |
| `order_date` / `order_filled_date` | DateTime | Timestamps |
| `funding_fee` | Float | Funding fee for this order |
| `ft_order_tag` | String(255) | Order tag |

**Unique constraint**: (`ft_pair`, `order_id`)

#### `pairlocks` Table

| Column | Type | Notes |
|--------|------|-------|
| `pair` | String(25) | Pair or "*" for global |
| `side` | String(25) | "long", "short", or "*" |
| `reason` | String(255) | Lock reason |
| `lock_time` / `lock_end_time` | DateTime | Duration |
| `active` | Boolean | Active flag |

#### `trade_custom_data` Table

| Column | Type | Notes |
|--------|------|-------|
| `ft_trade_id` | Integer FK → trades.id | Parent trade |
| `cd_key` | String(255) | Key name |
| `cd_type` | String(25) | "str", "int", "float", "bool", "json" |
| `cd_value` | Text | Serialized value |

**Unique constraint**: (`ft_trade_id`, `cd_key`)

#### `KeyValueStore` Table

Predefined keys for bot-wide persistent values (e.g., `bot_start_time`, `startup_time`).

#### `wallet_history` Table

Daily wallet snapshots: currency, rate, balance, total_quote, total_position_value, collateral, leverage.

### 14.3 Auto-Migration

`check_migrate()` runs at startup:
1. Checks for missing columns
2. Backs up old tables → creates new schema → copies data → drops backups
3. Handles PostgreSQL sequence IDs explicitly
4. Sets SQLite WAL mode
5. Fixes stale dry-run orders and wrong `max_stake_amount` for leveraged trades

### 14.4 Dual-Mode Trade Model

- **`LocalTrade`**: Plain Python class (for backtesting, no DB dependency)
- **`Trade`**: Inherits from both `ModelBase` (SQLAlchemy) AND `LocalTrade`, adding ORM mapping

This enables code reuse across backtesting (in-memory) and live trading (database).

### 14.5 Context Switching

`FtNoDBContext` context manager disables database for `PairLocks`, `Trade`, and `CustomDataWrapper` during backtesting, using in-memory lists instead.

---

## 15. Plugin System

### 15.1 Resolver Pattern

**File**: `freqtrade/resolvers/iresolver.py`

All plugins use the same dynamic loading pattern:

```python
class IResolver:
    @classmethod
    def load_object(cls, config, ...):
        # 1. Search directories: built-in → user_data → extra
        # 2. Scan .py files for classes subclassing expected type
        # 3. Validate: obj.__module__ must match module name
        # 4. Instantiate with constructor injection
```

Concrete resolvers: `PairListResolver`, `ProtectionResolver`, `StrategyResolver`, `ExchangeResolver`, `HyperoptResolver`, `FreqaiModelResolver`.

### 15.2 Pairlist Handlers (22)

**Base**: `freqtrade/plugins/pairlist/IPairList.py`

**Generator/Filter Pattern**: First handler generates the list, subsequent handlers filter it.

#### Generators (Position 0)
| Handler | Backtesting | Description |
|---------|-------------|-------------|
| `StaticPairList` | Full support | Returns whitelist from config |
| `VolumePairList` | **No** | Dynamic by quote volume with lookback |
| `MarketCapPairList` | Biased | CoinGecko top-N by market cap |
| `PercentChangePairList` | Yes | By percent price change |
| `RemotePairList` | Yes | Fetches from remote URL |
| `ProducerPairList` | Yes | Receives from producer bot |
| `CrossMarketPairList` | Yes | Cross-market generation |

#### Filters (Position 1+)
| Handler | Backtesting | Description |
|---------|-------------|-------------|
| `PriceFilter` | Biased | Min/max price, low price ratio |
| `SpreadFilter` | **No** | Bid/ask spread ratio |
| `AgeFilter` | **No** | Min/max days listed |
| `PerformanceFilter` | NO_ACTION | Sort by historical performance |
| `ShuffleFilter` | Yes (seed) | Randomize order |
| `OffsetFilter` | Yes | Pagination (offset + count) |
| `FullTradesFilter` | Yes | Max concurrent trades reached |
| `PrecisionFilter` | Yes | Tick size/precision |
| `DelistFilter` | Yes | Delisted pairs |
| `PairInformationFilter` | Yes | Pair info data |
| `VolatilityFilter` | Yes | Volatility metrics |
| `RangeStabilityFilter` | Yes | Price range stability |

### 15.3 Protection Handlers (4)

| Handler | Scope | Behavior |
|---------|-------|----------|
| `CooldownPeriod` | Per-pair | Cooldown after trade closes |
| `StoplossGuard` | Per-pair + Global | Lock after N stoplosses in lookback period |
| `MaxDrawdown` | Global | Stop trading when max drawdown exceeded |
| `LowProfitPairs` | Per-pair | Lock pairs with cumulative loss |

---

## 16. FreqAI: Machine Learning Module

### 16.1 Architecture

**File**: `freqtrade/freqai/freqai_interface.py` (~1044 lines)

```
IFreqaiModel (base)
├── Regression Models
│     ├── LightGBMRegression
│     ├── XGBoostRegression
│     ├── XGBoostRFRegression
│     ├── CatboostRegression
│     ├── RandomForestRegression
│     └── LinearRegression
├── Classification Models
│     ├── LightGBMClassifier
│     ├── XGBoostClassifier
│     ├── XGBoostRFClassifier
│     └── RandomForestClassifier
├── Multi-Target Models
│     ├── LightGBMMultiTarget
│     └── XGBoostMultiTarget
├── Deep Learning
│     ├── PyTorchMLP
│     ├── PyTorchTransformer
│     └── PyTorchLSTM
└── Reinforcement Learning
      ├── RLCPPO (3, 4, 5 action spaces)
      └── RLEnv (Gymnasium environments)
```

### 16.2 Data Kitchen

`freqtrade/freqai/data_kitchen.py` handles:
- Feature engineering (adding indicators as features)
- Train/test split (time-series aware)
- Data normalization (StandardScaler, etc.)
- Feature importance analysis
- Prediction target creation

### 16.3 Training Pipeline

```
1. DataProvider sends OHLCV + informative data
2. DataKitchen prepares features + targets
3. Model trains on training set
4. Model validates on test set
5. Model saved to disk (model_data_drawer)
6. Predictions applied to live DataFrame
7. Strategy uses predictions as signals
```

### 16.4 Reinforcement Learning

Uses **Gymnasium** environments with **Stable Baselines3** (PPO):
- 3, 4, and 5 action space variants
- Custom reward functions
- GPU training support (via `Dockerfile.freqai_rl`)

---

## 17. Configuration System

### 17.1 Multi-Layer Configuration

1. **JSON config files**: Primary method. Multiple files merged (last wins).
2. **Environment variables**: `FREQTRADE__` prefix (e.g., `FREQTRADE__DRY_RUN=true`)
3. **CLI arguments**: Override any config option (`--dry-run`, `--config`, `--strategy`)
4. **Schema validation**: JSON Schema with auto-default injection

### 17.2 Loading Pipeline

```
config/configuration.py:
    1. Load from JSON files → merge
    2. Apply environment variable overrides
    3. Apply CLI argument overrides
    4. Run validation (config_validation.py)
    5. Migrate deprecated settings
    6. Detect run mode (live, dry_run, backtest, hyperopt, webserver)
    7. Remove sensitive credentials from logging
```

### 17.3 Key Configuration Sections

| Section | Key Settings |
|---------|-------------|
| **Trading** | `max_open_trades`, `stake_currency`, `stake_amount`, `trading_mode`, `margin_mode`, `timeframe` |
| **Strategy** | `minimal_roi`, `stoploss`, `trailing_stop`, `use_exit_signal` |
| **Orders** | `order_types`, `order_time_in_force`, `entry_pricing`, `exit_pricing` |
| **Exchange** | `name`, `key`, `secret`, `pair_whitelist`, `pair_blacklist`, `ccxt_config` |
| **Pairlists** | Array of filter/provider methods |
| **Protections** | Array of protection mechanisms |
| **RPC** | `telegram`, `api_server`, `webhook`, `discord` |
| **Data** | `datadir`, `dataformat_ohlcv`, `dataformat_trades` |
| **FreqAI** | ML model params, feature engineering, data split |
| **Internals** | `process_throttle_secs`, `heartbeat_interval`, `sd_notify` |

### 17.4 Validation

Two-phase validation:
- **Phase 1**: JSON Schema validation with mode-specific required fields
- **Phase 2**: Consistency checks (trailing stop logic, price config, unlimited stake conflicts, FreqAI validation, etc.)

---

## 18. Dependencies & Tech Stack

### Core Runtime

| Package | Version | Purpose |
|---------|---------|---------|
| `ccxt` | >=4.5.4 | Unified crypto exchange API |
| `SQLAlchemy` | >=2.0.6 | ORM + database |
| `pandas` | >=2.2.0 | Data manipulation |
| `numpy` | >2.0,<3.0 | Numerical computing |
| `fastapi` | — | REST API framework |
| `pydantic` | >=2.2.0 | Data validation |
| `uvicorn` | — | ASGI server |
| `python-telegram-bot` | >=20.1 | Telegram integration |
| `TA-Lib` | <0.7 | Technical analysis indicators |
| `ft-pandas-ta` | — | Additional TA indicators |
| `pyarrow` | — | Feather/Parquet data format |
| `websockets` | — | WebSocket support |
| `aiohttp` | — | Async HTTP |
| `httpx` | — | HTTP client |
| `orjson` | — | Fast JSON serialization |
| `rapidjson` | — | Fast JSON |
| `rich` | — | CLI formatting |
| `pycoingecko` | — | Fiat conversion |
| `cryptography` | — | JWT support |
| `schedule` | — | Scheduled tasks |
| `psutil` | — | System monitoring |

### Optional Dependencies

| Group | Packages |
|-------|----------|
| `[plot]` | plotly |
| `[hyperopt]` | optuna (>4.0), scikit-learn, cmaes |
| `[freqai]` | scikit-learn, lightgbm, xgboost, tensorboard, datasieve |
| `[freqai_rl]` | torch, gymnasium, stable-baselines3, sb3-contrib |
| `[develop]` | pytest, ruff, mypy, pre-commit, time-machine |

### Dev Tools

- **Linting**: Ruff (extensive rules)
- **Type checking**: mypy + Pyright
- **Testing**: pytest (asyncio, xdist, timeout, coverage)
- **CI/CD**: GitHub Actions
- **Docs**: MkDocs
- **Containerization**: Multi-variant Docker (standard, ARM, GPU, Jupyter, Plot)

---

## 19. Gap Analysis: Freqtrade vs Custom Tabdeal Bot Requirements

This section maps each of your 4-phase requirements against Freqtrade's existing capabilities.

### Phase 0: Raw Ledger Ingestion

| Requirement | Freqtrade Status | Details |
|-------------|-----------------|---------|
| Append-only Raw Trade Ledger | **NOT BUILT** | Trades stored as aggregated OHLCV in files. No per-trade raw ledger. |
| Special_margin/broadcast WS ingestion | **NOT BUILT** | WebSocket only for OHLCV (`watchOHLCV`). No raw trade stream subscription. |
| Parquet/SQLite raw storage | **PARTIAL** | Has Parquet handler but for OHLCV, not raw trades. Trade converter exists but is one-shot, not streaming. |
| 1-second tick capture | **NOT BUILT** | Minimum timeframe is 1m. No sub-minute ingestion. |

### Phase 1: Multi-Timeframe Candle Engine

| Requirement | Freqtrade Status | Details |
|-------------|-----------------|---------|
| In-memory candle aggregation | **PARTIAL** | `trades_to_ohlcv()` converts trades→candles but is batch, not real-time streaming. |
| 1s to 1Y timeframes | **PARTIAL** | Supports standard timeframes (1m to 1w). No 1s. No 1Y. |
| Hot Path priority routing | **NOT BUILT** | All timeframes processed equally in DataProvider. No priority queue. |
| Cold Path async computation | **NOT BUILT** | No background candle building for secondary timeframes. |
| Liveness Heartbeat (depth stream) | **NOT BUILT** | No order book depth subscription for heartbeat. |
| Quality Tagging (CLEAN/FLAT/SUSPECT/MISSING) | **NOT BUILT** | `ohlcv_fill_up_missing_data()` silently forward-fills. No quality tags. |

### Phase 2: Self-Heal Protocol

| Requirement | Freqtrade Status | Details |
|-------------|-----------------|---------|
| Halt on SUSPECT/MISSING data | **OPPOSITE** | System forward-fills by design. No halt mechanism. |
| Query Raw Ledger to patch gaps | **NOT BUILT** | No raw ledger to query. |
| Recalculate missed bars | **NOT BUILT** | No incremental bar recalculation. |
| Re-warm stateful indicators | **PARTIAL** | `startup_candle_count` provides initial warmup, but no re-warm after gap. |
| Autonomous resume | **NOT BUILT** | No self-heal state machine. |

### Phase 3: Execution Module

| Requirement | Freqtrade Status | Details |
|-------------|-----------------|---------|
| Tabdeal FAPI adapter | **NOT BUILT** | 20+ exchanges supported, but Tabdeal is not among them. |
| DELETE /position endpoint | **NOT BUILT** | Uses opposite-side orders with `reduceOnly` flag. Tabdeal doesn't support reduceOnly. |
| One In-Flight Order Mutex | **NOT BUILT** | Orders are fire-and-forget with timeout cleanup. No per-symbol mutex. |
| Timeout reconciliation | **NOT BUILT** | `manage_open_orders()` cancels on timeout but doesn't query exchange to reconcile state. |

### Phase 4: Watchdog (Split-Brain Prevention)

| Requirement | Freqtrade Status | Details |
|-------------|-----------------|---------|
| Isolated Watchdog process | **NOT BUILT** | Single-process architecture. |
| Time-fencing (T_self=6s, T_dead=15s) | **NOT BUILT** | No heartbeat-based fencing. |
| Write-Ahead Intent protocol | **NOT BUILT** | No intent signaling before order placement. |
| Independent SL placement by Watchdog | **NOT BUILT** | Only main bot places orders. |

### What Freqtrade DOES Well (Worth Copying)

| Capability | Quality | Notes |
|------------|---------|-------|
| Strategy interface pattern | **Excellent** | Clean ABC with 15+ hooks, safe wrapper, hyperopt params |
| Plugin resolver pattern | **Excellent** | Dynamic class loading from filesystem, works for any plugin type |
| DB schema (trades/orders) | **Very Good** | Comprehensive, handles futures, DCA, custom data |
| REST API (FastAPI) | **Excellent** | 60+ endpoints, JWT auth, WebSocket, background tasks |
| Telegram bot | **Excellent** | 30+ commands, inline keyboards, per-type notifications |
| Configuration system | **Very Good** | Multi-layer (JSON + env + CLI + schema validation) |
| Protection system | **Good** | 4 plugins, extensible |
| Pairlist filter chain | **Good** | Chain-of-Responsibility, 22 handlers |
| Backtesting fidelity | **Very Good** | Anti-lookahead, detail timeframes, funding fees |
| Hyperopt | **Very Good** | Optuna backend, 13 loss functions, parallel |

---

## 20. What to Borrow vs What to Build Fresh

### Borrow from Freqtrade (Patterns Worth Copying)

#### 1. Strategy Interface Pattern

```
Your equivalent:
├── IStrategy (ABC)
│   ├── populate_indicators(dataframe, metadata) → DataFrame
│   ├── populate_entry_trend(dataframe, metadata) → DataFrame
│   ├── populate_exit_trend(dataframe, metadata) → DataFrame
│   ├── custom_stoploss(pair, trade, current_rate, current_profit)
│   ├── custom_exit(pair, trade, current_rate, current_profit)
│   ├── confirm_trade_entry(pair, amount, rate)
│   └── confirm_trade_exit(pair, trade, order_type)
```

**Why borrow**: Proven pattern, 15+ hooks cover almost all use cases, safe wrapper prevents strategy errors from crashing the bot.

#### 2. Plugin Resolver Pattern

```python
# Your equivalent:
class IResolver:
    @classmethod
    def load_object(cls, object_type, search_paths, ...):
        for path in search_paths:
            for file in path.glob("*.py"):
                module = importlib.util.spec_from_file_location(...)
                for name, obj in inspect.getmembers(module):
                    if isinstance(obj, type) and issubclass(obj, object_type):
                        return obj(**kwargs)
```

**Why borrow**: Works for any extensible component — exchange adapters, strategy types, protection handlers, data handlers.

#### 3. Database Schema (Trades/Orders)

Copy and modify:
- `trades` table: all columns relevant (exchange, pair, stake, amount, rates, fees, stoploss, leverage, funding_fees)
- `orders` table: order lifecycle tracking
- `pairlocks` table: for your watchdog's lock mechanism
- `trade_custom_data` table: for Write-Ahead Intent storage

**Modify**: Add columns for:
- `quality_tag` (CLEAN/FLAT/SUSPECT/MISSING)
- `raw_ledger_id` (link to raw trade ledger)
- `watchdog_intent_id` (link to watchdog intent log)

#### 4. RPC/API Architecture

Copy the three-layer pattern:
```
TradingEngine → RPC(business logic) → RPCManager(dispatch) → Handlers(Telegram/API/Webhook)
```

**Why borrow**: Clean separation of concerns, adding new notification channels is trivial.

#### 5. Configuration System

Copy the multi-layer approach: JSON → env vars → CLI → schema validation.

#### 6. Pairlist Chain Pattern

Chain of Responsibility for filtering trading pairs — easy to extend.

#### 7. Protection System

CooldownPeriod and StoplossGuard patterns are directly reusable.

---

### Build Fresh (Freqtrade Cannot Help)

#### 1. Tabdeal FAPI Exchange Adapter

```python
class TabdealFAPI(Exchange):
    """Custom exchange adapter for Tabdeal Futures API."""

    def create_order(self, pair, ordertype, side, amount, rate, ...):
        # Tabdeal-specific order creation
        pass

    def delete_position(self, pair, side):
        """DELETE /fapi/v1/position — flatten server-side.
        This is the key Tabdeal-specific method that doesn't exist in CCXT."""
        pass

    def subscribe_trades_ws(self, pair):
        """Subscribe to special_margin/broadcast websocket for raw trades."""
        pass

    def subscribe_depth_ws(self, pair):
        """Subscribe to order book depth for liveness heartbeat."""
        pass
```

#### 2. Raw Trade Ledger Service

```python
class RawTradeLedger:
    """Append-only store for every executed trade from the WS stream."""

    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self._create_table()

    def _create_table(self):
        """CREATE TABLE raw_trades (
            id INTEGER PRIMARY KEY,
            timestamp_ms INTEGER,
            pair TEXT,
            price REAL,
            amount REAL,
            side TEXT,
            trade_id TEXT UNIQUE
        )"""

    def ingest(self, trade: dict):
        """Append a single trade. Idempotent via UNIQUE trade_id."""
        pass

    def query_window(self, pair, start_ms, end_ms):
        """Query trades in a time window for gap patching."""
        pass
```

#### 3. Multi-Timeframe Candle Aggregator

```python
class CandleAggregator:
    """Real-time in-memory candle builder from raw trade stream."""

    def __init__(self):
        self.candles = {}  # {(pair, timeframe): [candle, ...]}
        self.hot_path = "1m"  # Strategy's primary timeframe

    def on_trade(self, trade):
        """Called for every raw trade from WS."""
        for timeframe in self.active_timeframes:
            self._update_candle(trade.pair, timeframe, trade)

        if trade.timeframe == self.hot_path:
            self._emit_hot(trade.pair)  # Sub-millisecond callback

    def _update_candle(self, pair, timeframe, trade):
        """Update OHLCV candle for the given timeframe."""
        pass

    def get_candles(self, pair, timeframe, count):
        """Return last N candles (from memory or recalculate from ledger)."""
        pass
```

#### 4. Data Quality Engine

```python
class DataQualityTagger:
    """Tags every candle with a quality indicator."""

    def tag_candle(self, candle, expected_interval):
        if candle is None:
            return "MISSING"
        if candle.volume == 0 and candle.open == candle.close:
            return "FLAT"
        if self._has_jitter(candle, expected_interval):
            return "SUSPECT"
        return "CLEAN"

    def _has_jitter(self, candle, expected_interval):
        """Check if candle timing or data suggests dropped frames."""
        pass
```

#### 5. Halt & Self-Heal Protocol

```python
class HaltController:
    """State machine: RUNNING → HALTING → HEALING → RUNNING."""

    def on_candle(self, candle, quality_tag):
        if quality_tag in ("SUSPECT", "MISSING"):
            self._halt("Data quality degraded")

    def _halt(self, reason):
        """Immediately stop placing new orders."""
        self.state = "HALTING"
        self._cancel_all_pending_orders()

    def _heal(self):
        """Query raw ledger, patch gaps, re-warm indicators."""
        self.state = "HEALING"
        gaps = self._find_gaps()
        for gap in gaps:
            raw_trades = self.ledger.query_window(gap.pair, gap.start, gap.end)
            candles = self.aggregator.recalculate(raw_trades, gap.timeframe)
            self.strategy.re_warm(candles)

        if self._verify_continuity():
            self.state = "RUNNING"
```

#### 6. Mutex-Locked Order Execution

```python
class OrderExecutor:
    """Per-symbol mutex prevents concurrent orders."""

    def __init__(self):
        self.locks = {}  # {pair: asyncio.Lock}

    async def execute(self, pair, order):
        lock = self.locks.setdefault(pair, asyncio.Lock())
        async with lock:
            try:
                result = await self.exchange.create_order(order)
                return result
            except TimeoutError:
                # Known order is in-flight. Query exchange to reconcile.
                status = await self.exchange.query_order(order.id)
                if status == "FILLED":
                    return status
                elif status == "NEW":
                    await self.exchange.cancel_order(order.id)
                # DO NOT blindly retry
```

#### 7. Watchdog Service

```python
class Watchdog:
    """Isolated process with time-fencing and Write-Ahead Intent."""

    T_DEAD = 15  # seconds

    async def run(self):
        while True:
            last_ping = await self._get_last_ping()
            age = (now() - last_ping).total_seconds()

            if age > self.T_DEAD:
                # Main bot is mathematically dead (T_self=6s < T_dead=15s)
                await self._flatten_all_positions()
                await self._set_global_lock()

            await self._check_unprotected_positions()
            await asyncio.sleep(1)

    async def _check_unprotected_positions(self):
        """If position exists without SL, check intent log."""
        positions = await self.exchange.get_positions()
        intents = await self.db.get_pending_intents()

        for pos in positions:
            if not self._has_sl(pos):
                intent = intents.find(pos.pair, pos.side)
                if intent:
                    await self._place_sl(pos, intent.sl_price)
```

#### 8. Write-Ahead Intent Protocol

```python
class IntentLogger:
    """Logs trading intent before order placement."""

    async def log_intent(self, pair, side, amount, sl_price, sl_type):
        """Call BEFORE placing the market order."""
        await self.db.insert({
            "pair": pair,
            "side": side,
            "amount": amount,
            "sl_price": sl_price,
            "sl_type": sl_type,
            "status": "PENDING",
            "created_at": now()
        })

    async def mark_filled(self, pair, side, order_id):
        """Call AFTER order fill confirmed."""
        await self.db.update(pair, side, {"status": "FILLED", "order_id": order_id})

    async def get_stale_intents(self, max_age_seconds=30):
        """Find PENDING intents older than threshold — likely crashed during naked window."""
        pass
```

---

## 21. Recommendations for Custom Build

### Architecture Overview

Based on the analysis, here is the recommended architecture for your custom Tabdeal FAPI bot:

```
┌────────────────────────────────────────────────────────────────┐
│                    Tabdeal FAPI Trading Bot                     │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐     ┌──────────────────────────────┐  │
│  │  Raw Trade Ingestion │     │   Order Book Heartbeat        │  │
│  │  (special_margin WS) │     │   (depth WS)                  │  │
│  └──────────┬──────────┘     └──────────┬───────────────────┘  │
│             │                            │                       │
│             ▼                            ▼                       │
│  ┌─────────────────────┐     ┌──────────────────────────────┐  │
│  │  Raw Trade Ledger    │     │   Liveness Monitor            │  │
│  │  (append-only DB)    │     │   (trades stopped + depth OK  │  │
│  └──────────┬──────────┘     │    = FLAT market)              │  │
│             │                 └──────────────────────────────┘  │
│             ▼                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │         Multi-Timeframe Candle Aggregator                │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │   │
│  │  │ Hot Path │  │ Cold Path│  │ Quality Tagger        │  │   │
│  │  │ (1m)     │  │ (5m-1Y)  │  │ (CLEAN/FLAT/SUSPECT)  │  │   │
│  │  └────┬─────┘  └──────────┘  └──────────────────────┘  │   │
│  └───────┼──────────────────────────────────────────────────┘   │
│          │                                                      │
│          ▼                                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Halt Controller                              │  │
│  │  RUNNING → (SUSPECT/MISSING) → HALTING → HEALING → RUN   │  │
│  │  On halt: cancel all pending orders, stop new entries     │  │
│  │  On heal: query ledger → patch gaps → re-warm indicators  │  │
│  └──────────┬───────────────────────────────────────────────┘  │
│             │                                                   │
│             ▼                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Strategy Engine                              │  │
│  │  (borrowed IStrategy pattern from Freqtrade)              │  │
│  │  populate_indicators / populate_entry / populate_exit     │  │
│  └──────────┬───────────────────────────────────────────────┘  │
│             │                                                   │
│             ▼                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Mutex-Locked Order Executor                       │  │
│  │  Per-symbol asyncio.Lock → prevents concurrent orders     │  │
│  │  Timeout → query exchange → reconcile → never blind retry  │  │
│  └──────────┬───────────────────────────────────────────────┘  │
│             │                                                   │
│             ├── Write-Ahead Intent → ┌───────────────────────┐  │
│             │                        │  Watchdog Service       │  │
│             └── Market Order ────────┤  (isolated process)     │  │
│                                      │  T_self=6s, T_dead=15s  │  │
│                                      │  Flatten on timeout      │  │
│                                      │  Set SL from intent      │  │
│                                      └───────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Tabdeal FAPI Exchange Adapter                │  │
│  │  create_order / DELETE /position / WS streams             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              RPC Layer (borrowed from Freqtrade)           │  │
│  │  Telegram + REST API (FastAPI) + WebSocket                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Persistence (SQLAlchemy + SQLite/Postgres)    │  │
│  │  trades | orders | pairlocks | custom_data | raw_ledger   │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### Implementation Priority Order

| Phase | Component | Estimated Complexity | Freqtrade Code to Reuse |
|-------|-----------|---------------------|------------------------|
| **Phase 0** | Raw Trade Ledger | Medium | `data/converter/trade_converter.py` (patterns), `persistence/` (DB schema) |
| **Phase 0** | Tabdeal FAPI Adapter | High | `exchange/exchange.py` (structure), but Tabdeal-specific code is new |
| **Phase 1** | Candle Aggregator | Medium-High | `data/converter/converter.py` (clean_ohlcv logic), `data/dataprovider.py` (serving pattern) |
| **Phase 1** | Quality Tagger | Low | New — no Freqtrade equivalent |
| **Phase 2** | Halt Controller | Medium | New — no Freqtrade equivalent |
| **Phase 2** | Self-Heal Protocol | Medium-High | New — no Freqtrade equivalent |
| **Phase 3** | DELETE Position Executor | Low | New — Tabdeal-specific |
| **Phase 3** | Mutex Order Executor | Medium | New — no Freqtrade equivalent |
| **Phase 4** | Watchdog Service | High | New — completely isolated |
| **Phase 4** | Write-Ahead Intent | Medium | New — no Freqtrade equivalent |
| **Always** | Strategy Interface | Low | Directly copy `strategy/interface.py` patterns |
| **Always** | RPC/API Layer | Medium | Directly copy `rpc/api_server/` structure |
| **Always** | Configuration System | Low | Directly copy `configuration/` system |
| **Always** | Database Schema | Low | Copy and extend `persistence/` models |

### Key Design Principles from Freqtrade Worth Adopting

1. **Safe Strategy Wrapper**: Every strategy callback is wrapped in exception handling that deep-copies trade objects and catches errors without crashing the bot.

2. **Scoped Sessions**: Thread-local + request-aware database sessions handle both threading and async contexts.

3. **Dual-Mode Trade Model**: Use `LocalTrade` (plain Python) for backtesting and `Trade` (SQLAlchemy) for live. Shared logic lives in the base class.

4. **Chain of Responsibility for Pairlists**: Easy to add/remove/reorder filter steps.

5. **Configurable Notification Granularity**: Per-message-type on/silent/off settings.

6. **Anti-Lookahead in Backtesting**: Signal columns shifted by 1 candle to prevent future information leakage.

7. **Progressive Throttling**: WebSocket sends throttled adaptively based on average send time.

### Key Design Principles Freqtrade LACKS (Your Differentiators)

1. **Deterministic Safety**: "Make dangerous states unreachable rather than recoverable." Freqtrade relies on heuristics; your system should enforce invariants.

2. **Data Integrity Over Market Participation**: Halt on bad data rather than forward-filling. Freqtrade does the opposite.

3. **One In-Flight Order**: Freqtrade has no mutex. Your mutex-per-symbol prevents double entries.

4. **Split-Brain Prevention**: Freqtrade is single-process. Your watchdog is mathematically guaranteed to act only when the main bot is dead.

5. **Write-Ahead Logging**: Freqtrade has no intent protocol. Your WAL-style intent log protects the naked window.

6. **Server-Side Position Flattening**: Freqtrade uses opposite-side orders (risky on Tabdeal). Your DELETE endpoint is safer.

---

## Appendix A: Key File Reference

| Component | File Path |
|-----------|-----------|
| Root entry point | `freqtrade/main.py` |
| Worker state machine | `freqtrade/worker.py` |
| Core trading engine | `freqtrade/freqtradebot.py` |
| Strategy base class | `freqtrade/strategy/interface.py` |
| Strategy safe wrapper | `freqtrade/strategy/strategy_wrapper.py` |
| Hyperopt parameters | `freqtrade/strategy/parameters.py` |
| Informative decorator | `freqtrade/strategy/informative_decorator.py` |
| Exchange base class | `freqtrade/exchange/exchange.py` |
| Exchange WebSocket | `freqtrade/exchange/exchange_ws.py` |
| Binance adapter | `freqtrade/exchange/binance.py` |
| Bybit adapter | `freqtrade/exchange/bybit.py` |
| Data download utils | `freqtrade/data/history/history_utils.py` |
| Data handler interface | `freqtrade/data/history/datahandlers/idatahandler.py` |
| Feather handler | `freqtrade/data/history/datahandlers/featherdatahandler.py` |
| OHLCV converter | `freqtrade/data/converter/converter.py` |
| Trade-to-OHLCV | `freqtrade/data/converter/trade_converter.py` |
| Orderflow | `freqtrade/data/converter/orderflow.py` |
| DataProvider | `freqtrade/data/dataprovider.py` |
| Performance metrics | `freqtrade/data/metrics.py` |
| Backtesting engine | `freqtrade/optimize/backtesting.py` |
| Hyperopt orchestrator | `freqtrade/optimize/hyperopt/hyperopt.py` |
| Hyperopt optimizer | `freqtrade/optimize/hyperopt/hyperopt_optimizer.py` |
| Backtest caching | `freqtrade/optimize/backtest_caching.py` |
| RPC core | `freqtrade/rpc/rpc.py` |
| RPC manager | `freqtrade/rpc/rpc_manager.py` |
| Telegram bot | `freqtrade/rpc/telegram.py` |
| REST API server | `freqtrade/rpc/api_server/webserver.py` |
| API auth | `freqtrade/rpc/api_server/api_auth.py` |
| API endpoints | `freqtrade/rpc/api_server/api_v1.py` |
| WebSocket system | `freqtrade/rpc/api_server/ws/channel.py` |
| Message stream | `freqtrade/rpc/api_server/ws/message_stream.py` |
| External consumer | `freqtrade/rpc/external_message_consumer.py` |
| Webhook | `freqtrade/rpc/webhook.py` |
| Discord | `freqtrade/rpc/discord.py` |
| Trade model | `freqtrade/persistence/trade_model.py` |
| Order model | `freqtrade/persistence/trade_model.py` (line 65-378) |
| PairLock model | `freqtrade/persistence/pairlock.py` |
| Custom data | `freqtrade/persistence/custom_data.py` |
| DB migrations | `freqtrade/persistence/migrations.py` |
| Key-value store | `freqtrade/persistence/key_value_store.py` |
| Wallet history | `freqtrade/persistence/wallet_history.py` |
| Models init | `freqtrade/persistence/models.py` |
| Pairlist manager | `freqtrade/plugins/pairlistmanager.py` |
| IPairList base | `freqtrade/plugins/pairlist/IPairList.py` |
| StaticPairList | `freqtrade/plugins/pairlist/StaticPairList.py` |
| VolumePairList | `freqtrade/plugins/pairlist/VolumePairList.py` |
| Protection manager | `freqtrade/plugins/protectionmanager.py` |
| IProtection base | `freqtrade/plugins/protections/iprotection.py` |
| StoplossGuard | `freqtrade/plugins/protections/stoploss_guard.py` |
| MaxDrawdown | `freqtrade/plugins/protections/max_drawdown.py` |
| Wallets | `freqtrade/wallets.py` |
| Resolver base | `freqtrade/resolvers/iresolver.py` |
| Strategy resolver | `freqtrade/resolvers/strategy_resolver.py` |
| Exchange resolver | `freqtrade/resolvers/exchange_resolver.py` |
| Configuration loader | `freqtrade/configuration/configuration.py` |
| Config validation | `freqtrade/configuration/config_validation.py` |
| JSON Schema | `freqtrade/config_schema/config_schema.py` |
| FreqAI interface | `freqtrade/freqai/freqai_interface.py` |
| Data kitchen | `freqtrade/freqai/data_kitchen.py` |
| Data drawer | `freqtrade/freqai/data_drawer.py` |
| All enums | `freqtrade/enums/` |
| Constants | `freqtrade/constants.py` |
| Exceptions | `freqtrade/exceptions.py` |
| Leverage calc | `freqtrade/leverage/liquidation_price.py` |
| Sample strategy | `freqtrade/templates/sample_strategy.py` |
| Full config example | `config_examples/config_full.example.json` |

---

## Appendix B: Freqtrade Statistics

| Metric | Value |
|--------|-------|
| Total Python files | ~200+ |
| Lines of code (core) | ~30,000+ |
| Largest file | `exchange.py` (~4,157 lines) |
| Second largest | `telegram.py` (~2,285 lines) |
| Third largest | `rpc.py` (~1,837 lines) |
| Strategy base class | ~1,903 lines |
| Backtesting engine | ~1,979 lines |
| Supported exchanges | 20+ |
| Pairlist handlers | 22 |
| Protection handlers | 4 |
| API endpoints | 60+ |
| Telegram commands | 30+ |
| Hyperopt loss functions | 13 |
| Database tables | 5 (+ KeyValueStore) |
| Enumeration files | 15 |
| Test files | 100+ |

---

*This document was generated by analyzing the complete freqtrade codebase (v2026.7-dev) at `/home/siavash/Projects/freqtrade/`. All code references, line counts, and architectural details are derived from direct source code inspection.*
