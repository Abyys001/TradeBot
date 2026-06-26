"""Hyperliquid public WebSocket feed for closed candlesticks."""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import threading
import time

from apps.dashboard.health import set_market_feed_heartbeat
from apps.exchange.hl_constants import normalize_coin, normalize_interval, network_url
from apps.exchange.subscriptions import list_channels, publish_closed_candle

logger = logging.getLogger(__name__)

REGISTRY_POLL_INTERVAL = 5


class MarketFeed:
    """HL candle WS consumer with dynamic subscription registry."""

    def __init__(self):
        self._stop = threading.Event()
        self._subscribed: set[tuple[str, str, str]] = set()
        self._info_by_network: dict[str, object] = {}
        self._lock = threading.Lock()
        self._last_msg_ts = time.time()

    def run(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: self._stop.set())

        registry = threading.Thread(target=self._poll_registry, daemon=True)
        registry.start()
        ping = threading.Thread(target=self._ping_loop, daemon=True)
        ping.start()

        try:
            while not self._stop.is_set():
                time.sleep(1)
        finally:
            self._stop.set()
            for info in self._info_by_network.values():
                try:
                    info.disconnect_websocket()
                except Exception:  # noqa: BLE001
                    pass

    def _ping_loop(self) -> None:
        interval = 55
        try:
            from django.conf import settings

            interval = int(getattr(settings, "HL_WS_PING_INTERVAL", 55))
        except Exception:  # noqa: BLE001
            interval = 55
        while not self._stop.is_set():
            self._stop.wait(interval)
            if self._stop.is_set():
                return
            if time.time() - float(getattr(self, "_last_msg_ts", 0)) < 60:
                continue
            for info in list(self._info_by_network.values()):
                try:
                    info.ws_manager.ws.send('{"method":"ping"}')
                except Exception:  # noqa: BLE001
                    pass

    def _poll_registry(self) -> None:
        while not self._stop.is_set():
            try:
                self._sync_subscriptions()
            except Exception:  # noqa: BLE001
                logger.exception("subscription sync failed")
            self._stop.wait(REGISTRY_POLL_INTERVAL)

    def _sync_subscriptions(self) -> None:
        desired = set(list_channels())
        with self._lock:
            to_add = desired - self._subscribed
            to_remove = self._subscribed - desired

            for network, coin, interval in to_remove:
                self._unsubscribe(network, coin, interval)
                self._subscribed.discard((network, coin, interval))

            for network, coin, interval in to_add:
                self._subscribe(network, coin, interval)
                self._subscribed.add((network, coin, interval))

    def _get_info(self, network: str):
        if network not in self._info_by_network:
            from hyperliquid.info import Info

            info = Info(network_url(network), skip_ws=False)
            self._info_by_network[network] = info
        return self._info_by_network[network]

    def _subscribe(self, network: str, coin: str, interval: str) -> None:
        info = self._get_info(network)
        coin = normalize_coin(coin)
        interval = normalize_interval(interval)

        def callback(msg):
            self._last_msg_ts = time.time()
            self._handle_message(network, coin, interval, msg)

        info.subscribe({"type": "candle", "coin": coin, "interval": interval}, callback)
        logger.info("subscribed HL %s %s %s", network, coin, interval)

    def _unsubscribe(self, network: str, coin: str, interval: str) -> None:
        info = self._info_by_network.get(network)
        if info is None:
            return
        coin = normalize_coin(coin)
        interval = normalize_interval(interval)
        try:
            info.unsubscribe({"type": "candle", "coin": coin, "interval": interval}, None)
        except Exception:  # noqa: BLE001
            pass
        logger.info("unsubscribed HL %s %s %s", network, coin, interval)

    def _handle_message(self, network: str, coin: str, interval: str, msg) -> None:
        if not isinstance(msg, dict):
            return
        if msg.get("channel") != "candle":
            return
        data = msg.get("data")
        if not isinstance(data, dict):
            return
        # HL marks closed candles with boolean `closed` or final bar in stream.
        if not data.get("closed", True):
            return

        try:
            candle = {
                "ts": int(data["t"]),
                "open": float(data["o"]),
                "high": float(data["h"]),
                "low": float(data["l"]),
                "close": float(data["c"]),
                "volume": float(data.get("v", 0)),
            }
        except (KeyError, TypeError, ValueError):
            return

        publish_closed_candle(
            network=network,
            coin=coin,
            interval=interval,
            ts=candle["ts"],
            open_=candle["open"],
            high=candle["high"],
            low=candle["low"],
            close=candle["close"],
            volume=candle["volume"],
        )
        set_market_feed_heartbeat(last_bar_ts=candle["ts"])


def run_feed() -> None:
    MarketFeed().run()


async def run_feed_async() -> None:
    """Async wrapper kept for compatibility with management command."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_feed)
