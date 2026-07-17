"""Walk-forward optimization."""
from __future__ import annotations

from apps.transpiler.engine import run_backtest

from .grid import grid_search


def walk_forward(
    source: str,
    df,
    param_grid: dict,
    *,
    train_bars: int,
    test_bars: int,
    base_kwargs: dict | None = None,
) -> list[dict]:
    """Rolling train/test windows with grid search on train, validate on test."""
    windows: list[dict] = []
    n = len(df)
    start = 0
    while start + train_bars + test_bars <= n:
        train_df = df.iloc[start : start + train_bars]
        test_df = df.iloc[start + train_bars : start + train_bars + test_bars]
        grid = grid_search(source, train_df, param_grid, base_kwargs=base_kwargs)
        best = grid[0] if grid else {"params": {}, "metrics": {}}
        test_result = run_backtest(source, test_df, **(base_kwargs or {}), **best["params"])
        windows.append(
            {
                "train_start": start,
                "test_start": start + train_bars,
                "best_params": best["params"],
                "train_metrics": best["metrics"],
                "test_metrics": test_result.metrics,
            }
        )
        start += test_bars
    return windows
