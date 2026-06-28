"""Order routing for `strategy.entry / close / exit`.

Two backends behind one interface:
  - SimBroker  — backtest fills at the next bar's open with commission/slippage;
    tracks position and realised PnL; emits trade records and summary metrics.
  - LiveBroker — routes to Hyperliquid via agent-signed orders
    (`apps.exchange.hl_client.build_exchange`) and persists
    `apps.execution.OrderRecord` + `ExecutionLog`. Honours the per-user
    `is_trading_enabled` kill-switch before any live order.
"""
from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


from .sim_broker import SimBroker, Trade  # noqa: F401 — enhanced backtest broker


class WarmupBroker:
    """No-op broker used during historical warmup (no orders placed)."""

    def entry(self, oid, direction, price, bar_index, qty=None, **kwargs):
        return None

    def close(self, oid, price, bar_index, **kwargs):
        return None

    def exit(self, oid, price, bar_index, **kwargs):
        return None

    def finalize(self, last_price, last_bar):
        return None

    def metrics(self):
        return {}

    def trades(self):
        return []


class LiveBroker:
    """Routes orders to Hyperliquid via agent-signed transactions."""

    def __init__(self, credential, strategy, symbol):
        self.credential = credential
        self.strategy = strategy
        self.symbol = symbol
        self._exchange = None
        self._name = None
        self.last_action = "No Action"
        from apps.risk.config import parse_risk_config
        from apps.risk.manager import RiskManager

        live_config = getattr(strategy, "live_config", None) or {}
        self._risk_manager = RiskManager(parse_risk_config(live_config))
        self._leverage = float(live_config.get("leverage", 1))
        self._open_orders: dict[str, dict] = {}

    def _get_exchange(self):
        if self._exchange is None:
            from apps.exchange.hl_client import build_exchange
            from apps.exchange.hl_constants import normalize_coin
            from apps.exchange.hl_meta import resolve_trading_name

            self._coin = normalize_coin(self.symbol)
            market_type = "spot" if self._is_spot() else "perp"
            self._name = resolve_trading_name(self._coin, market_type=market_type, network=self.credential.network)
            self._exchange = build_exchange(self.credential)
        return self._exchange

    def _risk_gate(self, *, oid: str, open_trades: int = 0) -> bool:
        from apps.execution.models import ExecutionLog
        from apps.risk import gates

        if self._risk_manager.halted:
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="risk.blocked",
                payload={"reason": self._risk_manager.halt_reason or "risk_halted", "oid": oid},
            )
            return False
        decision = gates.check_max_open_trades(open_trades, self._risk_manager.config.max_open_trades)
        if not decision.ok:
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="risk.blocked",
                payload={"reason": decision.reason, "oid": oid},
            )
            return False
        return True

    def _kill_switch_ok(self) -> bool:
        return bool(getattr(self.strategy.user, "is_trading_enabled", False))

    @staticmethod
    def _extract_order_id(resp) -> str:
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return ""
        statuses = (resp.get("response") or {}).get("data", {}).get("statuses") or []
        if not statuses:
            return ""
        st = statuses[0]
        if "filled" in st:
            return str(st["filled"].get("oid", ""))
        if "resting" in st:
            return str(st["resting"].get("oid", ""))
        return ""

    def _place_perp(self, *, is_buy: bool, oid, price, qty):
        from apps.execution.models import ExecutionLog, OrderRecord
        from apps.exchange.hl_cloid import pine_oid_to_cloid
        from apps.exchange.hl_errors import parse_exchange_response
        from apps.exchange.hl_meta import get_asset_meta, round_size
        from apps.exchange.hl_rate_limit import signed_action
        from apps.exchange.risk import pre_trade_gate

        if not self._kill_switch_ok():
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="order.blocked",
                payload={"reason": "is_trading_enabled is False", "oid": oid},
            )
            return None

        if not self._risk_gate(oid=oid, open_trades=len(self._open_orders)):
            return None

        decision = pre_trade_gate(credential=self.credential)
        if not decision.ok:
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="risk.blocked",
                payload={"reason": decision.reason, "details": decision.details, "oid": oid},
            )
            return None

        exchange = self._get_exchange()
        cloid = pine_oid_to_cloid(str(oid))
        meta = get_asset_meta(self._name, market_type="perp", network=self.credential.network)
        sz = round_size(float(qty), meta)

        def _call():
            return exchange.market_open(
                name=self._name,
                is_buy=is_buy,
                sz=float(sz),
                px=None,
                slippage=0.01,
                cloid=cloid,
            )

        resp = signed_action(self.credential, _call, weight=1)
        side = OrderRecord.Side.BUY if is_buy else OrderRecord.Side.SELL
        parsed = parse_exchange_response(resp if isinstance(resp, dict) else {})
        exchange_id = self._extract_order_id(resp)
        err = parsed[0][1] if parsed else None
        rec = OrderRecord.objects.create(
            strategy=self.strategy,
            exchange_order_id=exchange_id,
            client_order_id=str(oid),
            symbol=self._coin,
            side=side,
            order_type="market",
            size=Decimal(str(sz)),
            price=Decimal(str(price)) if price is not None else None,
            status="rejected" if err else "submitted",
            raw=resp if isinstance(resp, dict) else {},
        )
        self.last_action = f"{'BUY' if is_buy else 'SELL'} at {price}"
        ExecutionLog.objects.create(
            strategy=self.strategy,
            level="error" if err else "info",
            event="order.rejected" if err else "order.placed",
            payload={
                "oid": oid,
                "side": side,
                "symbol": self._coin,
                "price": price,
                "exchange_order_id": exchange_id,
                "cloid": str(cloid),
                "error": err.code if err else None,
                "hint": err.action if err else None,
            },
        )
        return rec

    def _place_spot(self, *, is_buy: bool, oid, price, qty):
        from apps.execution.models import ExecutionLog, OrderRecord
        from apps.exchange.hl_cloid import pine_oid_to_cloid
        from apps.exchange.hl_errors import parse_exchange_response
        from apps.exchange.hl_meta import (
            aggressive_spot_price,
            get_asset_meta,
            round_price,
            round_size,
            validate_min_notional,
        )
        from apps.exchange.hl_rate_limit import signed_action
        from apps.exchange.risk import pre_trade_gate

        if not self._kill_switch_ok():
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="order.blocked",
                payload={"reason": "is_trading_enabled is False", "oid": oid},
            )
            return None

        if not self._risk_gate(oid=oid, open_trades=len(self._open_orders)):
            return None

        decision = pre_trade_gate(credential=self.credential)
        if not decision.ok:
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="risk.blocked",
                payload={"reason": decision.reason, "details": decision.details, "oid": oid},
            )
            return None

        exchange = self._get_exchange()
        cloid = pine_oid_to_cloid(str(oid))
        meta = get_asset_meta(self._name, market_type="spot", network=self.credential.network)
        sz = round_size(float(qty), meta)
        px = aggressive_spot_price(self._coin, is_buy=is_buy, network=self.credential.network, slippage=0.01)
        px = round_price(px, meta)
        notional_err = validate_min_notional(sz, px)
        if notional_err:
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="order.blocked",
                payload={"reason": notional_err, "oid": oid, "symbol": self._coin},
            )
            return None

        def _call():
            return exchange.order(
                self._name,
                is_buy,
                float(sz),
                float(px),
                {"limit": {"tif": "Ioc"}},
                cloid=cloid,
            )

        resp = signed_action(self.credential, _call, weight=1)
        side = OrderRecord.Side.BUY if is_buy else OrderRecord.Side.SELL
        parsed = parse_exchange_response(resp if isinstance(resp, dict) else {})
        exchange_id = self._extract_order_id(resp)
        err = parsed[0][1] if parsed else None
        rec = OrderRecord.objects.create(
            strategy=self.strategy,
            exchange_order_id=exchange_id,
            client_order_id=str(oid),
            symbol=self._coin,
            side=side,
            order_type="market",
            size=Decimal(str(sz)),
            price=Decimal(str(px)),
            status="rejected" if err else "submitted",
            raw=resp if isinstance(resp, dict) else {},
        )
        self.last_action = f"{'BUY' if is_buy else 'SELL'} at {px}"
        ExecutionLog.objects.create(
            strategy=self.strategy,
            level="error" if err else "info",
            event="order.rejected" if err else "order.placed",
            payload={
                "oid": oid,
                "side": side,
                "symbol": self._coin,
                "price": px,
                "exchange_order_id": exchange_id,
                "cloid": str(cloid),
                "error": err.code if err else None,
                "hint": err.action if err else None,
            },
        )
        return rec

    def _place_perp_limit(self, *, is_buy: bool, oid, limit_px, qty):
        from apps.execution.models import ExecutionLog, OrderRecord
        from apps.exchange.hl_cloid import pine_oid_to_cloid
        from apps.exchange.hl_errors import parse_exchange_response
        from apps.exchange.hl_meta import get_asset_meta, round_price, round_size, validate_min_notional
        from apps.exchange.hl_rate_limit import signed_action
        from apps.exchange.risk import pre_trade_gate

        if not self._kill_switch_ok():
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="order.blocked",
                payload={"reason": "is_trading_enabled is False", "oid": oid},
            )
            return None

        if not self._risk_gate(oid=oid, open_trades=len(self._open_orders)):
            return None

        decision = pre_trade_gate(credential=self.credential)
        if not decision.ok:
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="risk.blocked",
                payload={"reason": decision.reason, "details": decision.details, "oid": oid},
            )
            return None

        exchange = self._get_exchange()
        cloid = pine_oid_to_cloid(str(oid))
        meta = get_asset_meta(self._name, market_type="perp", network=self.credential.network)
        sz = round_size(float(qty), meta)
        px = round_price(float(limit_px), meta)
        notional_err = validate_min_notional(sz, px)
        if notional_err:
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="order.blocked",
                payload={"reason": notional_err, "oid": oid, "symbol": self._coin},
            )
            return None

        def _call():
            return exchange.order(
                name=self._name,
                is_buy=is_buy,
                sz=float(sz),
                limit_px=float(px),
                order_type={"limit": {"tif": "Gtc"}},
                reduce_only=False,
                cloid=cloid,
            )

        resp = signed_action(self.credential, _call, weight=1)
        parsed = parse_exchange_response(resp if isinstance(resp, dict) else {})
        exchange_id = self._extract_order_id(resp)
        err = parsed[0][1] if parsed else None
        side = OrderRecord.Side.BUY if is_buy else OrderRecord.Side.SELL
        rec = OrderRecord.objects.create(
            strategy=self.strategy,
            exchange_order_id=exchange_id,
            client_order_id=str(oid),
            symbol=self._coin,
            side=side,
            order_type="limit",
            size=Decimal(str(sz)),
            price=Decimal(str(px)),
            status="rejected" if err else "submitted",
            raw=resp if isinstance(resp, dict) else {},
        )
        ExecutionLog.objects.create(
            strategy=self.strategy,
            level="error" if err else "info",
            event="order.rejected" if err else "order.placed",
            payload={
                "oid": oid,
                "side": side,
                "symbol": self._coin,
                "price": px,
                "exchange_order_id": exchange_id,
                "cloid": str(cloid),
                "error": err.code if err else None,
                "hint": err.action if err else None,
            },
        )
        return rec

    def _place_perp_tpsl(self, *, oid, stop_px=None, limit_px=None):
        """Create reduce-only trigger orders for stop-loss / take-profit."""
        from apps.execution.models import ExecutionLog, OrderRecord
        from apps.exchange.hl_cloid import pine_oid_to_cloid
        from apps.exchange.hl_errors import parse_exchange_response
        from apps.exchange.hl_meta import get_asset_meta, round_price
        from apps.exchange.hl_rate_limit import signed_action
        from apps.exchange.risk import pre_trade_gate

        if not self._kill_switch_ok():
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="order.blocked",
                payload={"reason": "is_trading_enabled is False", "oid": oid},
            )
            return None

        if not self._risk_gate(oid=oid, open_trades=len(self._open_orders)):
            return None

        decision = pre_trade_gate(credential=self.credential)
        if not decision.ok:
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="risk.blocked",
                payload={"reason": decision.reason, "details": decision.details, "oid": oid},
            )
            return None

        exchange = self._get_exchange()
        meta = get_asset_meta(self._name, market_type="perp", network=self.credential.network)

        results = []
        for kind, px, tpsl in (
            ("sl", stop_px, "sl"),
            ("tp", limit_px, "tp"),
        ):
            if px is None:
                continue
            trig_px = round_price(float(px), meta)
            cloid = pine_oid_to_cloid(f"{oid}:{kind}")

            def _call():
                return exchange.order(
                    name=self._name,
                    is_buy=False,  # reduce-only; HL enforces reduceOnly
                    sz=0.0,
                    limit_px=0.0,
                    order_type={"trigger": {"triggerPx": float(trig_px), "isMarket": True, "tpsl": tpsl}},
                    reduce_only=True,
                    cloid=cloid,
                )

            resp = signed_action(self.credential, _call, weight=1)
            parsed = parse_exchange_response(resp if isinstance(resp, dict) else {})
            exchange_id = self._extract_order_id(resp)
            err = parsed[0][1] if parsed else None
            rec = OrderRecord.objects.create(
                strategy=self.strategy,
                exchange_order_id=exchange_id,
                client_order_id=str(cloid),
                symbol=self._coin,
                side=OrderRecord.Side.SELL,
                order_type="trigger",
                size=Decimal("0"),
                price=Decimal(str(trig_px)),
                status="rejected" if err else "submitted",
                raw=resp if isinstance(resp, dict) else {},
            )
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="error" if err else "info",
                event="order.rejected" if err else "order.placed",
                payload={"oid": oid, "kind": kind, "triggerPx": trig_px, "cloid": str(cloid), "error": err.code if err else None},
            )
            results.append(rec.pk)
        return results

    def _is_spot(self) -> bool:
        from apps.strategies.models import Strategy

        return getattr(self.strategy, "market_type", Strategy.MarketType.PERP) == Strategy.MarketType.SPOT

    def entry(self, oid, direction, price, bar_index, qty=None, **kwargs):
        is_buy = str(direction).lower() in ("long", "strategy.long")
        target_side = "long" if is_buy else "short"
        for open_oid, meta in list(self._open_orders.items()):
            if meta.get("side") != target_side:
                self.close(open_oid, price, bar_index, reason="reversal")

        qty = qty or 1
        limit_px = kwargs.get("limit")
        rec = None
        if limit_px is not None and not self._is_spot():
            rec = self._place_perp_limit(is_buy=is_buy, oid=oid, limit_px=limit_px, qty=qty)
        elif self._is_spot():
            rec = self._place_spot(is_buy=is_buy, oid=oid, price=price, qty=qty)
        else:
            rec = self._place_perp(is_buy=is_buy, oid=oid, price=price, qty=qty)
        if rec is not None:
            self._open_orders[str(oid)] = {"side": target_side, "qty": qty}
            alert_message = kwargs.get("alert_message")
            if alert_message:
                from apps.execution.models import ExecutionLog
                from apps.integrations.tasks import signum_send_webhook_task

                ExecutionLog.objects.create(
                    strategy=self.strategy,
                    level="info",
                    event="signum.webhook",
                    payload={"oid": oid, "preview": alert_message[:500]},
                )
                signum_send_webhook_task.delay(self.strategy.user_id, alert_message)
            from apps.telegram.tasks import dispatch_telegram_alert

            dispatch_telegram_alert.delay(
                user_id=self.strategy.user_id,
                strategy_name=self.strategy.name,
                symbol=self.symbol,
                action=f"{'LONG' if is_buy else 'SHORT'} Entry",
                price=f"Entry Price: ${price}" if price else "",
                leverage=f"Leverage: {self._leverage}x",
                qty=str(qty),
            )
        return rec

    def close(self, oid, price, bar_index, **kwargs):
        from apps.execution.models import ExecutionLog
        from apps.exchange.hl_rate_limit import signed_action

        if not self._kill_switch_ok():
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="order.blocked",
                payload={"reason": "is_trading_enabled is False", "oid": oid},
            )
            return None

        qty_pct = float(kwargs.get("qty_pct", 1.0))
        qty_pct = max(0.0, min(1.0, qty_pct))

        if self._is_spot():
            from apps.exchange.hl_client import build_info

            info = build_info(self.credential.network)
            spot_state = info.spot_user_state(self.credential.wallet_address) or {}
            balances = spot_state.get("balances") or []
            qty = 0.0
            for bal in balances:
                if str(bal.get("coin", "")).upper() == str(self._coin).upper():
                    try:
                        qty = float(bal.get("total", 0))
                    except (TypeError, ValueError):
                        qty = 0.0
                    break
            if qty <= 0:
                return None
            close_qty = qty * qty_pct if qty_pct < 1.0 else qty
            return self._place_spot(is_buy=False, oid=oid, price=price, qty=close_qty)

        exchange = self._get_exchange()
        close_sz = None
        if qty_pct < 1.0:
            from apps.exchange.hl_client import build_info
            from apps.exchange.hl_constants import normalize_coin

            info = build_info(self.credential.network)
            state = info.user_state(self.credential.wallet_address) or {}
            for item in state.get("assetPositions") or []:
                pos = item.get("position") or {}
                if normalize_coin(pos.get("coin", "")) == self._coin:
                    try:
                        sz = abs(float(pos.get("szi", 0)))
                    except (TypeError, ValueError):
                        sz = 0.0
                    if sz > 0:
                        from apps.exchange.hl_meta import get_asset_meta, round_size

                        meta = get_asset_meta(self._name, market_type="perp", network=self.credential.network)
                        close_sz = round_size(sz * qty_pct, meta)
                    break

        def _call():
            return exchange.market_close(coin=self._coin, sz=close_sz)

        resp = signed_action(self.credential, _call, weight=1)
        self.last_action = f"CLOSE {qty_pct * 100:.0f}% at {price}"
        if qty_pct >= 1.0 and oid in self._open_orders:
            del self._open_orders[oid]
        return resp

    def exit(self, oid, price, bar_index, **kwargs):
        stop_px = kwargs.get("stop")
        limit_px = kwargs.get("limit")
        if kwargs.get("update") and (stop_px is not None or limit_px is not None) and not self._is_spot():
            from apps.exchange.hl_client import cancel_all_orders

            cancel_all_orders(self.credential)
            return self._place_perp_tpsl(oid=oid, stop_px=stop_px, limit_px=limit_px)
        if (stop_px is not None or limit_px is not None) and not self._is_spot():
            return self._place_perp_tpsl(oid=oid, stop_px=stop_px, limit_px=limit_px)
        return self.close(oid, price, bar_index)

    # Live broker has no synthetic metrics.
    def finalize(self, last_price, last_bar):
        return

    def metrics(self):
        return {}

    def trades(self):
        return []
