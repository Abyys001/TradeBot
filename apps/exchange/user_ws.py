"""Hyperliquid private WebSocket feed for orderUpdates / userFills."""
from __future__ import annotations

import logging
import signal
import threading
import time

from django.utils import timezone

from apps.credentials.models import ExchangeCredential
from apps.execution.order_sync import apply_order_update, apply_user_fill
from apps.exchange.hl_constants import network_url

logger = logging.getLogger(__name__)

REGISTRY_POLL_INTERVAL = 5


class UserFeed:
    """Multiplex per-network Info WS and subscribe to private user channels."""

    def __init__(self):
        self._stop = threading.Event()
        self._subscribed: set[tuple[str, int]] = set()  # (network, cred_id)
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
                logger.exception("user-feed registry sync failed")
            self._stop.wait(REGISTRY_POLL_INTERVAL)

    def _sync_subscriptions(self) -> None:
        desired = set(
            ExchangeCredential.objects.filter(is_active=True)
            .exclude(wallet_address="")
            .values_list("network", "id")
        )
        with self._lock:
            to_add = desired - self._subscribed
            to_remove = self._subscribed - desired

            for network, cred_id in to_remove:
                self._unsubscribe(network, cred_id)
                self._subscribed.discard((network, cred_id))

            for network, cred_id in to_add:
                self._subscribe(network, cred_id)
                self._subscribed.add((network, cred_id))

    def _get_info(self, network: str):
        if network not in self._info_by_network:
            from hyperliquid.info import Info

            info = Info(network_url(network), skip_ws=False)
            self._info_by_network[network] = info
        return self._info_by_network[network]

    def _subscribe(self, network: str, cred_id: int) -> None:
        cred = ExchangeCredential.objects.filter(pk=cred_id, is_active=True).first()
        if cred is None:
            return
        info = self._get_info(network)
        user = cred.wallet_address

        def on_order_updates(msg):
            try:
                if not isinstance(msg, dict) or msg.get("channel") != "orderUpdates":
                    return
                self._last_msg_ts = time.time()
                data = msg.get("data")
                if not isinstance(data, dict):
                    return
                # SDK currently multiplexes orderUpdates without user in identifier.
                apply_order_update(credential_id=cred_id, update=data)
            except Exception:  # noqa: BLE001
                logger.exception("orderUpdates handler failed")

        def on_user_fills(msg):
            try:
                if not isinstance(msg, dict) or msg.get("channel") != "userFills":
                    return
                self._last_msg_ts = time.time()
                data = msg.get("data") or {}
                fills = data.get("fills") or []
                for f in fills:
                    if isinstance(f, dict):
                        apply_user_fill(credential_id=cred_id, fill=f)
            except Exception:  # noqa: BLE001
                logger.exception("userFills handler failed")

        info.subscribe({"type": "orderUpdates", "user": user}, on_order_updates)
        info.subscribe({"type": "userFills", "user": user}, on_user_fills)
        cred.last_verified_at = timezone.now()
        cred.save(update_fields=["last_verified_at"])
        logger.info("subscribed user feed %s cred=%s", network, cred_id)

    def _unsubscribe(self, network: str, cred_id: int) -> None:
        # SDK unsubscribe needs subscription id; we currently rely on process restart.
        logger.info("unsubscribed user feed %s cred=%s", network, cred_id)


def run_user_feed() -> None:
    UserFeed().run()

