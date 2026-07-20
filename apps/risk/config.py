"""Risk configuration schema.

Canonical location for sizing + risk caps is ``live_config["risk"]`` (§2.3). For
backward compatibility a few keys were historically written at the top level of
``live_config`` (``leverage``, ``position_size_pct``); ``read_risk`` merges those
under the nested ``risk`` block (nested wins) so every reader sees one shape.
"""
from __future__ import annotations

from dataclasses import dataclass


# Keys that older records / some writers put at the top level of live_config.
_LEGACY_TOPLEVEL_KEYS = ("leverage", "position_size_pct")


def read_risk(live_config: dict | None) -> dict:
    """Return a single flattened risk dict: nested ``risk`` block overlaid on the
    legacy top-level keys. Callers apply their own defaults via ``.get(k, default)``
    so per-path behaviour (e.g. Tabdeal 5x vs HL 1x) is preserved.
    """
    lc = live_config or {}
    merged: dict = {}
    for k in _LEGACY_TOPLEVEL_KEYS:
        v = lc.get(k)
        if v is not None:
            merged[k] = v
    risk = lc.get("risk") or {}
    for k, v in risk.items():
        if v is not None:
            merged[k] = v
    return merged


@dataclass
class RiskConfig:
    risk_per_trade_pct: float | None = 1.0
    fixed_risk_usd: float | None = None
    max_daily_loss_pct: float | None = 5.0
    max_drawdown_pct: float | None = 15.0
    max_open_trades: int | None = 3
    max_exposure_pct: float | None = 50.0
    max_leverage: float | None = 10.0
    # Sizing / cap fields (canonical schema §2.3). Default None so callers can
    # apply path-specific fallbacks without RiskConfig silently overriding them.
    leverage: float | None = None
    position_size_pct: float | None = None
    max_notional_usdt: float | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> RiskConfig:
        if not data:
            return cls()
        return cls(
            risk_per_trade_pct=data.get("risk_per_trade_pct", 1.0),
            fixed_risk_usd=data.get("fixed_risk_usd"),
            max_daily_loss_pct=data.get("max_daily_loss_pct", 5.0),
            max_drawdown_pct=data.get("max_drawdown_pct", 15.0),
            max_open_trades=data.get("max_open_trades", 3),
            max_exposure_pct=data.get("max_exposure_pct", 50.0),
            max_leverage=data.get("max_leverage", 10.0),
            leverage=data.get("leverage"),
            position_size_pct=data.get("position_size_pct"),
            max_notional_usdt=data.get("max_notional_usdt"),
        )


def parse_risk_config(live_config: dict | None) -> RiskConfig:
    """Build a RiskConfig from live_config, honouring both nested and legacy shapes."""
    return RiskConfig.from_dict(read_risk(live_config))
