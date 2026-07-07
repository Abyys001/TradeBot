"""Extended backtest performance metrics."""
from __future__ import annotations

import math
from statistics import mean, pstdev


def _trade_val(trade, key: str) -> float:
    if isinstance(trade, dict):
        return float(trade.get(key, 0))
    return float(getattr(trade, key, 0))


def compute_metrics(
    closed_trades: list,
    *,
    equity_series: list[float] | None = None,
    initial_balance: float = 10_000.0,
    funding_paid: float = 0.0,
) -> dict:
    """Compute rich metrics from closed trade dicts and optional equity curve."""
    n = len(closed_trades)
    if n == 0:
        return {
            "num_trades": 0,
            "net_pnl": 0.0,
            "gross_pnl": 0.0,
            "total_commission": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "avg_trade": 0.0,
            "risk_reward": 0.0,
            "expectancy": 0.0,
            "funding_paid": round(funding_paid, 8),
        }

    net = sum(_trade_val(t, "pnl") for t in closed_trades)
    gross = sum(_trade_val(t, "gross_pnl") for t in closed_trades)
    commission = sum(_trade_val(t, "commission") for t in closed_trades)
    wins = [t for t in closed_trades if _trade_val(t, "pnl") > 0]
    losses = [t for t in closed_trades if _trade_val(t, "pnl") <= 0]

    gross_profit = sum(_trade_val(t, "pnl") for t in wins) if wins else 0.0
    gross_loss = abs(sum(_trade_val(t, "pnl") for t in losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    avg_win = mean([_trade_val(t, "pnl") for t in wins]) if wins else 0.0
    avg_loss = abs(mean([_trade_val(t, "pnl") for t in losses])) if losses else 0.0
    risk_reward = avg_win / avg_loss if avg_loss > 0 else 0.0

    # Max drawdown as percentage of peak equity
    max_dd = 0.0
    if equity_series and len(equity_series) > 1:
        peak = equity_series[0]
        for eq in equity_series:
            peak = max(peak, eq)
            if peak > 0:
                max_dd = min(max_dd, (eq - peak) / peak * 100)
    else:
        equity, peak = initial_balance, initial_balance
        for t in closed_trades:
            pnl = _trade_val(t, "pnl")
            equity += pnl
            peak = max(peak, equity)
            if peak > 0:
                max_dd = min(max_dd, (equity - peak) / peak * 100)

    # Sharpe from per-trade returns vs initial balance
    returns = []
    for t in closed_trades:
        pnl = _trade_val(t, "pnl")
        returns.append(pnl / initial_balance if initial_balance else 0.0)
    sharpe = 0.0
    if len(returns) > 1:
        std = pstdev(returns)
        if std > 0:
            sharpe = (mean(returns) / std) * math.sqrt(len(returns))

    win_rate = len(wins) / n
    expectancy = net / n

    return {
        "num_trades": n,
        "net_pnl": round(net, 8),
        "gross_pnl": round(gross, 8),
        "total_commission": round(commission, 8),
        "win_rate": round(win_rate, 4),
        "max_drawdown": round(max_dd, 8),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else None,
        "sharpe_ratio": round(sharpe, 4),
        "avg_trade": round(expectancy, 8),
        "risk_reward": round(risk_reward, 4),
        "expectancy": round(expectancy, 8),
        "funding_paid": round(funding_paid, 8),
    }
