"""TabdealLiveBroker — routes a *primary* strategy's own live orders to the
strategy owner's Tabdeal futures account (no investor fan-out — that's
apps.transpiler.runtime.tabdeal_broker.TabdealBroker's job).

Same entry/close/exit/finalize/metrics/trades/last_action interface as
LiveBroker so runner.py/engine.py can construct either uniformly. Persists
apps.execution.OrderRecord + apps.execution.ExecutionLog with the same event
vocabulary LiveBroker uses (order.placed/order.rejected/order.blocked,
risk.blocked) so Tabdeal-primary trades look identical in the UI/order
history/execution log stream to HL-primary trades.

Orders here normally end in a terminal OrderRecord.status (filled/rejected).
Any left non-terminal (lost response, crash) are resolved by
apps.execution.tasks.reconcile_orders_task, which queries the Tabdeal order
record by exchange/client order id (§3.4).

Safety protocols (§1 invariant 8, §3.1 invariant 13, §6.2):
- ExecutionMutex per-symbol prevents concurrent orders (§1 invariant 8).
- Auto-SL after every entry: if global_stop_loss_pct is configured, attach SL
  immediately after fill. If SL attachment fails after retries, the position is
  closed to prevent naked exposure (§3.1 invariant 13).
- RiskManager persists halt state via strategy_id so daily-loss/drawdown gates
  survive worker restarts (§2.2).
"""
from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal

from .tabdeal_broker import to_tabdeal_symbol

logger = logging.getLogger(__name__)

# SL attachment retry config.
_SL_MAX_RETRIES = 3
_SL_RETRY_DELAY = 1.0  # seconds, doubled each attempt


def _run_sync(coro):
    """Run an async coroutine from synchronous code (Celery workers, runner.py).

    asyncio.run() creates a fresh event loop each call — safe in prefork
    Celery workers where the main thread has no running loop.
    """
    return asyncio.run(coro)


async def _acquire_mutex(symbol: str, owner: str | None = None, ttl: int = 30):
    """Acquire an ExecutionMutex for *symbol*. Returns the mutex or None."""
    from apps.exchange.execution_mutex import ExecutionMutex

    mutex = ExecutionMutex(symbol, owner=owner, ttl=ttl)
    acquired = await mutex.acquire(retry=True)
    if not acquired:
        return None
    return mutex


class TabdealLiveBroker:
    def __init__(
        self,
        credential,
        strategy,
        symbol,
        *,
        leverage: float | None = None,
        default_qty: float | None = None,
        qty_is_percent_of_equity: bool = False,
    ):
        self.credential = credential
        self.strategy = strategy
        self.symbol = symbol
        self.pair = to_tabdeal_symbol(symbol)
        self.last_action = "No Action"
        self._client_obj = None
        self._leverage_set = False
        self._open_orders: dict[str, dict] = {}
        self._filters = None

        from apps.risk.config import DEFAULT_LEVERAGE, read_risk

        live_config = getattr(strategy, "live_config", None) or {}
        risk = read_risk(live_config)
        self._live_config = live_config
        # The Pine header is the strategy's own statement of size, and it is what
        # the backtest used. When it specifies percent-of-equity, live must match
        # it or backtest results say nothing about live behaviour.
        self._default_qty = default_qty
        self._qty_is_pct = bool(qty_is_percent_of_equity)
        self._position_size_pct = (
            float(default_qty)
            if (qty_is_percent_of_equity and default_qty is not None)
            else float(risk.get("position_size_pct", 20))
        )
        self._leverage = float(leverage if leverage is not None else risk.get("leverage", DEFAULT_LEVERAGE))
        self._global_sl_pct: float | None = (
            float(risk["global_stop_loss_pct"]) if risk.get("global_stop_loss_pct") else None
        )

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

    def _get_filters(self, client):
        from apps.exchange.tabdeal_futures import SymbolFilters

        if self._filters is None:
            filters = None
            try:
                filters = client.symbol_filters(self.pair)
            except Exception:  # noqa: BLE001 — metadata must never block a trade
                filters = None
            # A client that predates symbol_filters (or a stub) can hand back
            # anything; only a real filter set is safe to size against.
            self._filters = (
                filters if isinstance(filters, SymbolFilters) else SymbolFilters(symbol=self.pair)
            )
        return self._filters

    def _compute_qty(self, client, price: float, explicit_qty: float | None = None) -> float:
        """Order quantity, floored to the exchange's lot step.

        Precedence matches the backtest broker: an explicit Pine ``qty=`` wins,
        then the header's percent-of-equity, then the dashboard risk config.
        """
        filters = self._get_filters(client)
        if explicit_qty is not None and float(explicit_qty) > 0:
            return filters.round_qty(float(explicit_qty))
        if not self._qty_is_pct and self._default_qty is not None:
            return filters.round_qty(float(self._default_qty))

        equity = client.available_usdt()
        notional = equity * (self._position_size_pct / 100.0) * self._leverage
        if price <= 0 or notional <= 0:
            return 0.0
        return filters.round_qty(notional / price)

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

        risk_cfg = parse_risk_config(self._live_config)
        risk_manager = RiskManager(
            risk_cfg,
            initial_balance=max(equity, 1.0),
            strategy_id=self.strategy.pk,
        )
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
        # absent status to "filled" rather than "submitted". A genuinely non-terminal
        # order is later resolved by apps.execution.tasks.reconcile_orders_task.
        return mapping.get((resp_status or "").upper(), "filled")

    # ----- naked-position protection (§3.1 invariant 13) -----

    def _attach_sl_after_entry(self, *, entry_oid: str, entry_price: float, is_buy: bool) -> None:
        """Attach stop-loss after a successful fill. If SL attachment fails after
        retries, close the position to prevent naked exposure (§3.1 invariant 13).

        The stop distance is derived from ``global_stop_loss_pct`` in the
        strategy's ``live_config.risk`` block. If that field is not configured,
        this method is a no-op — the position stays unprotected but the
        interpreter's own ``strategy.exit(stop=...)`` may still attach one.
        """
        if self._global_sl_pct is None or self._global_sl_pct <= 0:
            return

        client = self._client()

        # Compute stop price from entry.
        if is_buy:
            sl_price = entry_price * (1.0 - self._global_sl_pct / 100.0)
        else:
            sl_price = entry_price * (1.0 + self._global_sl_pct / 100.0)
        # Two decimals is right for BTC_USDT and wrong for most other pairs;
        # use the symbol's real tick size.
        sl_price = self._get_filters(client).round_price(sl_price)

        # Fetch position id (needed for the positionSlTp endpoint).
        try:
            pos_id = client.get_open_position_id(self.pair)
        except Exception:  # noqa: BLE001
            pos_id = None
        if pos_id is None:
            self._log("warning", "slattach.no_position", {"oid": entry_oid, "pair": self.pair})
            self._close_naked(entry_oid=entry_oid, reason="slattach_no_position")
            return

        # Attempt with retries (§4.3 retry budget).
        last_exc = None
        for attempt in range(_SL_MAX_RETRIES):
            try:
                client.set_position_sl_tp(
                    position_id=pos_id, sl_price=sl_price, symbol=self.pair
                )
                self._log("info", "order.sltp_auto", {
                    "oid": entry_oid, "pair": self.pair, "sl": sl_price, "attempt": attempt + 1,
                })
                # Mark sl_confirmed on StrategyState after successful attach.
                try:
                    self.strategy.state.sl_confirmed = True
                    self.strategy.state.save(update_fields=["sl_confirmed"])
                except Exception:  # noqa: BLE001
                    pass
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self._log("warning", "slattach.retry", {
                    "oid": entry_oid, "attempt": attempt + 1, "error": type(exc).__name__,
                })
                if attempt < _SL_MAX_RETRIES - 1:
                    time.sleep(_SL_RETRY_DELAY * (2 ** attempt))

        # All retries exhausted — close position to prevent naked exposure.
        self._log("error", "slattach.failed", {
            "oid": entry_oid, "pair": self.pair, "error": type(last_exc).__name__,
            "sl_price": sl_price,
        })
        self._close_naked(entry_oid=entry_oid, reason="slattach_failed")

    def _close_naked(self, *, entry_oid: str, reason: str) -> None:
        """Emergency close of an unprotected position (§3.1 invariant 13)."""
        from apps.exchange.tabdeal_errors import TabdealAPIError

        client = self._client()
        try:
            client.close_position(self.pair)
        except TabdealAPIError as exc:
            self._log("error", "naked_close_rejected", {"oid": entry_oid, "error": exc.info.code})
            return
        except Exception as exc:  # noqa: BLE001
            self._log("error", "naked_close_rejected", {"oid": entry_oid, "error": type(exc).__name__})
            return

        # Remove from open tracking.
        self._open_orders.pop(entry_oid, None)
        self.last_action = f"EMERGENCY CLOSE ({reason})"
        self._log("warning", "naked_close_executed", {"oid": entry_oid, "reason": reason, "pair": self.pair})

    # ----- order placement core -----

    def _place(self, *, is_buy: bool, oid, price, qty):
        from apps.exchange.execution_mutex import sync_lock_order
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
            with sync_lock_order(self.pair):
                resp = client.place_market_order(
                    symbol=self.pair, side=tabdeal_side, quantity=qty, price=price, client_order_id=coid,
                )
        except TimeoutError:
            self._log("warning", "order.mutex_contention", {"oid": oid, "symbol": self.pair})
            return None
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
        from apps.watchdog.intent import confirm_intent, publish_entry_intent

        is_buy = str(direction).lower() in ("long", "strategy.long")
        target_side = "long" if is_buy else "short"

        # §1 invariant 8: one in-flight order per symbol.
        mutex = None
        try:
            mutex = _run_sync(_acquire_mutex(self.pair, owner=f"broker-{self.strategy.pk}"))
            if mutex is None:
                self._log("warning", "order.mutex_busy", {"oid": oid, "pair": self.pair})
                return None

            for open_oid, meta in list(self._open_orders.items()):
                if meta.get("side") != target_side:
                    self.close(open_oid, price, bar_index, reason="reversal")

            client = self._client()
            qty_final = self._compute_qty(client, float(price or 0), explicit_qty=qty)
            # Refuse locally with a readable reason rather than letting the
            # exchange bounce it with an opaque filter error.
            reject = self._get_filters(client).reject_reason(qty_final, float(price or 0))
            if reject:
                self._log(
                    "warning",
                    "order.rejected_by_filters",
                    {"oid": oid, "pair": self.pair, "qty": qty_final,
                     "price": price, "reason": reject},
                )
                return None
            if qty_final <= 0:
                self._log("warning", "order.size_zero", {"oid": oid, "pair": self.pair, "price": price})
                return None

            # Publish write-ahead intent before order placement.
            from apps.risk.config import read_risk
            risk = read_risk(self._live_config)
            sl_pct = risk.get("global_stop_loss_pct")
            if sl_pct is not None:
                fill_f = float(price or 0)
                expected_sl = fill_f * (1 - float(sl_pct) / 100.0) if is_buy else fill_f * (1 + float(sl_pct) / 100.0)
            else:
                expected_sl = 0.0
            publish_entry_intent(self.strategy.pk, self.symbol, target_side, qty_final, expected_sl)

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

                # §3.1 invariant 13: auto-attach SL to prevent naked exposure.
                fill_px = float(rec.avg_fill_price or price or 0)
                if fill_px > 0:
                    self._attach_sl_after_entry(entry_oid=str(oid), entry_price=fill_px, is_buy=is_buy)

                confirm_intent(self.strategy.pk, self.symbol)
            else:
                confirm_intent(self.strategy.pk, self.symbol)

            return rec
        finally:
            if mutex is not None:
                _run_sync(mutex.release())

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
        self._open_orders.pop(str(oid), None)
        try:
            self.strategy.state.sl_confirmed = False
            self.strategy.state.save(update_fields=["sl_confirmed"])
        except Exception:  # noqa: BLE001
            pass
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
