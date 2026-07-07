"""Monte Carlo simulation on trade returns."""
from __future__ import annotations

import random


def monte_carlo_equity(
    trade_pnls: list[float],
    *,
    seed: int | None = None,
    initial_balance: float = 10_000.0,
    simulations: int = 1000,
) -> dict:
    """Bootstrap shuffled trade sequences and compute equity distribution."""
    if not trade_pnls:
        return {"simulations": 0, "median_final": initial_balance, "p5_final": initial_balance, "p95_final": initial_balance}

    rng = random.Random(seed)
    finals: list[float] = []
    for _ in range(simulations):
        shuffled = trade_pnls[:]
        rng.shuffle(shuffled)
        equity = initial_balance
        for pnl in shuffled:
            equity += pnl
        finals.append(equity)
    finals.sort()
    return {
        "simulations": simulations,
        "median_final": round(finals[len(finals) // 2], 4),
        "p5_final": round(finals[int(len(finals) * 0.05)], 4),
        "p95_final": round(finals[int(len(finals) * 0.95)], 4),
    }
