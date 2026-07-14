from rest_framework import status, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.transpiler.tasks import start_live_strategy_task, stop_live_strategy_task

from .models import Strategy
from .serializers import StrategySerializer


class StrategyViewSet(viewsets.ModelViewSet):
    serializer_class = StrategySerializer

    def get_queryset(self):
        return Strategy.objects.filter(user=self.request.user).select_related("state")


def _user_strategy(request, pk) -> Strategy:
    return get_object_or_404(
        Strategy.objects.select_related("credential", "user", "state"),
        pk=pk,
        user=request.user,
    )


class StartStrategyView(APIView):
    """POST /api/strategies/<id>/start/ — seed, warmup, and begin live execution."""

    def post(self, request, pk=None):
        strategy = _user_strategy(request, pk)
        errors = []

        if strategy.status == Strategy.Status.ACTIVE:
            errors.append("strategy is already active")
        if strategy.validation_status != "ok":
            errors.append("strategy source is not validated")
        if not strategy.credential:
            errors.append("no credential configured")
        elif not strategy.credential.is_active:
            errors.append("credential is not active")
        if not strategy.user.is_trading_enabled:
            errors.append("trading is disabled for this user")
        if not strategy.source.strip():
            errors.append("strategy source is empty")

        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        live_config = strategy.live_config or {}
        copy_mode = bool(live_config.get("copy_trading"))
        leverage = live_config.get("leverage")
        if copy_mode:
            # Fan-out mode: auto-subscribe all active investors' Tabdeal accounts.
            from apps.copytrading.subscriptions import sync_subscriptions

            sync_subscriptions(strategy)
        elif leverage and strategy.credential:
            from apps.exchange.hl_client import update_leverage

            update_leverage(strategy.credential, strategy.symbol, int(leverage))

        start_live_strategy_task.delay(strategy.pk)
        return Response({"status": "starting"}, status=status.HTTP_202_ACCEPTED)


class StrategyPositionsView(APIView):
    """GET positions and funding for a strategy's credential."""

    def get(self, request, pk=None):
        strategy = _user_strategy(request, pk)
        if not strategy.credential:
            return Response({"positions": [], "funding": []})
        from apps.exchange.hl_client import build_info

        info = build_info(strategy.credential.network)
        state = info.user_state(strategy.credential.wallet_address) or {}
        positions = []
        for item in state.get("assetPositions") or []:
            pos = item.get("position") or {}
            if not pos.get("coin"):
                continue
            positions.append(
                {
                    "coin": pos.get("coin"),
                    "size": pos.get("szi"),
                    "entry_px": pos.get("entryPx"),
                    "liquidation_px": pos.get("liquidationPx"),
                    "unrealized_pnl": pos.get("unrealizedPnl"),
                    "leverage": (item.get("leverage") or {}).get("value"),
                }
            )
        funding = []
        try:
            history = info.user_funding(strategy.credential.wallet_address) or []
            for row in history[-20:]:
                funding.append(row)
        except Exception:  # noqa: BLE001
            pass
        return Response({"positions": positions, "funding": funding})


class StrategyEnginesView(APIView):
    def get(self, request):
        from apps.strategies.plugins.registry import list_engines

        return Response({"engines": list_engines()})


class StopStrategyView(APIView):
    """POST /api/strategies/<id>/stop/ — stop live execution."""

    def post(self, request, pk=None):
        strategy = _user_strategy(request, pk)
        stop_live_strategy_task.delay(strategy.pk)
        return Response({"status": "stopping"}, status=status.HTTP_202_ACCEPTED)
