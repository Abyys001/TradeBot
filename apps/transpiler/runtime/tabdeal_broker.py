"""TabdealBroker — routes one investor's copy of a signal to their Tabdeal
futures account, sized off *their own* equity, and records CopyOrder/CopyTrade.

Same entry/close/exit interface as LiveBroker so the fan-out step can replay
captured signal intents uniformly. Each instance is bound to one
``CopySubscription`` (investor credential + per-investor sizing).

Sizing: qty = available_USDT * position_size_pct% * risk_factor * leverage / price.
The captured absolute qty from the signal run is ignored — every investor sizes
independently against their own balance (this is what "each trade invests in its
own account" means).
"""
from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def to_tabdeal_symbol(symbol: str) -> str:
    """Map a strategy symbol to a Tabdeal futures pair (``BASE_QUOTE``).

    ``BTC`` -> ``BTC_USDT``; ``BTCUSDT`` -> ``BTC_USDT``; ``BTC_USDT`` -> unchanged.
    """
    s = (symbol or "").upper().strip()
    if "_" in s:
        return s
    if s.endswith("USDT"):
        return f"{s[:-4]}_USDT"
    if s.endswith("USD"):
        return f"{s[:-3]}_USDT"
    return f"{s}_USDT"


class TabdealBroker:
    def __init__(self, subscription, strategy, symbol, *, leverage: float = 1.0):
        self.subscription = subscription
        self.credential = subscription.credential
        self.strategy = strategy
        self.symbol = symbol
        self.pair = to_tabdeal_symbol(symbol)
        self.leverage = max(1.0, float(leverage))
        self.last_action = "No Action"
        self._client_obj = None
        self._leverage_set = False
        self._live_config = getattr(strategy, "live_config", None) or {}

    # ----- helpers -----

    def _client(self):
        if self._client_obj is None:
            from apps.exchange.tabdeal_futures import TabdealFuturesClient

            self._client_obj = TabdealFuturesClient(self.credential)
        return self._client_obj

    def _kill_switch_ok(self) -> bool:
        user = getattr(self.credential, "user", None)
        return bool(
            self.subscription.is_active
            and self.credential.is_active
            and getattr(user, "is_trading_enabled", False)
        )

    def _effective_pct(self) -> float:
        sub = self.subscription
        pct = sub.position_size_pct_override
        if pct is None:
            pct = sub.signal.default_position_size_pct
        return float(pct)

    def _log(self, level, event, payload):
        from apps.execution.models import ExecutionLog

        ExecutionLog.objects.create(strategy=self.strategy, level=level, event=event, payload=payload)

    def _ensure_leverage(self, client):
        if self._leverage_set:
            return
        try:
            client.set_leverage(self.pair, int(self.leverage))
        except Exception as exc:  # noqa: BLE001
            # 1207 activation also happens here; log but don't hard-fail sizing.
            logger.warning("set_leverage failed for cred %s: %s", self.credential.pk, exc)
        self._leverage_set = True

    def _compute_qty(self, client, price: float) -> float:
        equity = client.available_usdt()
        risk_factor = float(self.subscription.risk_factor or 1)
        notional = equity * (self._effective_pct() / 100.0) * risk_factor * self.leverage
        if price <= 0 or notional <= 0:
            return 0.0
        raw_qty = notional / price
        try:
            _, qty_prec = client.symbol_precision(self.pair)
        except Exception:  # noqa: BLE001
            qty_prec = 3
        return round(raw_qty, qty_prec)

    def _open_copy_trade(self):
        from apps.copytrading.models import CopyTrade

        return (
            CopyTrade.objects.filter(subscription=self.subscription, status=CopyTrade.Status.OPEN)
            .order_by("-opened_at")
            .first()
        )

    @staticmethod
    def _avg_price(resp: dict, fallback: float) -> float:
        for key in ("avgPrice", "avg_price", "price"):
            v = resp.get(key)
            try:
                if v is not None and float(v) > 0:
                    return float(v)
            except (TypeError, ValueError):
                continue
        return float(fallback)

    # ----- interface -----

    def entry(self, oid, direction, price, bar_index, qty=None, **kwargs):
        from apps.copytrading.models import CopyOrder, CopyTrade

        if not self._kill_switch_ok():
            self._log("warning", "copy.blocked", {"reason": "trading disabled/inactive", "cred": self.credential.pk})
            return None

        is_buy = str(direction).lower() in ("long", "strategy.long")
        side = CopyOrder.Side.BUY if is_buy else CopyOrder.Side.SELL

        client = self._client()

        # Reverse: if an opposite position/trade is open, close it first.
        open_trade = self._open_copy_trade()
        if open_trade is not None:
            self.close(oid, price, bar_index, reason="reversal")
            open_trade = None

        # Per-account risk gate on the investor's own equity. The broker is
        # rebuilt per candle, so baseline the manager to this investor's actual
        # equity — per-trade gates (leverage/exposure/open-trades) still apply.
        from apps.risk.config import parse_risk_config
        from apps.risk.manager import RiskManager

        equity = client.available_usdt()
        risk_manager = RiskManager(parse_risk_config(self._live_config), initial_balance=max(equity, 1.0))
        decision = risk_manager.pre_trade(equity=equity, open_trades=0, exposure_pct=0.0, leverage=self.leverage)
        if not decision.ok:
            self._log("warning", "copy.risk_blocked", {"reason": decision.reason, "cred": self.credential.pk})
            return None

        self._ensure_leverage(client)
        qty_final = self._compute_qty(client, float(price or 0))
        if qty_final <= 0:
            self._log("warning", "copy.size_zero", {"cred": self.credential.pk, "equity": equity, "price": price})
            return None

        try:
            resp = client.place_market_order(
                symbol=self.pair, side=side, quantity=qty_final, price=price,
                client_order_id=f"c{self.subscription.pk}-{oid}",
            )
        except Exception as exc:  # noqa: BLE001
            self._log("error", "copy.order_failed", {"cred": self.credential.pk, "error": str(exc)[:200]})
            return None

        fill_px = self._avg_price(resp if isinstance(resp, dict) else {}, price or 0)
        order = CopyOrder.objects.create(
            subscription=self.subscription,
            exchange_order_id=str((resp or {}).get("orderId", "")),
            client_order_id=f"c{self.subscription.pk}-{oid}",
            pair=self.pair,
            side=side,
            order_type="market",
            size=Decimal(str(qty_final)),
            price=Decimal(str(fill_px)) if fill_px else None,
            status="submitted",
            filled_size=Decimal(str(qty_final)),
            avg_fill_price=Decimal(str(fill_px)) if fill_px else None,
            raw=resp if isinstance(resp, dict) else {},
        )
        CopyTrade.objects.create(subscription=self.subscription, entry_order=order, status=CopyTrade.Status.OPEN)
        self.last_action = f"{'LONG' if is_buy else 'SHORT'} entry {qty_final} @ {fill_px}"
        self._log("info", "copy.entry", {"cred": self.credential.pk, "pair": self.pair, "side": side, "qty": qty_final, "px": fill_px})
        return order

    def close(self, oid, price, bar_index, **kwargs):
        from apps.copytrading.models import CopyOrder

        if not self._kill_switch_ok():
            self._log("warning", "copy.blocked", {"reason": "trading disabled/inactive", "cred": self.credential.pk})
            return None

        open_trade = self._open_copy_trade()
        if open_trade is None:
            return None

        client = self._client()
        try:
            resp = client.close_position(self.pair)
        except Exception as exc:  # noqa: BLE001
            self._log("error", "copy.close_failed", {"cred": self.credential.pk, "error": str(exc)[:200]})
            return None

        entry = open_trade.entry_order
        exit_px = self._avg_price(resp if isinstance(resp, dict) else {}, price or 0)
        exit_order = CopyOrder.objects.create(
            subscription=self.subscription,
            client_order_id=f"c{self.subscription.pk}-{oid}-x",
            pair=self.pair,
            side=CopyOrder.Side.SELL if entry.side == CopyOrder.Side.BUY else CopyOrder.Side.BUY,
            order_type="market",
            size=entry.size,
            price=Decimal(str(exit_px)) if exit_px else None,
            status="submitted",
            filled_size=entry.size,
            avg_fill_price=Decimal(str(exit_px)) if exit_px else None,
            raw=resp if isinstance(resp, dict) else {},
        )

        # Realised PnL for this round-trip.
        entry_px = float(entry.avg_fill_price or entry.price or 0)
        size = float(entry.size or 0)
        if entry.side == CopyOrder.Side.BUY:
            gross = (exit_px - entry_px) * size
        else:
            gross = (entry_px - exit_px) * size

        open_trade.exit_order = exit_order
        open_trade.gross_pnl = Decimal(str(round(gross, 8)))
        open_trade.status = open_trade.Status.CLOSED
        from django.utils import timezone

        open_trade.closed_at = timezone.now()
        open_trade.save(update_fields=["exit_order", "gross_pnl", "status", "closed_at"])

        # Profit-share ledger (high-water mark) is applied here in Phase 4.
        try:
            from apps.copytrading.fees import apply_profit_share

            apply_profit_share(open_trade)
        except ImportError:
            pass

        self.last_action = f"CLOSE {size} @ {exit_px} (pnl {gross:.4f})"
        self._log("info", "copy.close", {"cred": self.credential.pk, "pair": self.pair, "gross_pnl": round(gross, 8), "px": exit_px})
        return exit_order

    def exit(self, oid, price, bar_index, **kwargs):
        """Attach SL/TP to the open position via positionSlTp (best-effort)."""
        stop_px = kwargs.get("stop")
        limit_px = kwargs.get("limit")
        if stop_px is None and limit_px is None:
            return self.close(oid, price, bar_index)
        if not self._kill_switch_ok():
            return None

        client = self._client()
        try:
            positions = client._signed("GET", "/r/fapi/v1/position", {"symbol": self.pair, "isActive": 1})
            rows = positions if isinstance(positions, list) else positions.get("positions", [])
            pos_id = rows[0].get("id") if rows else None
            if pos_id is None:
                self._log("warning", "copy.sltp_no_position", {"cred": self.credential.pk, "pair": self.pair})
                return None
            resp = client.set_position_sl_tp(
                position_id=pos_id, sl_price=stop_px, tp_price=limit_px, symbol=self.pair,
            )
            self._log("info", "copy.sltp", {"cred": self.credential.pk, "pair": self.pair, "sl": stop_px, "tp": limit_px})
            return resp
        except Exception as exc:  # noqa: BLE001
            self._log("error", "copy.sltp_failed", {"cred": self.credential.pk, "error": str(exc)[:200]})
            return None

    def finalize(self, last_price, last_bar):
        return None

    def metrics(self):
        return {}

    def trades(self):
        return []
