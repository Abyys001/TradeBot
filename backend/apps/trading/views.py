from __future__ import annotations

from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from apps.core.money import D
from apps.exchanges.base import Side
from apps.trading import killswitch
from apps.trading.models import Trade
from apps.trading.serializers import TradeSerializer
from apps.trading.sizing import balance_fraction
from apps.trading.sltp import compare_bases, liquidation_price


class TradeViewSet(viewsets.ReadOnlyModelViewSet):
    """Spec §8: per-account trade history — pair, time, PnL."""

    queryset = Trade.objects.prefetch_related("legs__account")
    serializer_class = TradeSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        account_id = self.request.query_params.get("account")
        if account_id:
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

    # Every open panel must show the halt, not just the tab that flipped it.
    layer = get_channel_layer()
    if layer is not None:
        payload = {**state, "updated_at": str(state["updated_at"])}
        async_to_sync(layer.group_send)("trading", {"type": "stop_all", "payload": payload})
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
