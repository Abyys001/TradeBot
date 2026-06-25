"""Execution context shared across the bar loop."""
from __future__ import annotations

import numpy as np

NA = float("nan")

# Derived price series Pine exposes as builtins.
DERIVED = {
    "hl2": lambda df: (df["high"] + df["low"]) / 2.0,
    "hlc3": lambda df: (df["high"] + df["low"] + df["close"]) / 3.0,
    "ohlc4": lambda df: (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0,
    "hlcc4": lambda df: (df["high"] + df["low"] + df["close"] * 2.0) / 4.0,
}


def is_na(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v))


class SeriesBuffer:
    """History buffer for a path-dependent (`var`/`varip`/`:=`) variable."""

    def __init__(self):
        self.values: list = []
        self.current = NA  # value for the bar currently executing

    def get(self, n: int):
        idx = len(self.values) - 1 - n
        return self.values[idx] if 0 <= idx < len(self.values) else NA

    def commit(self):
        self.values.append(self.current)


class ExecutionContext:
    def __init__(self, df, broker, *, header=None):
        self.df = df.reset_index(drop=True)
        self.n = len(self.df)
        self.broker = broker
        self.header = header
        self.bar_index = 0

        # Base + derived columns as float arrays.
        self.arrays: dict[str, np.ndarray] = {}
        for col in ("open", "high", "low", "close", "volume"):
            if col in self.df.columns:
                self.arrays[col] = self.df[col].to_numpy(dtype="float64")
        if "ts" in self.df.columns:
            self.arrays["ts"] = self.df["ts"].to_numpy(dtype="int64")
        for name, fn in DERIVED.items():
            try:
                self.arrays[name] = fn(self.df).to_numpy(dtype="float64")
            except KeyError:
                pass

        # Path-dependent scalar variables.
        self.scalars: dict[str, SeriesBuffer] = {}
        # User-defined functions (name -> FunctionDefNode), set by interpreter.run.
        self.functions: dict = {}
        # Per-call-site state for barssince / valuewhen / cum.
        self.bar_state: dict = {}
        # Cache of vectorized expression results, keyed by id(node).
        self._array_cache: dict[int, np.ndarray] = {}

    @property
    def close_price(self) -> float:
        return float(self.arrays["close"][self.bar_index])

    def refresh_df(self, df) -> None:
        """Rebuild OHLCV arrays after the sliding window changes."""
        self.df = df.reset_index(drop=True)
        self.n = len(self.df)
        self._array_cache.clear()
        for col in ("open", "high", "low", "close", "volume"):
            if col in self.df.columns:
                self.arrays[col] = self.df[col].to_numpy(dtype="float64")
        for name, fn in DERIVED.items():
            try:
                self.arrays[name] = fn(self.df).to_numpy(dtype="float64")
            except KeyError:
                pass
