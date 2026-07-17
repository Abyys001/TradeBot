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
    return _s(x).ewm(span=int(length), adjust=False).mean().to_numpy()


def rma(x, length: int):
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


def tr(high, low, close):
    h, l, c = _s(high), _s(low), _s(close)
    prev_c = c.shift(1)
    ranges = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1)
    return ranges.max(axis=1).to_numpy()


def atr(high, low, close, length: int):
    return rma(tr(high, low, close), length)


def change(x, length: int = 1):
    s = _s(x)
    return (s - s.shift(int(length))).to_numpy()


def mom(x, length: int):
    return change(x, length)


def roc(x, length: int):
    s = _s(x)
    prev = s.shift(int(length))
    return ((s - prev) / prev * 100.0).to_numpy()


def stdev(x, length: int):
    return _s(x).rolling(int(length)).std(ddof=0).to_numpy()


def variance(x, length: int):
    return _s(x).rolling(int(length)).var(ddof=0).to_numpy()


def wma(x, length: int):
    length = int(length)
    weights = np.arange(1, length + 1, dtype="float64")
    denom = weights.sum()

    def _wma(window):
        if len(window) < length:
            return np.nan
        return float(np.dot(window[-length:], weights) / denom)

    return _s(x).rolling(length).apply(_wma, raw=True).to_numpy()


def hma(x, length: int):
    length = int(length)
    half = max(length // 2, 1)
    sqrt_len = max(int(np.sqrt(length)), 1)
    wma_half = wma(x, half)
    wma_full = wma(x, length)
    diff = 2.0 * wma_half - wma_full
    return wma(diff, sqrt_len)


def cci(src, length: int):
    s = _s(src)
    length = int(length)
    sma_tp = s.rolling(length).mean()
    mad = s.rolling(length).apply(lambda w: np.mean(np.abs(w - w.mean())), raw=True)
    return ((s - sma_tp) / (0.015 * mad)).to_numpy()


def vwap(hlc3, volume):
    h, v = _s(hlc3), _s(volume)
    cum_pv = (h * v).cumsum()
    cum_v = v.cumsum()
    out = cum_pv / cum_v.replace(0, np.nan)
    return out.to_numpy()


def vwma(src, volume, length: int):
    s, v = _s(src), _s(volume)
    length = int(length)
    pv = (s * v).rolling(length).sum()
    vol = v.rolling(length).sum()
    return (pv / vol.replace(0, np.nan)).to_numpy()


def rising(src, length: int):
    s = _s(src)
    rising_bar = s.diff() > 0
    return rising_bar.rolling(int(length)).min().fillna(0).astype(bool).to_numpy()


def falling(src, length: int):
    s = _s(src)
    falling_bar = s.diff() < 0
    return falling_bar.rolling(int(length)).min().fillna(0).astype(bool).to_numpy()


def macd(src, fast: int, slow: int, sig: int):
    fast_ema = ema(src, fast)
    slow_ema = ema(src, slow)
    macd_line = fast_ema - slow_ema
    signal = ema(macd_line, sig)
    hist = macd_line - signal
    return macd_line, signal, hist


def bb(src, length: int, mult: float):
    basis = sma(src, length)
    dev = stdev(src, length)
    upper = basis + mult * dev
    lower = basis - mult * dev
    return basis, upper, lower


def stoch(close, high, low, length: int):
    c, h, l = _s(close), _s(high), _s(low)
    length = int(length)
    lowest_low = l.rolling(length).min()
    highest_high = h.rolling(length).max()
    span = highest_high - lowest_low
    k = 100.0 * (c - lowest_low) / span.replace(0, np.nan)
    return (k.to_numpy(),)


REGISTRY = {
    "sma": sma, "ema": ema, "rma": rma, "rsi": rsi,
    "crossover": crossover, "crossunder": crossunder,
    "highest": highest, "lowest": lowest,
    "tr": tr, "atr": atr, "change": change, "mom": mom, "roc": roc,
    "stdev": stdev, "variance": variance, "cci": cci, "wma": wma, "hma": hma,
    "vwap": vwap, "vwma": vwma, "rising": rising, "falling": falling,
}

# name -> (callable, return_count)
MULTI_REGISTRY = {
    "macd": (macd, 3),
    "bb": (bb, 3),
    "stoch": (stoch, 1),
}

# Indicators that use implicit OHLC from context (no series arg in Pine).
OHLC_IMPLICIT = {"tr", "atr"}

# Indicators that need high/low/close arrays from context.
HLC_INDICATORS = {"tr", "atr", "stoch"}
