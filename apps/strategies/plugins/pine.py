"""Pine Script strategy engine plugin."""
from __future__ import annotations

from apps.transpiler.engine import run_backtest_pine

from .base import CompiledStrategy, StrategyPlugin


class PineStrategyEngine(StrategyPlugin):
    name = "pine"

    def compile(self, source: str, params: dict | None = None) -> CompiledStrategy:
        from apps.transpiler.engine import compile

        program = compile(source)
        return CompiledStrategy(engine=self.name, artifact=program, params=params or {})

    def run_backtest(self, compiled: CompiledStrategy, df, **kwargs):
        source = kwargs.pop("source", None)
        if not source:
            raise ValueError("Pine backtest requires source= keyword argument")
        return run_backtest_pine(source, df, **kwargs)
