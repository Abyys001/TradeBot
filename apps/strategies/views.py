from rest_framework import status, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.credentials.models import Exchange
from apps.execution.models import ExecutionLog
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

        # Only one bot script may be live at a time for the admin: starting a
        # new one synchronously stops any other currently-active strategy of
        # theirs first, so its status flips to non-active before this request
        # returns -- avoiding a window where two signals could fan out real
        # Tabdeal orders to the same account at once. Scoped to admin role so
        # the shared per-investor /strategies page is unaffected.
        if strategy.user.role == User.Role.ADMIN:
            others = Strategy.objects.filter(
                user=strategy.user, status=Strategy.Status.ACTIVE
            ).exclude(pk=strategy.pk)
            for other in others:
                stop_live_strategy_task(other.pk)

        live_config = strategy.live_config or {}
        copy_mode = bool(live_config.get("copy_trading"))
        leverage = (live_config.get("risk") or {}).get("leverage", live_config.get("leverage"))
        if copy_mode:
            # Fan-out mode: auto-subscribe all active investors' Tabdeal accounts,
            # plus the strategy owner's own active Tabdeal credential if any.
            from apps.copytrading.subscriptions import ensure_owner_subscription, sync_subscriptions

            sync_subscriptions(strategy)
            ensure_owner_subscription(strategy)
        elif leverage and strategy.credential and strategy.credential.exchange == Exchange.HYPERLIQUID:
            from apps.exchange.hl_client import update_leverage

            update_leverage(strategy.credential, strategy.symbol, int(leverage))
        elif leverage and strategy.credential and strategy.credential.exchange == Exchange.TABDEAL:
            # Set leverage up front so a 1207 (futures not active) or invalid-leverage
            # error surfaces synchronously here, before the strategy shows as active,
            # instead of failing silently on the first live bar.
            from apps.exchange.tabdeal_errors import TabdealAPIError
            from apps.exchange.tabdeal_futures import TabdealFuturesClient
            from apps.transpiler.runtime.tabdeal_broker import to_tabdeal_symbol

            client = TabdealFuturesClient(strategy.credential)
            pair = to_tabdeal_symbol(strategy.symbol)
            try:
                client.set_leverage(pair, int(leverage))
            except TabdealAPIError as exc:
                return Response(
                    {"errors": [f"Tabdeal leverage setup failed: [{exc.info.code}] {exc.info.message} — {exc.info.action}"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as exc:  # noqa: BLE001
                return Response(
                    {"errors": [f"Tabdeal leverage setup failed: {type(exc).__name__}"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        start_live_strategy_task.delay(strategy.pk)
        return Response({"status": "starting"}, status=status.HTTP_202_ACCEPTED)


class StrategyPositionsView(APIView):
    """GET positions and funding for a strategy's credential."""

    def get(self, request, pk=None):
        strategy = _user_strategy(request, pk)
        if not strategy.credential:
            return Response({"positions": [], "funding": []})
        if strategy.credential.exchange == Exchange.TABDEAL:
            return Response(self._tabdeal_positions(strategy))

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

    @staticmethod
    def _tabdeal_positions(strategy) -> dict:
        from apps.exchange.tabdeal_futures import TabdealFuturesClient

        try:
            client = TabdealFuturesClient(strategy.credential)
            rows = client.get_positions()
        except Exception:  # noqa: BLE001
            return {"positions": [], "funding": []}
        positions = []
        for pos in rows:
            try:
                amt = float(pos.get("positionAmt", 0))
            except (TypeError, ValueError):
                amt = 0.0
            if amt == 0:
                continue
            positions.append(
                {
                    "coin": pos.get("symbol"),
                    "size": pos.get("positionAmt"),
                    "entry_px": pos.get("entryPrice"),
                    "liquidation_px": pos.get("liquidationPrice"),
                    "unrealized_pnl": pos.get("unRealizedProfit", pos.get("unrealizedProfit")),
                    "leverage": pos.get("leverage"),
                }
            )
        # Tabdeal has no funding-history endpoint wired up yet; PositionsPanel.vue
        # never reads this field for Tabdeal-credentialed strategies.
        return {"positions": positions, "funding": []}


class ClosePositionView(APIView):
    """POST /api/strategies/<id>/close-position/ — market-close a single position.

    Body: ``{"coin": "BTC"}``. De-risk action allowed regardless of the
    kill-switch; only a configured credential is required.
    """

    def post(self, request, pk=None):
        strategy = _user_strategy(request, pk)
        coin = (request.data or {}).get("coin")
        if not coin:
            return Response({"errors": ["coin is required"]}, status=status.HTTP_400_BAD_REQUEST)
        if not strategy.credential:
            return Response(
                {"errors": ["no credential configured"]}, status=status.HTTP_400_BAD_REQUEST
            )

        from apps.exchange.hl_client import close_position

        result = close_position(strategy.credential, coin)
        ExecutionLog.objects.create(
            strategy=strategy,
            level=ExecutionLog.Level.INFO if result.get("ok") else ExecutionLog.Level.ERROR,
            event="position.closed_manual",
            payload={"coin": coin, "result": result},
        )
        http_status = status.HTTP_200_OK if result.get("ok") else status.HTTP_502_BAD_GATEWAY
        return Response(result, status=http_status)


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
