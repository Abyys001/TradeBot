"""TabdealLiveBroker — routes a *primary* strategy's own live orders to the
strategy owner's Tabdeal futures account (no investor fan-out — that's
apps.transpiler.runtime.tabdeal_broker.TabdealBroker's job).

Same entry/close/exit/finalize/metrics/trades/last_action interface as
LiveBroker so runner.py/engine.py can construct either uniformly. Persists
apps.execution.OrderRecord + apps.execution.ExecutionLog with the same event
vocabulary LiveBroker uses (order.placed/order.rejected/order.blocked,
risk.blocked) so Tabdeal-primary trades look identical in the UI/order
history/execution log stream to HL-primary trades.

Orders here must always end in a terminal OrderRecord.status (filled/rejected,
never left "submitted") — apps.execution.tasks.reconcile_orders_task is
Hyperliquid-only and would mishandle a Tabdeal order left non-terminal.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from .tabdeal_broker import to_tabdeal_symbol

logger = logging.getLogger(__name__)


class TabdealLiveBroker:
    def __init__(self, credential, strategy, symbol, *, leverage: float | None = None):
        self.credential = credential
        self.strategy = strategy
        self.symbol = symbol
        self.pair = to_tabdeal_symbol(symbol)
        self.last_action = "No Action"
        self._client_obj = None
        self._leverage_set = False
        self._open_orders: dict[str, dict] = {}

        live_config = getattr(strategy, "live_config", None) or {}
        risk_block = live_config.get("risk") or {}
        self._live_config = live_config
        self._position_size_pct = float(risk_block.get("position_size_pct", 20))
        self._leverage = float(leverage if leverage is not None else risk_block.get("leverage", 5))

    # ----- helpers -----

    def _client(self):
        if self._client_obj is None:
            from apps.exchange.tabdeal_futures import TabdealFuturesClient

            self._client_obj = TabdealFuturesClient(self.credential)
        return self._client_obj

    def _kill_switch_ok(self) -> bool:
        return bool(getattr(self.strategy.user, "is_trading_enabled", False))

    def _log(self, level, event, payload):
        from apps.execution.models import ExecutionLog

        ExecutionLog.objects.create(strategy=self.strategy, level=level, event=event, payload=payload)

    def _ensure_leverage(self, client):
        if self._leverage_set:
            return
        try:
            client.set_leverage(self.pair, int(self._leverage))
        except Exception as exc:  # noqa: BLE001 — 1207 activation also happens here; don't hard-fail sizing
            logger.warning("set_leverage failed for cred %s: %s", self.credential.pk, exc)
        self._leverage_set = True

    def _compute_qty(self, client, price: float) -> float:
        equity = client.available_usdt()
        notional = equity * (self._position_size_pct / 100.0) * self._leverage
        if price <= 0 or notional <= 0:
            return 0.0
        raw_qty = notional / price
        try:
            _, qty_prec = client.symbol_precision(self.pair)
        except Exception:  # noqa: BLE001
            qty_prec = 3
        return round(raw_qty, qty_prec)

    def _risk_gate(self, *, oid, client) -> bool:
        try:
            equity = client.available_usdt()
        except Exception:  # noqa: BLE001
            equity = 0.0
        try:
            pos = client.get_position(self.pair)
        except Exception:  # noqa: BLE001
            pos = None

        open_trades = 1 if pos else 0
        exposure_pct = 0.0
        if pos:
            try:
                notional = abs(float(pos.get("positionAmt", 0))) * float(
                    pos.get("markPrice") or pos.get("entryPrice") or 0
                )
                exposure_pct = (notional / equity * 100.0) if equity > 0 else 0.0
            except (TypeError, ValueError):
                exposure_pct = 0.0

        from apps.risk.config import parse_risk_config
        from apps.risk.manager import RiskManager

        risk_manager = RiskManager(parse_risk_config(self._live_config), initial_balance=max(equity, 1.0))
        decision = risk_manager.pre_trade(
            equity=equity, open_trades=open_trades, exposure_pct=exposure_pct, leverage=self._leverage
        )
        if not decision.ok:
            self._log(
                "warning",
                "risk.blocked",
                {"reason": decision.reason, "oid": oid, "equity": equity, "exposure_pct": exposure_pct},
            )
            return False
        return True

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

    @staticmethod
    def _status_map(resp_status: str) -> str:
        mapping = {
            "NEW": "submitted",
            "PARTIALLY_FILLED": "partially_filled",
            "FILLED": "filled",
            "CANCELED": "canceled",
            "REJECTED": "rejected",
            "EXPIRED": "expired",
        }
        # Tabdeal market orders fill synchronously, so default any unrecognized/
        # absent status to "filled" rather than "submitted" -- leaving it
        # "submitted" would make apps.execution.tasks.reconcile_orders_task (HL-only)
        # pick this order up and mishandle it.
        return mapping.get((resp_status or "").upper(), "filled")

    # ----- order placement core -----

    def _place(self, *, is_buy: bool, oid, price, qty):
        from apps.exchange.tabdeal_errors import TabdealAPIError
        from apps.execution.models import OrderRecord

        if not self._kill_switch_ok():
            self._log("warning", "order.blocked", {"reason": "is_trading_enabled is False", "oid": oid})
            return None

        client = self._client()
        if not self._risk_gate(oid=oid, client=client):
            return None

        self._ensure_leverage(client)

        side = OrderRecord.Side.BUY if is_buy else OrderRecord.Side.SELL
        tabdeal_side = "BUY" if is_buy else "SELL"
        coid = f"s{self.strategy.pk}-{oid}"

        try:
            resp = client.place_market_order(
                symbol=self.pair, side=tabdeal_side, quantity=qty, price=price, client_order_id=coid,
            )
        except TabdealAPIError as exc:
            rec = OrderRecord.objects.create(
                strategy=self.strategy,
                client_order_id=coid,
                symbol=self.pair,
                side=side,
                order_type="market",
                size=Decimal(str(qty)),
                price=Decimal(str(price)) if price is not None else None,
                status="rejected",
                raw={"error_code": exc.info.code, "error_msg": exc.info.message},
            )
            self._log(
                "error",
                "order.rejected",
                {"oid": oid, "side": side, "symbol": self.pair, "price": price,
                 "error": exc.info.code, "hint": exc.info.action},
            )
            return rec
        except Exception as exc:  # noqa: BLE001 — network/timeout etc.
            self._log(
                "error",
                "order.rejected",
                {"oid": oid, "side": side, "symbol": self.pair, "error": type(exc).__name__},
            )
            return None

        fill_px = self._avg_price(resp if isinstance(resp, dict) else {}, price or 0)
        status = self._status_map((resp or {}).get("status", ""))
        rec = OrderRecord.objects.create(
            strategy=self.strategy,
            exchange_order_id=str((resp or {}).get("orderId", "")),
            client_order_id=coid,
            symbol=self.pair,
            side=side,
            order_type="market",
            size=Decimal(str(qty)),
            price=Decimal(str(fill_px)) if fill_px else (Decimal(str(price)) if price is not None else None),
            status=status,
            filled_size=Decimal(str((resp or {}).get("executedQty", qty))),
            avg_fill_price=Decimal(str(fill_px)) if fill_px else None,
            raw=resp if isinstance(resp, dict) else {},
        )
        self.last_action = f"{'BUY' if is_buy else 'SELL'} at {fill_px}"
        self._log(
            "info",
            "order.placed",
            {"oid": oid, "side": side, "symbol": self.pair, "price": fill_px,
             "exchange_order_id": rec.exchange_order_id, "client_order_id": coid},
        )
        return rec

    # ----- interface -----

    def entry(self, oid, direction, price, bar_index, qty=None, **kwargs):
        is_buy = str(direction).lower() in ("long", "strategy.long")
        target_side = "long" if is_buy else "short"
        for open_oid, meta in list(self._open_orders.items()):
            if meta.get("side") != target_side:
                self.close(open_oid, price, bar_index, reason="reversal")

        client = self._client()
        qty_final = self._compute_qty(client, float(price or 0))
        if qty_final <= 0:
            self._log("warning", "order.size_zero", {"oid": oid, "pair": self.pair, "price": price})
            return None

        rec = self._place(is_buy=is_buy, oid=oid, price=price, qty=qty_final)
        if rec is not None and rec.status != "rejected":
            self._open_orders[str(oid)] = {"side": target_side, "qty": qty_final}
            from apps.telegram.tasks import dispatch_telegram_alert

            dispatch_telegram_alert.delay(
                user_id=self.strategy.user_id,
                strategy_name=self.strategy.name,
                symbol=self.symbol,
                action=f"{'LONG' if is_buy else 'SHORT'} Entry",
                price=f"Entry Price: ${price}" if price else "",
                leverage=f"Leverage: {self._leverage}x",
                qty=str(qty_final),
                position_side="LONG" if is_buy else "SHORT",
            )
        return rec

    def close(self, oid, price, bar_index, **kwargs):
        from apps.exchange.tabdeal_errors import TabdealAPIError
        from apps.execution.models import OrderRecord

        if not self._kill_switch_ok():
            self._log("warning", "order.blocked", {"reason": "is_trading_enabled is False", "oid": oid})
            return None

        client = self._client()
        try:
            pos = client.get_position(self.pair)
        except Exception:  # noqa: BLE001
            pos = None
        if pos is None:
            return None

        qty_pct = float(kwargs.get("qty_pct", 1.0))
        if qty_pct < 1.0:
            # Tabdeal FAPI's reduceOnly is "not yet supported" (Tabdeal_API_Reference.md
            # line 676), so a partial close cannot be placed safely as a plain
            # opposite-side market order. Always full-close and log the mismatch.
            self._log("warning", "order.partial_close_unsupported", {"oid": oid, "requested_pct": qty_pct})

        exit_reason = kwargs.get("reason", "manual")
        side = self._open_orders.get(str(oid), {}).get("side", "unknown")

        try:
            resp = client.close_position(self.pair)
        except TabdealAPIError as exc:
            self._log("error", "order.close_rejected", {"oid": oid, "error": exc.info.code, "hint": exc.info.action})
            return None
        except Exception as exc:  # noqa: BLE001
            self._log("error", "order.close_rejected", {"oid": oid, "error": type(exc).__name__})
            return None

        pos_amt = abs(float(pos.get("positionAmt", 0) or 0))
        exit_px = self._avg_price(resp if isinstance(resp, dict) else {}, price or 0)
        rec = OrderRecord.objects.create(
            strategy=self.strategy,
            client_order_id=f"s{self.strategy.pk}-{oid}-x",
            symbol=self.pair,
            side=OrderRecord.Side.SELL if side == "long" else OrderRecord.Side.BUY,
            order_type="market",
            size=Decimal(str(pos_amt)),
            price=Decimal(str(exit_px)) if exit_px else None,
            status="filled",
            filled_size=Decimal(str(pos_amt)),
            avg_fill_price=Decimal(str(exit_px)) if exit_px else None,
            raw=resp if isinstance(resp, dict) else {},
        )
        self.last_action = f"CLOSE at {exit_px}"
        if oid in self._open_orders:
            del self._open_orders[oid]
        self._log("info", "order.closed", {"oid": oid, "pair": self.pair, "px": exit_px, "reason": exit_reason})

        from apps.telegram.tasks import dispatch_telegram_alert

        dispatch_telegram_alert.delay(
            user_id=self.strategy.user_id,
            strategy_name=self.strategy.name,
            symbol=self.symbol,
            action="Close",
            price=f"Close Price: ${price}" if price else "",
            leverage=f"Leverage: {self._leverage}x",
            qty=str(pos_amt),
            exit_reason=exit_reason,
            position_side=side,
        )
        return rec

    def exit(self, oid, price, bar_index, **kwargs):
        from apps.exchange.tabdeal_errors import TabdealAPIError

        stop_px = kwargs.get("stop")
        limit_px = kwargs.get("limit")
        if stop_px is None and limit_px is None:
            return self.close(oid, price, bar_index)
        if not self._kill_switch_ok():
            return None

        client = self._client()
        try:
            pos_id = client.get_open_position_id(self.pair)
        except Exception:  # noqa: BLE001
            pos_id = None
        if pos_id is None:
            self._log("warning", "order.sltp_no_position", {"oid": oid, "pair": self.pair})
            return None

        try:
            resp = client.set_position_sl_tp(position_id=pos_id, sl_price=stop_px, tp_price=limit_px, symbol=self.pair)
        except TabdealAPIError as exc:
            self._log("error", "order.sltp_rejected", {"oid": oid, "error": exc.info.code, "hint": exc.info.action})
            return None
        except Exception as exc:  # noqa: BLE001
            self._log("error", "order.sltp_rejected", {"oid": oid, "error": type(exc).__name__})
            return None

        self._log("info", "order.sltp", {"oid": oid, "pair": self.pair, "sl": stop_px, "tp": limit_px})
        return resp

    # Live broker has no synthetic metrics.
    def finalize(self, last_price, last_bar):
        return None

    def metrics(self):
        return {}

    def trades(self):
        return []
