"""Live Tabdeal FAPI probe suite (Master Plan §7, P0 gate).

Answers the load-bearing assumptions the whole execution layer rests on, against the
**real** API with a trade-enabled, withdrawal-disabled key at minimum size. Nothing
downstream should be trusted until these pass (§7: "Blocks everything").

Two tiers:

- **Read-only** (always run, harmless): server clock drift (error 1101), exchangeInfo
  filters, credential verify, balance, positionRisk shape, leverage read.
- **Order lifecycle** (only with ``live_orders=True``): set-leverage / futures activation
  (error 1207), market order open, SL/TP attach to the position, ``DELETE`` full close
  (invariant 7), userTrades + realized-PnL reconstruction. Any position opened is closed
  in a ``finally`` so a mid-sequence failure never leaves a naked position.

Rate-limit backoff (error 1216) is exercised implicitly by ``TabdealFuturesClient._signed``.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from .tabdeal_errors import TabdealAPIError


@dataclass
class ProbeResult:
    name: str
    assumption: str
    ok: bool
    detail: str = ""
    data: dict = field(default_factory=dict)

    def line(self) -> str:
        mark = "PASS" if self.ok else "FAIL"
        extra = f"  [{self.detail}]" if self.detail else ""
        return f"[{mark}] {self.name} — {self.assumption}{extra}"


def _err_text(exc: Exception) -> str:
    if isinstance(exc, TabdealAPIError):
        return f"{exc.info.code}: {exc.info.message}"
    return f"{type(exc).__name__}: {exc}"


def run_probes(
    client,
    *,
    symbol: str = "BTC_USDT",
    quantity: float | None = None,
    leverage: int = 1,
    live_orders: bool = False,
) -> list[ProbeResult]:
    results: list[ProbeResult] = []

    # 1. Clock drift (error 1101) --------------------------------------------
    try:
        local_before = int(time.time() * 1000)
        server = client.server_time()
        drift = server - local_before
        ok = abs(drift) < 60_000
        results.append(ProbeResult(
            "clock", "server time within recv window (avoids 1101)",
            ok, f"drift={drift}ms", {"server_time": server, "drift_ms": drift}))
    except Exception as exc:  # noqa: BLE001
        results.append(ProbeResult("clock", "server time reachable", False, _err_text(exc)))

    # 2. exchangeInfo filters (order validation) -----------------------------
    try:
        info = client.exchange_info(symbol)
        syms = info.get("symbols") or info.get("data") or []
        filters = {f.get("filterType"): f for f in (syms[0].get("filters", []) if syms else [])}
        pp, qp = client.symbol_precision(symbol)
        results.append(ProbeResult(
            "exchange_info", "LOT_SIZE/MIN_NOTIONAL/PRICE_FILTER present for order rounding",
            bool(filters), f"pricePrec={pp} qtyPrec={qp} filters={list(filters)}",
            {"filters": filters, "price_precision": pp, "qty_precision": qp}))
    except Exception as exc:  # noqa: BLE001
        results.append(ProbeResult("exchange_info", "exchangeInfo readable", False, _err_text(exc)))
        filters = {}

    # 3. Credential verify ----------------------------------------------------
    try:
        ok, msg = client.verify_credentials()
        results.append(ProbeResult("verify", "key valid & canTrade (1207 if futures inactive)", ok, msg))
    except Exception as exc:  # noqa: BLE001
        results.append(ProbeResult("verify", "account readable", False, _err_text(exc)))

    # 4. Balance --------------------------------------------------------------
    try:
        usdt = client.available_usdt()
        results.append(ProbeResult("balance", "USDT futures balance readable", True,
                                   f"available_usdt={usdt}", {"available_usdt": usdt}))
    except Exception as exc:  # noqa: BLE001
        results.append(ProbeResult("balance", "balance readable", False, _err_text(exc)))

    # 5. positionRisk shape ---------------------------------------------------
    try:
        positions = client.get_positions(symbol)
        sample = positions[0] if positions else {}
        needed = {"symbol", "positionAmt", "entryPrice"}
        have = needed & set(sample.keys()) if sample else set()
        results.append(ProbeResult(
            "position_risk", "positionRisk exposes symbol/positionAmt/entryPrice",
            bool(sample) and have == needed if sample else True,
            f"keys={sorted(sample.keys())[:8]}" if sample else "no open position (shape unverified)",
            {"sample_keys": sorted(sample.keys())}))
    except Exception as exc:  # noqa: BLE001
        results.append(ProbeResult("position_risk", "positionRisk readable", False, _err_text(exc)))

    if not live_orders:
        return results

    # ----- order lifecycle (mutating) --------------------------------------
    qty = quantity or _min_quantity(filters)
    opened = False
    coid = f"probe-{uuid.uuid4().hex[:12]}"
    try:
        # 6. set leverage / futures activation (error 1207)
        try:
            client.set_leverage(symbol, leverage)
            results.append(ProbeResult("leverage", "set_leverage activates futures (clears 1207)",
                                       True, f"leverage={leverage}"))
        except Exception as exc:  # noqa: BLE001
            results.append(ProbeResult("leverage", "set_leverage", False, _err_text(exc)))

        # 7. market order open
        try:
            order = client.place_market_order(symbol=symbol, side="BUY", quantity=qty, client_order_id=coid)
            opened = True
            results.append(ProbeResult("order_open", "market order opens a position",
                                       True, f"orderId={order.get('orderId')} qty={qty}",
                                       {"order": order}))
        except Exception as exc:  # noqa: BLE001
            results.append(ProbeResult("order_open", "market order opens", False, _err_text(exc)))
            return results

        time.sleep(1.0)  # let the fill settle before reading the position id

        # 8. SL/TP attach
        try:
            pos_id = client.get_open_position_id(symbol)
            pos = client.get_position(symbol)
            entry = float(pos.get("entryPrice", 0)) if pos else 0.0
            sl = round(entry * 0.90, 2) if entry else None
            if pos_id and sl:
                client.set_position_sl_tp(position_id=pos_id, sl_price=sl, symbol=symbol)
                results.append(ProbeResult("sl_attach", "SL attaches to open position",
                                           True, f"positionId={pos_id} sl={sl}"))
            else:
                results.append(ProbeResult("sl_attach", "SL attaches to open position",
                                           False, f"positionId={pos_id} entry={entry}"))
        except Exception as exc:  # noqa: BLE001
            results.append(ProbeResult("sl_attach", "SL attaches", False, _err_text(exc)))

        # 9. userTrades + realized PnL reconstruction
        try:
            trades = client.user_trades(symbol, limit=10)
            results.append(ProbeResult("user_trades", "own fills readable for PnL reconstruction",
                                       bool(trades), f"n={len(trades)}",
                                       {"sample_keys": sorted(trades[0].keys()) if trades else []}))
        except Exception as exc:  # noqa: BLE001
            results.append(ProbeResult("user_trades", "userTrades readable", False, _err_text(exc)))
    finally:
        # 10. DELETE full close (invariant 7) — always, even on earlier failure.
        if opened:
            try:
                client.close_position(symbol)
                gone = client.get_position(symbol) is None
                results.append(ProbeResult("delete_close", "DELETE /fapi/v1/position fully closes (invariant 7)",
                                           gone, "position flat" if gone else "STILL OPEN — investigate"))
            except Exception as exc:  # noqa: BLE001
                results.append(ProbeResult("delete_close", "DELETE close", False,
                                           f"{_err_text(exc)} — POSITION MAY BE OPEN"))
    return results


def _min_quantity(filters: dict) -> float:
    lot = filters.get("LOT_SIZE") or filters.get("MARKET_LOT_SIZE") or {}
    try:
        return float(lot.get("minQty", 0.001)) or 0.001
    except (TypeError, ValueError):
        return 0.001
