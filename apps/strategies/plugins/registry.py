"""Strategy engine registry."""
from __future__ import annotations

from .base import StrategyPlugin
from .pine import PineStrategyEngine

_REGISTRY: dict[str, StrategyPlugin] = {}


def register(engine: StrategyPlugin) -> None:
    _REGISTRY[engine.name] = engine


def get_engine(name: str) -> StrategyPlugin:
    if name not in _REGISTRY:
        raise KeyError(f"unknown strategy engine: {name}")
    return _REGISTRY[name]


def list_engines() -> list[str]:
    return sorted(_REGISTRY.keys())


# Bootstrap default engines
register(PineStrategyEngine())
