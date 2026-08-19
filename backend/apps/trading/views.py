from __future__ import annotations

from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db.models import Prefetch
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from apps.accounts.visibility import _check, accessible
from apps.core.money import D
from apps.exchanges.base import Side
from apps.trading import killswitch
from apps.trading.models import Trade, TradeLeg
from apps.trading.serializers import TradeSerializer
from apps.trading.services import route_close_all
from apps.trading.sizing import balance_fraction
from apps.trading.sltp import compare_bases, liquidation_price


class TradeViewSet(viewsets.ReadOnlyModelViewSet):
    """Spec §8: per-account trade history — pair, time, PnL."""

    queryset = Trade.objects.prefetch_related("legs__account")
    serializer_class = TradeSerializer

    def get_queryset(self):
        """History, with hidden accounts' legs removed for everyone but the viewer.

        Three things happen here, and all three are needed:

        1. The *legs* are prefetched through a filtered queryset, so a trade the
           reader is allowed to see still never carries a hidden account's row,
           fill price, or PnL.
        2. A trade whose every leg is hidden disappears entirely. Otherwise a
           lone entry with no legs in the history would announce that a trade was
           routed to accounts the reader cannot see.
        3. ``?account=`` is resolved against the *visible* accounts first. Doing
           it as another ``.filter()`` on the multi-valued ``legs`` relation
           would spawn a second join, and a trade that had both a visible leg and
           the probed hidden leg would come back — turning the filter into an
           existence oracle for hidden account ids.
        """
        user = self.request.user
        sees_hidden = _check(user)

        legs = TradeLeg.objects.all() if sees_hidden else TradeLeg.objects.filter(
            account__hidden=False
        )
        queryset = Trade.objects.prefetch_related(
            Prefetch("legs", queryset=legs.select_related("account"))
        )
        if not sees_hidden:
            queryset = queryset.filter(legs__account__hidden=False).distinct()

        account_id = self.request.query_params.get("account")
        if account_id:
            if not accessible(user).filter(id=account_id).exists():
                return queryset.none()
            queryset = queryset.filter(legs__account_id=account_id).distinct()
        return queryset


@api_view(["POST"])
@permission_classes([AllowAny])
def risk_preview(request):
    """Answers questions.md Q5a with numbers instead of prose.

    Give it a balance, leverage, entry and SL/TP percentages; it returns what
    those percentages mean under *both* readings — price-basis and margin-basis
    — plus the liquidation price, so the difference is visible rather than
    argued about.

    POST {balance, leverage, entry, side, sl_pct, tp_pct}
    """
    data = request.data
    balance = D(data.get("balance", "1000"))
    leverage = int(data.get("leverage", 10))
    entry = D(data.get("entry", "100000"))
    side = Side(data.get("side", "long"))
    sl_pct = D(data["sl_pct"]) if data.get("sl_pct") not in (None, "") else None
    tp_pct = D(data["tp_pct"]) if data.get("tp_pct") not in (None, "") else None

    margin = balance * balance_fraction()
    notional = margin * D(leverage)
    liq = liquidation_price(side, entry, leverage)

    lines = compare_bases(
        side=side,
        entry=entry,
        leverage=leverage,
        margin=margin,
        notional=notional,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
    )

    def render(line) -> dict:
        return {
            "basis": line.basis,
            "stop_price": _num(line.stop_price),
            "take_profit_price": _num(line.take_profit_price),
            "loss_at_stop": _num(line.loss_at_stop),
            "loss_pct_of_account": _num(line.loss_pct_of_account),
            "profit_at_tp": _num(line.profit_at_tp),
            "price_move_pct": _num(line.price_move_pct),
            "reachable": line.reachable,
            "note": line.note,
        }

    return Response(
        {
            "inputs": {
                "balance": _num(balance),
                "leverage": leverage,
                "entry": _num(entry),
                "side": side.value,
                "sl_pct": _num(sl_pct),
                "tp_pct": _num(tp_pct),
            },
            "position": {
                "balance_fraction": _num(balance_fraction()),
                "margin": _num(margin),
                "notional": _num(notional),
                "qty": _num(notional / entry),
                "liquidation_price": _num(liq),
                "liquidation_distance_pct": _num(abs(entry - liq) / entry * D("100")),
            },
            "readings": {"price": render(lines["price"]), "margin": render(lines["margin"])},
            "active_basis": settings.TRADING["SLTP_BASIS"],
        }
    )


@api_view(["GET"])
def policy(request):
    """The open questions as live settings, so the UI can show what is in force."""
    trading = settings.TRADING
    halt = killswitch.state()
    return Response(
        {
            "balance_fraction": trading["BALANCE_FRACTION"],
            "sltp_basis": trading["SLTP_BASIS"],
            "sltp_reference": trading["SLTP_REFERENCE"],
            "sltp_amend_strategy": trading["SLTP_AMEND_STRATEGY"],
            "sltp_failure_policy": trading["SLTP_FAILURE_POLICY"],
            "reject_sl_beyond_liquidation": trading["REJECT_SL_BEYOND_LIQUIDATION"],
            "fanout_timeout_seconds": trading["FANOUT_TIMEOUT_SECONDS"],
            "leverage_range": [trading["MIN_LEVERAGE"], trading["MAX_LEVERAGE"]],
            # Effective value: the environment pin OR the runtime switch.
            "stop_all": halt["stop_all"],
            "stop_all_locked": halt["locked"],
            "stop_all_source": halt["source"],
            "stop_all_reason": halt["reason"],
            "open_questions": {
                "sltp_basis": "Q5a",
                "sltp_reference": "Q5b/Q5c",
                "sltp_amend_strategy": "Q5d",
                "sltp_failure_policy": "Q5e",
                "balance_fraction": "Q12",
            },
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def stop_all(request):
    """Spec §7's emergency halt, as a control rather than a redeploy.

    Staff-gated like the routing endpoints: halting every account's trading is
    as consequential as starting it. Turning it *on* is deliberately the cheap
    direction — no confirmation payload is required, because the moment this is
    wanted is the moment nobody should be filling in a form.

    Closing and amending open positions keep working while it is on; that is the
    design, not an oversight. A halt that stranded open leveraged positions
    without a way out would be more dangerous than the thing it stops.

    ``close_positions`` (what the panel's Stop-all button sends, with ``on``
    true) also **flattens every open trade** — the halt alone stops the next
    order, which is no help when the danger is the position already running at
    leverage. The halt is applied *first* so nothing new can be routed into the
    gap while the close fans out, and the close is reported back rather than
    assumed: a leg the exchange would not flatten leaves its trade OPEN and
    raises its own spec §4 notice.

    It is a parameter and not the default because this endpoint is not only the
    button: a halt flipped by anything else must keep Q14's meaning — stop new
    routing, touch nothing that is already live.
    """
    if request.method == "GET":
        return Response(killswitch.state())

    requested = request.data.get("on")
    if not isinstance(requested, bool):
        return Response({"detail": "'on' must be true or false"}, status=400)

    try:
        state = killswitch.set_stop_all(
            requested,
            actor=request.user.get_username(),
            reason=str(request.data.get("reason") or ""),
        )
    except PermissionError as exc:
        return Response({"detail": str(exc), "code": "stop_all_locked"}, status=409)

    flattened: dict | None = None
    if requested and bool(request.data.get("close_positions")):
        closed = async_to_sync(route_close_all)()
        flattened = {
            "trade_ids": [trade.id for trade, _ in closed],
            "closed": all(result.all_ok for _, result in closed),
            "failed": [
                {"account_id": leg.account_id, "error": leg.error, "code": leg.error_code}
                for _trade, result in closed
                for leg in result.failed
            ],
        }

    # Every open panel must show the halt, not just the tab that flipped it.
    layer = get_channel_layer()
    if layer is not None:
        payload = {**state, "updated_at": str(state["updated_at"])}
        async_to_sync(layer.group_send)("trading", {"type": "stop_all", "payload": payload})
    if flattened is not None:
        # Hidden accounts are filtered on the read surfaces; this response only
        # ever reaches the staff caller that pressed the button, and the leg
        # detail it carries is the same the notification centre already filters.
        from apps.accounts.visibility import _filtered

        hidden = _filtered(request.user)
        flattened["failed"] = [
            leg for leg in flattened["failed"] if leg["account_id"] not in hidden
        ]
        return Response({**state, "flattened": flattened})
    return Response(state)


@api_view(["GET"])
def exchanges(request):
    """Per-exchange capabilities for the panel.

    Spec §9 / Q9: exchanges without a test environment are labelled here so the
    panel can say so instead of pretending a testnet exists.
    """
    from apps.exchanges.registry import testnet_support

    return Response({"exchanges": testnet_support()})


def _num(value: Decimal | None) -> str | None:
    """Plain decimal string — never scientific notation, which the UI cannot parse."""
    if value is None:
        return None
    return f"{round(value, 8).normalize():f}"
