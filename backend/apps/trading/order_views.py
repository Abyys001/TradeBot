"""Order routing endpoints (spec §3, §4).

Plain Django **async** views rather than DRF ones: the fan-out is asyncio, and
DRF 3.15 has no async view support, so routing through it would run the legs in
a worker thread and serialise them — exactly what the fan-out deadline cannot
afford.

The cost of leaving DRF behind is that none of its request handling applies
here, so this module owns both halves itself:

  - **CSRF is enforced** (`@csrf_protect`, not `@csrf_exempt`). These endpoints
    authenticate by session cookie and fan a leveraged entry across every
    connected account, so an exempt POST is one any page the admin has open can
    make. SameSite=Lax happens to stop it in a current browser; a money
    endpoint should not rest on a cookie default it does not set.
  - **Every input is validated before it becomes an order.** Nothing downstream
    re-checks: `sizing` divides by the price it is given, and `sltp` turns a
    percentage into a stop price without asking whether the sign makes sense.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from apps.core.auth import admin_required
from apps.core.money import D
from apps.engine.fanout import StopAllActive
from apps.exchanges.base import MarketType, OrderType, Side
from apps.trading.models import Trade, TradeStatus
from apps.trading.services import (
    NoLegsToRoute,
    refresh_balances,
    route_amend,
    route_close,
    route_close_all,
    route_open,
)

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


#: A pair as the platform names it: base + quote, letters and digits only.
#: Anything else is refused here rather than sent to eight different exchanges
#: to be rejected eight different ways — a leg that fails on a malformed symbol
#: reads as an exchange problem in the notification centre, which is a lie.
_SYMBOL = re.compile(r"^[A-Z0-9]{4,20}$")


def _symbol(data: dict) -> str:
    """The pair, normalised once here so every adapter sees the same string."""
    value = str(data.get("symbol") or "").strip().upper()
    if not _SYMBOL.match(value):
        raise ValueError(f"symbol is not a pair: {data.get('symbol')!r}")
    return value


def _percent(data: dict, key: str, *, ceiling: Decimal | None) -> Decimal:
    """An SL/TP percentage, mandatory and bounded.

    Mandatory because protection is part of the order, not an option on top of
    it: spec §4 fans an entry at leverage across every partner account, and a
    leg with no stop is one exchange outage away from an unbounded loss on
    money that is not the admin's. Both percentages are therefore required
    here and turned into real trigger prices per account, which the adapter
    sends *to the exchange* — on the entry order where the venue accepts it,
    and immediately after the fill where it does not (`executor._protect`).
    Nothing is kept as an intention inside the platform.

    Unbounded, these reach `sltp.resolve` and turn into a stop price: a
    negative one puts the stop on the *profit* side of entry, where it fires
    the instant the trade goes right, and a stop loss above 100% is a price
    below zero. Both are typos, and a typo must not become an order.

    The take-profit has no ceiling — a 250% target is a real thing to ask for.
    """
    value = _optional_decimal(data, key)
    if value is None:
        raise ValueError(f"{key} is required — every order carries a stop loss and a take profit")
    if value <= 0:
        raise ValueError(f"{key} must be greater than zero")
    if ceiling is not None and value > ceiling:
        raise ValueError(f"{key} must not exceed {ceiling:g}")
    return value


@sync_to_async
def _filtered(user) -> set[int]:
    from apps.accounts.visibility import _filtered as _f

    return _f(user)


def _result_payload(result, hidden: set[int]) -> dict:
    """The fan-out result as the *caller* is allowed to see it.

    ``total_ms`` is the real wall clock of the whole fan-out and stays whole:
    the legs run concurrently, so it is the slowest leg's time, not a sum, and
    it carries no per-account information. The per-leg lists are the part that
    names accounts, and those are filtered.
    """
    succeeded = [
        {"account_id": leg.account_id, "ms": round(leg.duration_ms, 1)}
        for leg in result.succeeded
        if leg.account_id not in hidden
    ]
    # Spec §4: each of these is also persisted as a notification that stays
    # until the admin dismisses it — and that notification is filtered too, both
    # over the WebSocket and on /notifications/.
    failed = [
        {
            "account_id": leg.account_id,
            "error": leg.error,
            "code": leg.error_code,
            "ms": round(leg.duration_ms, 1),
        }
        for leg in result.failed
        if leg.account_id not in hidden
    ]
    return {
        "total_ms": round(result.total_ms, 1),
        "within_budget": result.within_budget(),
        "succeeded": succeeded,
        "failed": failed,
    }


@csrf_protect
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
        symbol = _symbol(data)
        side = Side(data.get("side", "long"))
        market = MarketType(data.get("market", "futures"))
        order_type = OrderType(data.get("order_type", "market"))
        # A stop loss past 100% is a price below zero; a take profit past it is
        # just an ambitious target, so only the stop is capped.
        sl_pct = _percent(data, "sl_pct", ceiling=Decimal("100"))
        tp_pct = _percent(data, "tp_pct", ceiling=None)
        limit_price = _optional_decimal(data, "limit_price")
    except (ValueError, InvalidOperation) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    if order_type is OrderType.LIMIT and limit_price is None:
        return JsonResponse({"detail": "a limit order needs limit_price"}, status=400)
    if limit_price is not None and limit_price <= 0:
        # Sizing divides by this price. Zero or negative is a division by zero
        # or a negative quantity, neither of which should reach an adapter.
        return JsonResponse({"detail": "limit_price must be greater than zero"}, status=400)

    try:
        trade, result = await route_open(
            symbol=symbol,
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

    hidden = await _filtered(await request.auser())
    return JsonResponse({"trade_id": trade.id, **_result_payload(result, hidden)})


@csrf_protect
@require_POST
@admin_required
async def amend_position(request: HttpRequest, pk: int) -> JsonResponse:
    """Mid-trade SL/TP change (spec §4 — must land within the deadline)."""
    trade = await _get_open_trade(pk)
    if trade is None:
        return JsonResponse({"detail": "no open trade with that id"}, status=404)

    data = _body(request)
    try:
        sl_pct = _percent(data, "sl_pct", ceiling=Decimal("100"))
        tp_pct = _percent(data, "tp_pct", ceiling=None)
    except (ValueError, InvalidOperation) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    try:
        result = await route_amend(trade=trade, sl_pct=sl_pct, tp_pct=tp_pct)
    except NoLegsToRoute as exc:
        return JsonResponse({"detail": str(exc), "code": "no_legs"}, status=409)
    hidden = await _filtered(await request.auser())
    return JsonResponse({"trade_id": trade.id, **_result_payload(result, hidden)})


@csrf_protect
@require_POST
@admin_required
async def close_position(request: HttpRequest, pk: int) -> JsonResponse:
    """Market-close on every account (spec §3). Works even while STOP_ALL is on."""
    trade = await _get_open_trade(pk)
    if trade is None:
        return JsonResponse({"detail": "no open trade with that id"}, status=404)

    try:
        result = await route_close(trade=trade)
    except NoLegsToRoute as exc:
        return JsonResponse({"detail": str(exc), "code": "no_legs"}, status=409)
    hidden = await _filtered(await request.auser())
    # A leg the exchange would not flatten leaves the trade OPEN, so say so
    # rather than letting an empty `failed` list read as "position gone".
    return JsonResponse(
        {"trade_id": trade.id, "closed": result.all_ok, **_result_payload(result, hidden)}
    )


def _merged_payload(closed: list, hidden: set[int]) -> dict:
    """Several trades' fan-outs as one result the panel can render.

    ``total_ms`` is the slowest trade's wall clock, not the sum: they ran
    together, so a sum would report a delay nobody waited. ``closed`` is the
    conjunction — one leg the exchange would not flatten means the answer to
    "is everything closed?" is no, whatever the other trades did.
    """
    merged = {
        "total_ms": 0.0,
        "within_budget": True,
        "succeeded": [],
        "failed": [],
    }
    for _trade, result in closed:
        payload = _result_payload(result, hidden)
        merged["total_ms"] = max(merged["total_ms"], payload["total_ms"])
        merged["within_budget"] &= payload["within_budget"]
        merged["succeeded"].extend(payload["succeeded"])
        merged["failed"].extend(payload["failed"])
    return merged


@csrf_protect
@require_POST
@admin_required
async def close_all_positions(request: HttpRequest) -> JsonResponse:
    """Market-close every open trade (spec §3, §7).

    The panel's close button routes here rather than at one trade id. More than
    one trade can be open at a time — accounts freed by a close can take a new
    entry while the rest are still in the old one — and closing only the one the
    panel happens to be showing left the other live on the exchange with the
    panel reporting flat.

    Works while halted, like the single-trade close: STOP_ALL stops new routing,
    never the way out of a position.
    """
    closed = await route_close_all()
    if not closed:
        return JsonResponse(
            {
                "detail": "no open trade to close",
                "code": "no_open_trades",
                "closed": True,
                "trade_ids": [],
                "total_ms": 0.0,
                "within_budget": True,
                "succeeded": [],
                "failed": [],
            }
        )

    hidden = await _filtered(await request.auser())
    return JsonResponse(
        {
            "trade_ids": [trade.id for trade, _ in closed],
            # False whenever any leg would not flatten: the trade stays OPEN and
            # the panel must not report a close the exchange never made.
            "closed": all(result.all_ok for _, result in closed),
            **_merged_payload(closed, hidden),
        }
    )


@csrf_protect
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
    rows = await refresh_balances(force=force)
    # The fan-out itself still polls every account, hidden ones included —
    # spec §6 wants their balances current too, and the viewer's panel reads
    # them from the same push. Only this caller's copy is trimmed.
    hidden = await _filtered(await request.auser())
    return JsonResponse(
        {"accounts": [row for row in rows if row.get("id") not in hidden]}
    )


@sync_to_async
def _get_open_trade(pk: int) -> Trade | None:
    return Trade.objects.filter(pk=pk, status=TradeStatus.OPEN).first()
