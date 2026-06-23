"""Scalar `math.*` builtins mapped to NumPy, plus nz/na helpers."""
from __future__ import annotations

import numpy as np

from .context import NA, is_na


def _f(v):
    return float(v) if not is_na(v) else NA


MATH = {
    "abs": lambda x: abs(_f(x)),
    "max": lambda *xs: max(_f(x) for x in xs),
    "min": lambda *xs: min(_f(x) for x in xs),
    "round": lambda x, n=0: round(_f(x), int(n)),
    "pow": lambda x, y: _f(x) ** _f(y),
    "sqrt": lambda x: float(np.sqrt(_f(x))),
    "floor": lambda x: float(np.floor(_f(x))),
    "ceil": lambda x: float(np.ceil(_f(x))),
    "sign": lambda x: float(np.sign(_f(x))),
    "log": lambda x: float(np.log(_f(x))),
    "log10": lambda x: float(np.log10(_f(x))),
    "exp": lambda x: float(np.exp(_f(x))),
}


def nz(x, replacement=0.0):
    return replacement if is_na(x) else x


def na_check(x):
    return is_na(x)
