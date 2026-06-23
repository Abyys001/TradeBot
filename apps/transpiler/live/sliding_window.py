"""Fixed-size OHLCV buffer for incremental live execution."""
from __future__ import annotations

import pandas as pd


class SlidingWindow:
    """Maintains a bounded chronological OHLCV window."""

    def __init__(self, max_size: int):
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self.max_size = max_size
        self._rows: list[dict] = []

    def __len__(self) -> int:
        return len(self._rows)

    def load_df(self, df: pd.DataFrame) -> None:
        """Replace window contents from a DataFrame (ts, open, high, low, close, volume)."""
        self._rows = []
        for _, row in df.iterrows():
            self._append_row(
                {
                    "ts": int(row["ts"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                }
            )

    def append_closed(self, candle: dict) -> None:
        """Append one closed candle; drop the oldest when over capacity."""
        self._append_row(
            {
                "ts": int(candle["ts"]),
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
                "volume": float(candle.get("volume", 0.0)),
            }
        )

    def _append_row(self, row: dict) -> None:
        self._rows.append(row)
        if len(self._rows) > self.max_size:
            self._rows = self._rows[-self.max_size :]

    def to_dataframe(self) -> pd.DataFrame:
        if not self._rows:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        return pd.DataFrame(self._rows).reset_index(drop=True)

    def to_rows(self) -> list[dict]:
        return list(self._rows)

    @classmethod
    def from_rows(cls, max_size: int, rows: list[dict]) -> SlidingWindow:
        w = cls(max_size)
        for row in rows:
            w._append_row(row)
        return w
