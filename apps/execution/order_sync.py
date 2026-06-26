"""Order lifecycle sync from Hyperliquid WS (orderUpdates / userFills)."""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.execution.models import ExecutionLog, OrderRecord
from apps.exchange.ws_manager import publish_update


def _dec(x) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:  # noqa: BLE001
        return Decimal("0")


@transaction.atomic
def apply_order_update(*, credential_id: int, update: dict) -> None:
    """Apply an orderUpdates message to matching OrderRecord rows."""
    oid = str(update.get("oid", "") or "")
    cloid = str(update.get("cloid", "") or "")
    status = str(update.get("status", "") or "").lower()

    if not oid and not cloid:
        return

    qs = OrderRecord.objects.select_for_update().filter(strategy__credential_id=credential_id)
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


@transaction.atomic
def apply_user_fill(*, credential_id: int, fill: dict) -> None:
    """Apply a userFills message: filled_size + avg_fill_price."""
    oid = str(fill.get("oid", "") or "")
    cloid = str(fill.get("cloid", "") or "")
    px = _dec(fill.get("px"))
    sz = _dec(fill.get("sz"))

    if not oid and not cloid:
        return

    qs = OrderRecord.objects.select_for_update().filter(strategy__credential_id=credential_id)
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

