"""Strategy plugin interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class CompiledStrategy:
    engine: str
    artifact: Any
    params: dict


class StrategyPlugin(ABC):
    """Base class for pluggable strategy engines (Pine, native Python, ...)."""

    name: str = "base"

    @abstractmethod
    def compile(self, source: str, params: dict | None = None) -> CompiledStrategy:
        ...

    @abstractmethod
    def run_backtest(self, compiled: CompiledStrategy, df, **kwargs):
        ...

    def supported_timeframes(self) -> list[str]:
        return ["1m", "5m", "15m", "1h", "4h", "1d"]
