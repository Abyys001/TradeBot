"""Vectorized `ta.*` indicators (NumPy/pandas).

Each takes/returns a 1-D NumPy float array aligned to the OHLCV frame, with
NaN during the warm-up window — matching Pine's `na` lead-in. These are the
"vectorized" half of the hybrid model: computed once over the whole series,
then indexed per bar by the interpreter.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _s(x) -> pd.Series:
    return pd.Series(np.asarray(x, dtype="float64"))


def sma(x, length: int):
    return _s(x).rolling(int(length)).mean().to_numpy()


def ema(x, length: int):
    # Pine ema: alpha = 2/(length+1), no bias correction.
    return _s(x).ewm(span=int(length), adjust=False).mean().to_numpy()


def rma(x, length: int):
    # Wilder's smoothing: alpha = 1/length.
    return _s(x).ewm(alpha=1.0 / int(length), adjust=False).mean().to_numpy()


def rsi(x, length: int):
    s = _s(x)
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / int(length), adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / int(length), adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(avg_loss != 0.0, 100.0)
    return out.to_numpy()


def crossover(a, b):
    a, b = _s(a), _s(b)
    out = (a > b) & (a.shift(1) <= b.shift(1))
    return out.to_numpy()


def crossunder(a, b):
    a, b = _s(a), _s(b)
    out = (a < b) & (a.shift(1) >= b.shift(1))
    return out.to_numpy()


def highest(x, length: int):
    return _s(x).rolling(int(length)).max().to_numpy()


def lowest(x, length: int):
    return _s(x).rolling(int(length)).min().to_numpy()


# Dispatch table: name -> (callable, positional arg count incl. source).
REGISTRY = {
    "sma": sma, "ema": ema, "rma": rma, "rsi": rsi,
    "crossover": crossover, "crossunder": crossunder,
    "highest": highest, "lowest": lowest,
}
