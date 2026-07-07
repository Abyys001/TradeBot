"""Order lifecycle sync from Hyperliquid WS (orderUpdates / userFills).

Also contains:
  - hydrate_clearinghouse_state: isSnapshot processing for live margin/position state
  - apply_twap_fill: userTwapSliceFills event handler
  - handle_nonfinal_status: marginCanceled / iocCancelRejected gating
"""
from __future__ import annotations

import logging
from decimal import Decimal

import redis
from django.conf import settings
from django.db import transaction

from apps.execution.models import ExecutionLog, OrderRecord
from apps.exchange.ws_manager import publish_update

logger = logging.getLogger(__name__)

_MARGIN_KEY = "live:margin:{cred_id}"
_POS_KEY = "live:pos:{cred_id}:{coin}"
_MARGIN_TTL = 3600

_NONFINAL_RETRYABLE = {"margincanceled", "ioccancelrejected", "reduceonlycanceled"}


def _redis() -> redis.Redis:
    return redis.Redis.from_url(
        getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=False,
    )


def _dec(x) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:  # noqa: BLE001
        logger.warning("_dec conversion failed for %r", x)
        return Decimal("0")


def hydrate_clearinghouse_state(*, credential_id: int, state: dict) -> None:
    """Process a clearinghouseState isSnapshot message into Redis.

    Called once per connection (isSnapshot: true) to seed the live margin and
    position cache used by the risk gate in LiveBroker._risk_gate().

    Redis keys written:
      live:margin:{cred_id}  — hash: accountValue, totalMarginUsed, withdrawable
      live:pos:{cred_id}:{coin}  — hash: szi, entryPx, unrealizedPnl
    """
    try:
        r = _redis()
        margin = state.get("marginSummary") or {}
        margin_key = _MARGIN_KEY.format(cred_id=credential_id)
        r.hset(
            margin_key,
            mapping={
                "accountValue": str(margin.get("accountValue", "0")),
                "totalMarginUsed": str(margin.get("totalMarginUsed", "0")),
                "withdrawable": str(state.get("withdrawable", "0")),
            },
        )
        r.expire(margin_key, _MARGIN_TTL)

        positions = state.get("assetPositions") or []
        coin_count = 0
        for item in positions:
            pos = (item or {}).get("position") or {}
            coin = str(pos.get("coin", "")).upper()
            if not coin:
                continue
            pos_key = _POS_KEY.format(cred_id=credential_id, coin=coin)
            r.hset(
                pos_key,
                mapping={
                    "szi": str(pos.get("szi", "0")),
                    "entryPx": str(pos.get("entryPx", "0")),
                    "unrealizedPnl": str(pos.get("unrealizedPnl", "0")),
                    "leverage": str((pos.get("leverage") or {}).get("value", "1")),
                },
            )
            r.expire(pos_key, _MARGIN_TTL)
            coin_count += 1

        account_value = margin.get("accountValue", "0")
        ExecutionLog.objects.create(
            level=ExecutionLog.Level.INFO,
            event="ws.snapshot.hydrated",
            payload={
                "credential_id": credential_id,
                "account_value": str(account_value),
                "positions": coin_count,
            },
        )
        logger.info(
            "clearinghouse hydrated cred=%s account_value=%s positions=%d",
            credential_id, account_value, coin_count,
        )
    except Exception:  # noqa: BLE001
        logger.exception("hydrate_clearinghouse_state failed cred=%s", credential_id)


@transaction.atomic
def apply_twap_fill(*, credential_id: int, fill: dict) -> None:
    """Apply a userTwapSliceFills event to the matching OrderRecord.

    TWAP fills share the same fill shape as userFills but arrive on a different
    WS channel. We re-use the avg_fill_price accumulation logic.
    """
    oid = str(fill.get("oid", "") or "")
    cloid = str(fill.get("cloid", "") or "")
    px = _dec(fill.get("px"))
    sz = _dec(fill.get("sz"))

    if not oid and not cloid:
        return

    qs = OrderRecord.objects.select_for_update(nowait=True).filter(
        strategy__credential_id=credential_id
    )
    rec = None
    if oid:
        rec = qs.filter(exchange_order_id=oid).order_by("-created_at").first()
    if rec is None and cloid:
        rec = qs.filter(client_order_id=cloid).order_by("-created_at").first()
    if rec is None:
        return

    new_filled = (rec.filled_size or Decimal("0")) + sz
    if new_filled > 0 and px > 0:
        prev_notional = (rec.avg_fill_price or Decimal("0")) * (rec.filled_size or Decimal("0"))
        rec.avg_fill_price = (prev_notional + px * sz) / new_filled

    rec.filled_size = new_filled
    if rec.status not in ("filled", "canceled", "rejected"):
        rec.status = "partially_filled"
    rec.raw = {**(rec.raw or {}), "lastTwapFill": fill}
    rec.save(update_fields=["status", "filled_size", "avg_fill_price", "raw", "updated_at"])

    ExecutionLog.objects.create(
        strategy=rec.strategy,
        level=ExecutionLog.Level.INFO,
        event="twap.fill",
        payload={"oid": oid, "cloid": cloid, "px": str(px), "sz": str(sz)},
    )
    publish_update(
        credential_id,
        {"type": "twap.fill", "oid": oid, "cloid": cloid, "filled_size": str(rec.filled_size)},
    )


def handle_nonfinal_status(*, credential_id: int, cloid: str, status_code: str) -> None:
    """Gate retryability for non-final order statuses.

    HL occasionally emits cancellation events for orders that are still active
    (e.g. ``marginCanceled`` can be a transient margin fluctuation). This
    function checks the live order book before marking the order canceled.

    Retryable statuses: ``marginCanceled``, ``iocCancelRejected``, ``reduceOnlyCanceled``

    If the order is NOT in the active book → mark canceled in DB.
    If the order IS in the active book → log a warning (caller may retry).
    """
    if status_code not in _NONFINAL_RETRYABLE:
        return

    try:
        with transaction.atomic():
            rec = (
                OrderRecord.objects.select_for_update(nowait=True)
                .filter(
                    strategy__credential_id=credential_id,
                    client_order_id=cloid,
                )
                .exclude(status__in=("filled", "canceled", "rejected"))
                .order_by("-created_at")
                .first()
            )
            if rec is None:
                return

            in_active_book = _check_active_book(rec, credential_id)

            if not in_active_book:
                rec.status = "canceled"
                rec.raw = {**(rec.raw or {}), "nonfinal_status": status_code}
                rec.save(update_fields=["status", "raw", "updated_at"])
                ExecutionLog.objects.create(
                    strategy=rec.strategy,
                    level=ExecutionLog.Level.INFO,
                    event="order.nonfinal_cancel",
                    payload={"cloid": cloid, "status_code": status_code},
                )
                publish_update(credential_id, {"type": "order.canceled", "cloid": cloid})
                logger.info(
                    "nonfinal status=%s cloid=%s → marked canceled (not in book)",
                    status_code, cloid,
                )
            else:
                ExecutionLog.objects.create(
                    strategy=rec.strategy,
                    level=ExecutionLog.Level.WARNING,
                    event="order.nonfinal_retry_eligible",
                    payload={"cloid": cloid, "status_code": status_code},
                )
                logger.warning(
                    "nonfinal status=%s cloid=%s → still in book, retry eligible",
                    status_code, cloid,
                )
    except Exception:  # noqa: BLE001
        logger.exception("handle_nonfinal_status failed cloid=%s", cloid)


def _check_active_book(rec: OrderRecord, credential_id: int) -> bool:
    """Return True if the order is still in the HL active order book.

    Tries ``query_order_by_oid`` first (precise match). Falls back to
    ``query_order_by_cloid`` when the ``exchange_order_id`` is empty or the
    OID-based query returns no result — this handles the case where non-final
    status events arrive before the exchange order ID has been assigned.
    """
    try:
        from apps.credentials.models import ExchangeCredential
        from apps.exchange.hl_client import build_info

        cred = ExchangeCredential.objects.filter(pk=credential_id).first()
        if cred is None:
            return False
        info = build_info(cred.network)

        if rec.exchange_order_id:
            try:
                result = info.query_order_by_oid(cred.wallet_address, int(rec.exchange_order_id))
                status = (result or {}).get("order", {}).get("status", "")
                if status in ("open", "resting", "triggered"):
                    return True
            except Exception:  # noqa: BLE001
                logger.debug("_check_active_book oid lookup failed, trying cloid")

        if rec.client_order_id:
            try:
                result = info.query_order_by_cloid(cred.wallet_address, rec.client_order_id)
                status = (result or {}).get("order", {}).get("status", "")
                return status in ("open", "resting", "triggered")
            except Exception:  # noqa: BLE001
                logger.debug("_check_active_book cloid lookup failed")

        return False
    except Exception:  # noqa: BLE001
        logger.exception("_check_active_book failed rec=%s", rec.pk)
        return False


@transaction.atomic
def apply_order_update(*, credential_id: int, update: dict) -> None:
    """Apply an orderUpdates message to matching OrderRecord rows."""
    oid = str(update.get("oid", "") or "")
    cloid = str(update.get("cloid", "") or "")
    status = str(update.get("status", "") or "").lower()

    if not oid and not cloid:
        return

    qs = OrderRecord.objects.select_for_update(nowait=True).filter(strategy__credential_id=credential_id)
    rec = None
    if oid:
        rec = qs.filter(exchange_order_id=oid).order_by("-created_at").first()
    if rec is None and cloid:
        rec = qs.filter(client_order_id=cloid).order_by("-created_at").first()
    if rec is None:
        return

    mapped = {
        "open": "submitted",
        "resting": "submitted",
        "filled": "filled",
        "canceled": "canceled",
        "cancelled": "canceled",
        "rejected": "rejected",
    }.get(status, status or rec.status)

    rec.status = mapped
    rec.raw = {**(rec.raw or {}), "orderUpdates": update}
    rec.save(update_fields=["status", "raw", "updated_at"])

    ExecutionLog.objects.create(
        strategy=rec.strategy,
        level="info",
        event="order.update",
        payload={"oid": oid, "cloid": cloid, "status": mapped},
    )
    publish_update(credential_id, {"type": "order.update", "oid": oid, "cloid": cloid, "status": mapped})

    # Immediately gate non-final statuses against the live order book.
    # If the status was mapped as-is (not one of the well-known codes above)
    # AND it matches a non-final pattern, dispatch to handle_nonfinal_status
    # which will check the HL active book and decide retry vs cancel.
    if mapped == status and status in _NONFINAL_RETRYABLE:
        handle_nonfinal_status(credential_id=credential_id, cloid=cloid, status_code=status)


@transaction.atomic
def apply_user_fill(*, credential_id: int, fill: dict) -> None:
    """Apply a userFills message: filled_size + avg_fill_price."""
    oid = str(fill.get("oid", "") or "")
    cloid = str(fill.get("cloid", "") or "")
    px = _dec(fill.get("px"))
    sz = _dec(fill.get("sz"))

    if not oid and not cloid:
        return

    qs = OrderRecord.objects.select_for_update(nowait=True).filter(strategy__credential_id=credential_id)
    rec = None
    if oid:
        rec = qs.filter(exchange_order_id=oid).order_by("-created_at").first()
    if rec is None and cloid:
        rec = qs.filter(client_order_id=cloid).order_by("-created_at").first()
    if rec is None:
        return

    new_filled = (rec.filled_size or Decimal("0")) + sz
    if new_filled > 0 and px > 0:
        prev_notional = (rec.avg_fill_price or Decimal("0")) * (rec.filled_size or Decimal("0"))
        new_notional = prev_notional + (px * sz)
        rec.avg_fill_price = new_notional / new_filled

    rec.filled_size = new_filled
    if rec.status not in ("filled", "canceled", "rejected"):
        rec.status = "partially_filled"
    rec.raw = {**(rec.raw or {}), "lastFill": fill}
    rec.save(update_fields=["status", "filled_size", "avg_fill_price", "raw", "updated_at"])

    ExecutionLog.objects.create(
        strategy=rec.strategy,
        level="info",
        event="order.fill",
        payload={"oid": oid, "cloid": cloid, "px": str(px), "sz": str(sz)},
    )
    publish_update(
        credential_id,
        {
            "type": "order.fill",
            "oid": oid,
            "cloid": cloid,
            "filled_size": str(rec.filled_size),
            "avg_fill_price": str(rec.avg_fill_price or ""),
        },
    )

