"""Consume Hyperliquid candle Pub/Sub and fan out to Celery."""
from __future__ import annotations

import json
import logging
import signal
import threading

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


def _redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


class CandleConsumer:
    """Subscribe to ``hl:candles:*`` and enqueue ``process_live_bar_task``."""

    def __init__(self):
        self._stop = threading.Event()

    def run(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: self._stop.set())

        prefix = getattr(settings, "HL_CANDLE_CHANNEL_PREFIX", "hl:candles")
        r = _redis()
        pubsub = r.pubsub()
        pubsub.psubscribe(f"{prefix}:*")
        logger.info("listening on %s:*", prefix)

        for message in pubsub.listen():
            if self._stop.is_set():
                break
            if message.get("type") not in ("pmessage", "message"):
                continue
            try:
                self._dispatch(json.loads(message["data"]))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        pubsub.close()

    def _dispatch(self, payload: dict) -> None:
        from apps.exchange.subscriptions import strategies_for
        from apps.transpiler.tasks import process_live_bar_task

        network = payload["network"]
        coin = payload["coin"]
        interval = payload["interval"]
        candle = {
            "ts": int(payload["ts"]),
            "open": float(payload["open"]),
            "high": float(payload["high"]),
            "low": float(payload["low"]),
            "close": float(payload["close"]),
            "volume": float(payload.get("volume", 0)),
        }
        for strategy_id in strategies_for(network, coin, interval):
            process_live_bar_task.delay(strategy_id, candle)
            from apps.paper.tasks import process_paper_bar_task

            process_paper_bar_task.delay(strategy_id, candle)


def run_consumer() -> None:
    CandleConsumer().run()
