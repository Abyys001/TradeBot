"""Grid search over strategy parameters."""
from __future__ import annotations

import itertools
from typing import Any

from apps.transpiler.engine import run_backtest


def grid_search(
    source: str,
    df,
    param_grid: dict[str, list[Any]],
    *,
    base_kwargs: dict | None = None,
) -> list[dict]:
    """Run backtests for every combination in param_grid."""
    keys = list(param_grid.keys())
    results: list[dict] = []
    for values in itertools.product(*(param_grid[k] for k in keys)):
        params = dict(zip(keys, values))
        kwargs = {**(base_kwargs or {}), **params}
        result = run_backtest(source, df, **kwargs)
        results.append({"params": params, "metrics": result.metrics})
    results.sort(key=lambda r: r["metrics"].get("net_pnl", 0), reverse=True)
    return results
