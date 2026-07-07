"""Tests for the optimizer (grid, walk-forward, monte-carlo, portfolio)."""
import pandas as pd

from apps.optimizer.grid import grid_search
from apps.optimizer.monte_carlo import monte_carlo_equity
from apps.optimizer.portfolio import portfolio_backtest
from apps.optimizer.walk_forward import walk_forward


def _df(n=120, start=100.0):
    rows = []
    for i in range(n):
        c = start + (i % 10)  # oscillating closes so crossover strategies trade
        rows.append({"ts": 1000 + i, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 10})
    return pd.DataFrame(rows)


SMA_CROSS = (
    'strategy("x", overlay=true)\n'
    "fast = ta.sma(close, 3)\n"
    "slow = ta.sma(close, 8)\n"
    "if ta.crossover(fast, slow)\n"
    '    strategy.entry("long", strategy.long)\n'
    "if ta.crossunder(fast, slow)\n"
    '    strategy.close("long")\n'
)


def test_grid_search_returns_sorted_results():
    results = grid_search(SMA_CROSS, _df(), {"default_qty": [1.0, 2.0, 3.0]})
    assert len(results) == 3
    # each result carries its params + metrics
    assert set(results[0]["params"].keys()) == {"default_qty"}
    assert "net_pnl" in results[0]["metrics"]
    # sorted descending by net_pnl
    pnls = [r["metrics"]["net_pnl"] for r in results]
    assert pnls == sorted(pnls, reverse=True)


def test_grid_search_multi_dimensional():
    results = grid_search(SMA_CROSS, _df(), {"default_qty": [1.0, 2.0], "leverage": [1.0, 2.0]})
    assert len(results) == 4  # cartesian product


def test_walk_forward_window_math():
    df = _df(300)
    windows = walk_forward(SMA_CROSS, df, {"default_qty": [1.0, 2.0]}, train_bars=100, test_bars=50)
    # (300 - 100) // 50 = 4 rolling windows
    assert len(windows) == 4
    first = windows[0]
    assert first["train_start"] == 0
    assert first["test_start"] == 100
    assert "best_params" in first
    assert "test_metrics" in first
    # windows advance by test_bars
    assert windows[1]["train_start"] == 50


def test_monte_carlo_percentiles_ordered():
    pnls = [10.0, -5.0, 7.0, -3.0, 12.0, -8.0]
    out = monte_carlo_equity(pnls, initial_balance=1_000.0, simulations=200)
    assert out["simulations"] == 200
    assert out["p5_final"] <= out["median_final"] <= out["p95_final"]
    # sum of pnls is path-independent -> every shuffle ends identically
    assert out["median_final"] == 1_000.0 + sum(pnls)


def test_monte_carlo_empty():
    out = monte_carlo_equity([], initial_balance=5_000.0)
    assert out["simulations"] == 0
    assert out["median_final"] == 5_000.0


def test_portfolio_backtest_aggregates():
    data = {"BTC": _df(120, start=100), "ETH": _df(120, start=50)}
    strategies = [
        {"symbol": "BTC", "source": SMA_CROSS},
        {"symbol": "ETH", "source": SMA_CROSS},
    ]
    out = portfolio_backtest(strategies, data)
    assert out["num_assets"] == 2
    assert {a["symbol"] for a in out["assets"]} == {"BTC", "ETH"}
    expected = round(sum(a["metrics"]["net_pnl"] for a in out["assets"]), 8)
    assert out["combined_net_pnl"] == expected


def test_portfolio_reports_risk_metrics_and_correlation():
    data = {"BTC": _df(120, start=100), "ETH": _df(120, start=50)}
    strategies = [
        {"symbol": "BTC", "source": SMA_CROSS},
        {"symbol": "ETH", "source": SMA_CROSS},
    ]
    out = portfolio_backtest(strategies, data)
    assert "portfolio" in out
    p = out["portfolio"]
    assert set(p.keys()) == {"initial_balance", "final_equity", "return_pct", "max_drawdown", "sharpe_ratio"}
    assert p["initial_balance"] == 20_000.0  # 2 assets x 10k
    assert isinstance(out["equity_series"], list)
    # one correlation pair for two assets
    assert "BTC|ETH" in out["correlation"]


def test_portfolio_skips_missing_data():
    out = portfolio_backtest(
        [{"symbol": "BTC", "source": SMA_CROSS}, {"symbol": "ETH", "source": SMA_CROSS}],
        {"BTC": _df(120)},  # ETH missing
    )
    assert out["num_assets"] == 1
