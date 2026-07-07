"""Hyperliquid private WebSocket feed.

Subscribes to:
  - orderUpdates     — order status changes
  - userFills        — fill events (with 2000-item limit guard → REST fallback)
  - clearinghouseState — full account snapshot (isSnapshot) + incremental deltas
  - userTwapSliceFills — TWAP slice fills

On each reconnect, ``reconcile_after_reconnect`` is called before activating
subscriptions to reconcile any orders placed during the disconnect gap.
"""
from __future__ import annotations

import logging
import signal
import threading
import time

from django.utils import timezone

from apps.credentials.models import ExchangeCredential
from apps.execution.order_sync import (
    apply_order_update,
    apply_twap_fill,
    apply_user_fill,
    hydrate_clearinghouse_state,
)
from apps.exchange.hl_constants import network_url

logger = logging.getLogger(__name__)

REGISTRY_POLL_INTERVAL = 5
_USERFILLS_LIMIT = 2000


class UserFeed:
    """Multiplex per-network Info WS and subscribe to private user channels."""

    def __init__(self):
        self._stop = threading.Event()
        self._subscribed: set[tuple[str, int]] = set()  # (network, cred_id)
        self._info_by_network: dict[str, object] = {}
        self._lock = threading.Lock()
        self._last_msg_ts = time.time()
        self._fill_counts: dict[int, int] = {}  # cred_id → cumulative fill count

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
                    logger.exception("error disconnecting websocket during shutdown")

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
                    logger.exception("ping failed")

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

        # Reconcile orders placed during any prior disconnect before we
        # start applying new deltas, to avoid double-counting or gaps.
        try:
            from apps.execution.tasks import reconcile_after_reconnect
            reconcile_after_reconnect(cred_id)
        except Exception:  # noqa: BLE001
            logger.exception("pre-subscribe reconcile failed cred=%s", cred_id)

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
                batch = len(fills)
                self._fill_counts[cred_id] = self._fill_counts.get(cred_id, 0) + batch
                if self._fill_counts[cred_id] >= _USERFILLS_LIMIT:
                    logger.warning(
                        "userFills limit reached cred=%s (seen=%d) — switching to REST",
                        cred_id, self._fill_counts[cred_id],
                    )
                    self._fill_counts[cred_id] = 0
                    from apps.exchange.tasks import fetch_fills_rest_task
                    fetch_fills_rest_task.delay(credential_id=cred_id)
                for f in fills:
                    if isinstance(f, dict):
                        apply_user_fill(credential_id=cred_id, fill=f)
            except Exception:  # noqa: BLE001
                logger.exception("userFills handler failed")

        def on_clearinghouse(msg):
            try:
                if not isinstance(msg, dict) or msg.get("channel") != "clearinghouseState":
                    return
                self._last_msg_ts = time.time()
                data = msg.get("data") or {}
                if data.get("isSnapshot"):
                    # Full account snapshot → seed Redis margin/position cache.
                    hydrate_clearinghouse_state(credential_id=cred_id, state=data)
                else:
                    # Incremental delta → update margin summary in Redis.
                    _apply_clearinghouse_delta(cred_id, data)
            except Exception:  # noqa: BLE001
                logger.exception("clearinghouseState handler failed")

        def on_twap_fills(msg):
            try:
                if not isinstance(msg, dict) or msg.get("channel") != "userTwapSliceFills":
                    return
                self._last_msg_ts = time.time()
                data = msg.get("data") or {}
                fills = data.get("fills") or (data if isinstance(data, list) else [])
                for f in fills:
                    if isinstance(f, dict):
                        apply_twap_fill(credential_id=cred_id, fill=f)
            except Exception:  # noqa: BLE001
                logger.exception("userTwapSliceFills handler failed")

        info.subscribe({"type": "orderUpdates", "user": user}, on_order_updates)
        info.subscribe({"type": "userFills", "user": user}, on_user_fills)
        info.subscribe({"type": "clearinghouseState", "user": user}, on_clearinghouse)
        info.subscribe({"type": "userTwapSliceFills", "user": user}, on_twap_fills)

        cred.last_verified_at = timezone.now()
        cred.save(update_fields=["last_verified_at"])
        logger.info("subscribed user feed %s cred=%s (4 channels)", network, cred_id)

    def _unsubscribe(self, network: str, cred_id: int) -> None:
        self._fill_counts.pop(cred_id, None)
        logger.info("unsubscribed user feed %s cred=%s", network, cred_id)


def _apply_clearinghouse_delta(credential_id: int, data: dict) -> None:
    """Apply a non-snapshot clearinghouseState delta to Redis margin cache."""
    try:
        import redis
        from django.conf import settings

        r = redis.Redis.from_url(
            getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=False,
        )
        margin = data.get("marginSummary") or {}
        if not margin:
            return
        margin_key = f"live:margin:{credential_id}"
        updates = {}
        for field in ("accountValue", "totalMarginUsed", "withdrawable"):
            val = margin.get(field)
            if val is not None:
                updates[field] = str(val)
        if updates:
            r.hset(margin_key, mapping=updates)
            r.expire(margin_key, 3600)
    except Exception:  # noqa: BLE001
        logger.debug("clearinghouse delta update failed cred=%s", credential_id)


def run_user_feed() -> None:
    UserFeed().run()

