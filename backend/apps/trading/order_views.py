"""Order routing endpoints (spec §3, §4).

Plain Django **async** views rather than DRF ones: the fan-out is asyncio, and
DRF 3.15 has no async view support, so routing through it would run the legs in
a worker thread and serialise them — exactly what the 1-second budget cannot
afford.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.auth import admin_required
from apps.core.money import D
from apps.engine.fanout import StopAllActive
from apps.exchanges.base import MarketType, OrderType, Side
from apps.trading.models import Trade, TradeStatus
from apps.trading.services import refresh_balances, route_amend, route_close, route_open

logger = logging.getLogger(__name__)


def _body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _optional_decimal(data: dict, key: str) -> Decimal | None:
    value = data.get(key)
    if value in (None, ""):
        return None
    try:
        return D(value)
    except ValueError as exc:
        raise ValueError(f"{key} is not a number: {value!r}") from exc


def _result_payload(result) -> dict:
    return {
        "total_ms": round(result.total_ms, 1),
        "within_budget": result.within_budget(),
        "succeeded": [
            {"account_id": leg.account_id, "ms": round(leg.duration_ms, 1)}
            for leg in result.succeeded
        ],
        # Spec §4: each of these is also persisted as a notification that stays
        # until the admin dismisses it.
        "failed": [
            {
                "account_id": leg.account_id,
                "error": leg.error,
                "code": leg.error_code,
                "ms": round(leg.duration_ms, 1),
            }
            for leg in result.failed
        ],
    }


@csrf_exempt
@require_POST
@admin_required
async def open_position(request: HttpRequest) -> JsonResponse:
    """Fan an entry out to every eligible account."""
    data = _body(request)

    try:
        leverage = int(data.get("leverage", 1))
    except (TypeError, ValueError):
        return JsonResponse({"detail": "leverage must be a whole number"}, status=400)

    low, high = settings.TRADING["MIN_LEVERAGE"], settings.TRADING["MAX_LEVERAGE"]
    if not low <= leverage <= high:
        return JsonResponse({"detail": f"leverage must be between {low} and {high}"}, status=400)

    try:
        side = Side(data.get("side", "long"))
        market = MarketType(data.get("market", "futures"))
        order_type = OrderType(data.get("order_type", "market"))
        sl_pct = _optional_decimal(data, "sl_pct")
        tp_pct = _optional_decimal(data, "tp_pct")
        limit_price = _optional_decimal(data, "limit_price")
    except (ValueError, InvalidOperation) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    if order_type is OrderType.LIMIT and limit_price is None:
        return JsonResponse({"detail": "a limit order needs limit_price"}, status=400)

    try:
        trade, result = await route_open(
            symbol=str(data.get("symbol", "BTCUSDT")),
            side=side,
            market=market,
            order_type=order_type,
            leverage=leverage,
            sl_pct=sl_pct,
            tp_pct=tp_pct,
            limit_price=limit_price,
        )
    except StopAllActive as exc:
        # Spec §7: the kill switch refuses new routing. Closing is unaffected.
        return JsonResponse({"detail": str(exc), "code": "stop_all"}, status=409)

    if trade is None:
        # Spec §5/§6: everyone is paused, unusable, or already in a trade.
        return JsonResponse(
            {
                "detail": "no connected account can take this order right now — "
                "each account may hold only one open trade",
                "code": "no_eligible_accounts",
            },
            status=409,
        )

    return JsonResponse({"trade_id": trade.id, **_result_payload(result)})


@csrf_exempt
@require_POST
@admin_required
async def amend_position(request: HttpRequest, pk: int) -> JsonResponse:
    """Mid-trade SL/TP change (spec §4 — 1-second budget)."""
    trade = await _get_open_trade(pk)
    if trade is None:
        return JsonResponse({"detail": "no open trade with that id"}, status=404)

    data = _body(request)
    try:
        sl_pct = _optional_decimal(data, "sl_pct")
        tp_pct = _optional_decimal(data, "tp_pct")
    except (ValueError, InvalidOperation) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    result = await route_amend(trade=trade, sl_pct=sl_pct, tp_pct=tp_pct)
    return JsonResponse({"trade_id": trade.id, **_result_payload(result)})


@csrf_exempt
@require_POST
@admin_required
async def close_position(request: HttpRequest, pk: int) -> JsonResponse:
    """Market-close on every account (spec §3). Works even while STOP_ALL is on."""
    trade = await _get_open_trade(pk)
    if trade is None:
        return JsonResponse({"detail": "no open trade with that id"}, status=404)

    result = await route_close(trade=trade)
    return JsonResponse({"trade_id": trade.id, **_result_payload(result)})


@csrf_exempt
@require_POST
@admin_required
async def refresh_balances_view(request: HttpRequest) -> JsonResponse:
    """Spec §6: refresh every connected account's balance.

    The panel calls this on a timer as well as from the button, so by default
    it is rate-limited server-side (see ``refresh_balances``). ``{"force":true}``
    — what the button sends — skips the guard, because a human asking for fresh
    numbers should get them.
    """
    force = bool(_body(request).get("force"))
    return JsonResponse({"accounts": await refresh_balances(force=force)})


@sync_to_async
def _get_open_trade(pk: int) -> Trade | None:
    return Trade.objects.filter(pk=pk, status=TradeStatus.OPEN).first()
