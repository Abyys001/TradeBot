"""Tabdeal FAPI trade-broadcast WebSocket client (Master Plan §3.1, Node A ingest).

Connects to the public, unauthenticated **broadcast** endpoint
(``wss://api1.tabdeal.org/special_margin/broadcast/``, Tabdeal_API_Reference.md §10.2).
Protocol is *plain text*: immediately after connecting, send the raw market string
(e.g. ``"BTC_USDT"``); the server then streams ``{"trade": {...}}`` for every trade.

One connection per market (the broadcast subscribe string is a single market). Each
connection normalizes trades and pushes them onto a shared bounded queue owned by the
ingest command. Design invariants realized here:

- **Exchange timestamp only** (invariant 4): ``ts`` comes from the trade payload, never
  ``time.time()``.
- **Per-node trade-id dedupe** (§3.1): a bounded ring of recently-seen ids drops the
  replays that follow a reconnect, before they reach the queue.
- **Expected hourly reconnect** (§10): a plain-text ``connection closed ok`` frame is a
  normal, planned reconnect — not an error.
- **Coverage honesty**: on every (re)connect the client signals a gap so the ledger opens
  a fresh coverage interval across the socket-down window.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Awaitable, Callable

from .tabdeal_constants import broadcast_url

logger = logging.getLogger(__name__)

# Aliases seen across Tabdeal REST recent-trades (§4.2: id/price/qty/time/isBuyerMaker)
# and Binance-style stream payloads (t/p/q/T/m). The broadcast inner-trade schema is
# confirmed live in P0; this normalizer is deliberately tolerant until then.
_ID_KEYS = ("id", "tradeId", "trade_id", "t", "a")
_TS_KEYS = ("time", "T", "ts", "timestamp", "E")
_PRICE_KEYS = ("price", "p")
_QTY_KEYS = ("qty", "quantity", "amount", "q")
_SIDE_KEYS = ("side", "S", "direction")

_DEDUPE_RING = 4096


def _first(d: dict, keys: tuple[str, ...]):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def normalize_trade(message: str) -> dict | None:
    """Parse one broadcast frame → a ledger row, or ``None`` if it isn't a trade.

    Returns ``{trade_id, ts, price, qty, side, raw}`` with ``ts`` in exchange ms.
    Tolerant of the ``{"trade": {...}}`` wrapper and of a bare flat dict.
    """
    try:
        obj = json.loads(message)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None

    trade = obj.get("trade") if isinstance(obj.get("trade"), dict) else obj
    tid = _first(trade, _ID_KEYS)
    price = _first(trade, _PRICE_KEYS)
    qty = _first(trade, _QTY_KEYS)
    ts = _first(trade, _TS_KEYS)
    if tid is None or price is None or ts is None:
        return None

    try:
        ts_ms = int(ts)
        # Some feeds emit seconds; promote to ms if the value is implausibly small.
        if ts_ms < 10_000_000_000:
            ts_ms *= 1000
        row = {
            "trade_id": str(tid),
            "ts": ts_ms,
            "price": float(price),
            "qty": float(qty) if qty is not None else 0.0,
            "side": _resolve_side(trade),
            "raw": message if len(message) <= 2000 else message[:2000],
        }
    except (TypeError, ValueError):
        return None
    return row


def _resolve_side(trade: dict) -> str:
    side = _first(trade, _SIDE_KEYS)
    if isinstance(side, str) and side:
        s = side.lower()
        if s in ("buy", "sell"):
            return s
        if s in ("b", "bid"):
            return "buy"
        if s in ("s", "ask"):
            return "sell"
    maker = trade.get("isBuyerMaker", trade.get("m"))
    if isinstance(maker, bool):
        # Buyer is the maker → aggressor is the seller → trade side "sell".
        return "sell" if maker else "buy"
    return ""


TradeCallback = Callable[[str, dict], Awaitable[None]]
GapCallback = Callable[[str], None]


class TabdealBroadcastClient:
    """Runs one reconnecting broadcast connection per symbol, feeding a callback."""

    def __init__(
        self,
        symbols: list[str],
        on_trade: TradeCallback,
        on_gap: GapCallback | None = None,
        *,
        url: str | None = None,
        ping_interval: float = 20.0,
        max_backoff: float = 30.0,
    ):
        self._symbols = [s.strip().upper() for s in symbols]
        self._on_trade = on_trade
        self._on_gap = on_gap
        self._url = url or broadcast_url()
        self._ping_interval = ping_interval
        self._max_backoff = max_backoff
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        await asyncio.gather(*(self._run_symbol(s) for s in self._symbols))

    async def _run_symbol(self, symbol: str) -> None:
        import websockets  # lazy: keeps the pure normalizer importable without the dep

        seen: deque[str] = deque(maxlen=_DEDUPE_RING)
        seen_set: set[str] = set()
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    self._url, ping_interval=self._ping_interval, open_timeout=15
                ) as ws:
                    await ws.send(symbol)  # plain-text subscribe (§10.2)
                    if self._on_gap:
                        self._on_gap(symbol)  # (re)connect → new coverage interval
                    logger.info("broadcast connected: %s", symbol)
                    backoff = 1.0
                    await self._consume(ws, symbol, seen, seen_set)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect on any socket error
                if self._stop.is_set():
                    break
                logger.warning("broadcast %s dropped (%s); reconnect in %.1fs", symbol, exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)

    async def _consume(self, ws, symbol: str, seen: deque, seen_set: set) -> None:
        async for message in ws:
            if self._stop.is_set():
                return
            text = message if isinstance(message, str) else message.decode("utf-8", "ignore")
            # Planned hourly reconnect (§10): server sends plain text, close and reopen.
            if "connection closed ok" in text:
                logger.info("broadcast %s: planned reconnect", symbol)
                return
            if '"error"' in text and "Invalid params" in text:
                logger.error("broadcast %s: server rejected subscribe (%s)", symbol, text)
                await asyncio.sleep(5)
                return
            row = normalize_trade(text)
            if row is None:
                continue
            tid = row["trade_id"]
            if tid in seen_set:
                continue  # replay after reconnect — deduped before the queue (§3.1)
            if len(seen) == seen.maxlen:
                seen_set.discard(seen[0])
            seen.append(tid)
            seen_set.add(tid)
            await self._on_trade(symbol, row)
