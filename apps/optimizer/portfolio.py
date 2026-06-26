"""Multi-asset portfolio backtest with aggregated equity and risk metrics."""
from __future__ import annotations

import math
from statistics import mean, pstdev

from apps.transpiler.engine import run_backtest


def _equity_returns(series: list[float]) -> list[float]:
    out = []
    for prev, cur in zip(series, series[1:]):
        out.append((cur - prev) / prev if prev else 0.0)
    return out


def _max_drawdown(series: list[float]) -> float:
    if len(series) < 2:
        return 0.0
    peak = series[0]
    dd = 0.0
    for eq in series:
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 8)


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    std = pstdev(returns)
    if std <= 0:
        return 0.0
    return round((mean(returns) / std) * math.sqrt(len(returns)), 4)


def _correlation(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 2:
        return None
    a, b = a[:n], b[:n]
    ma, mb = mean(a), mean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    return round(cov / math.sqrt(va * vb), 4)


def portfolio_backtest(
    strategies: list[dict],
    data: dict[str, object],
    *,
    initial_balance: float = 10_000.0,
) -> dict:
    """Run a backtest per symbol and aggregate into portfolio-level metrics.

    Each asset receives ``initial_balance``; the portfolio equity curve is the
    sum of per-asset equity curves (shared/pooled capital view), from which
    portfolio drawdown, Sharpe and per-asset return correlation are derived.
    """
    per_asset: list[dict] = []
    combined_pnl = 0.0
    equity_curves: dict[str, list[float]] = {}

    for item in strategies:
        symbol = item["symbol"]
        df = data.get(symbol)
        if df is None:
            continue
        result = run_backtest(item["source"], df, initial_balance=initial_balance, **item.get("kwargs", {}))
        metrics = result.metrics
        combined_pnl += metrics.get("net_pnl", 0)
        curve = metrics.get("equity_series") or []
        if curve:
            equity_curves[symbol] = curve
        per_asset.append({"symbol": symbol, "metrics": metrics})

    # Aligned combined equity curve (truncate to shortest asset history).
    combined_series: list[float] = []
    if equity_curves:
        min_len = min(len(c) for c in equity_curves.values())
        for i in range(min_len):
            combined_series.append(sum(c[i] for c in equity_curves.values()))

    # Pairwise correlation of per-asset equity returns.
    returns = {sym: _equity_returns(c) for sym, c in equity_curves.items()}
    correlation: dict[str, float | None] = {}
    symbols = list(returns.keys())
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            key = f"{symbols[i]}|{symbols[j]}"
            correlation[key] = _correlation(returns[symbols[i]], returns[symbols[j]])

    port_initial = initial_balance * len(equity_curves) if equity_curves else initial_balance
    port_final = combined_series[-1] if combined_series else port_initial

    return {
        "combined_net_pnl": round(combined_pnl, 8),
        "assets": per_asset,
        "num_assets": len(per_asset),
        "equity_series": [round(x, 4) for x in combined_series],
        "portfolio": {
            "initial_balance": round(port_initial, 8),
            "final_equity": round(port_final, 8),
            "return_pct": round((port_final - port_initial) / port_initial * 100.0, 4) if port_initial else 0.0,
            "max_drawdown": _max_drawdown(combined_series),
            "sharpe_ratio": _sharpe(_equity_returns(combined_series)),
        },
        "correlation": correlation,
    }
