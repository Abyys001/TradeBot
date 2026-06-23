"""Dashboard REST API views."""
from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.credentials.models import ExchangeCredential
from apps.exchange.candles import BAR_MAP, CandleFetchError, fetch_candles
from apps.execution.models import ExecutionLog, OrderRecord
from apps.strategies.models import Strategy
from apps.transpiler.models import BacktestTrade

from .health import get_celery_status, get_market_feed_status
from .overview import build_overview_payload
from .tasks import emergency_stop_all_task


def build_health_payload(*, user) -> dict:
    credentials = []
    active_strategies = 0
    is_trading_enabled = False
    if user is not None and user.is_authenticated:
        credentials = [
            {
                "id": c.pk,
                "label": c.label,
                "is_active": c.is_active,
                "network": c.network,
                "wallet_address": c.wallet_address,
                "last_verified_at": c.last_verified_at,
            }
            for c in ExchangeCredential.objects.filter(user=user)
        ]
        active_strategies = Strategy.objects.filter(
            user=user, status=Strategy.Status.ACTIVE
        ).count()
        is_trading_enabled = bool(user.is_trading_enabled)

    return {
        "hl_market_feed": get_market_feed_status(),
        "celery": get_celery_status(),
        "credentials": credentials,
        "active_strategies": active_strategies,
        "is_trading_enabled": is_trading_enabled,
    }


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.pk,
                "username": user.username,
                "email": user.email,
                "is_trading_enabled": user.is_trading_enabled,
            }
        )


class KillSwitchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        enabled = request.data.get("enabled", False)
        close_positions = request.data.get("close_positions", False)

        if not enabled and close_positions:
            emergency_stop_all_task.delay(request.user.pk)
            return Response({"status": "emergency_stop_queued"}, status=status.HTTP_202_ACCEPTED)

        request.user.is_trading_enabled = bool(enabled)
        request.user.save(update_fields=["is_trading_enabled"])
        return Response({"is_trading_enabled": request.user.is_trading_enabled})


class HealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_health_payload(user=request.user))


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_overview_payload(request.user))


class CandlesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        symbol = request.query_params.get("symbol", "BTC")
        bar = request.query_params.get("bar", "1m")
        try:
            limit = min(int(request.query_params.get("limit", 500)), 1000)
        except (TypeError, ValueError):
            return Response({"error": "invalid limit"}, status=status.HTTP_400_BAD_REQUEST)

        if bar not in BAR_MAP:
            return Response({"error": f"unsupported bar: {bar}"}, status=status.HTTP_400_BAD_REQUEST)

        network = request.query_params.get("network", "testnet")
        try:
            df = fetch_candles(symbol, bar, limit, network=network)
        except (CandleFetchError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        candles = [
            {
                "time": int(row.ts // 1000),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
            for row in df.itertuples()
        ]
        return Response({"symbol": symbol, "bar": bar, "candles": candles})


class MarkersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        strategy_id = request.query_params.get("strategy_id")
        source = request.query_params.get("source", "live")
        if not strategy_id:
            return Response({"error": "strategy_id required"}, status=status.HTTP_400_BAD_REQUEST)

        strategy = get_object_or_404(Strategy, pk=strategy_id, user=request.user)
        markers = []

        if source == "backtest":
            backtest_id = request.query_params.get("backtest_id")
            if not backtest_id:
                return Response({"error": "backtest_id required for backtest source"}, status=status.HTTP_400_BAD_REQUEST)
            trades = BacktestTrade.objects.filter(backtest_id=backtest_id, backtest__strategy=strategy)
            for trade in trades:
                markers.append(
                    {
                        "time": trade.entry_bar,
                        "position": "belowBar",
                        "color": "#22c55e",
                        "shape": "arrowUp",
                        "text": "Buy",
                        "side": trade.side,
                    }
                )
                if trade.exit_bar is not None:
                    markers.append(
                        {
                            "time": trade.exit_bar,
                            "position": "aboveBar",
                            "color": "#ef4444",
                            "shape": "arrowDown",
                            "text": "Sell",
                            "side": trade.side,
                        }
                    )
        else:
            orders = OrderRecord.objects.filter(strategy=strategy).order_by("created_at")
            for order in orders:
                ts = int(order.created_at.timestamp())
                is_buy = order.side == OrderRecord.Side.BUY
                markers.append(
                    {
                        "time": ts,
                        "position": "belowBar" if is_buy else "aboveBar",
                        "color": "#22c55e" if is_buy else "#ef4444",
                        "shape": "arrowUp" if is_buy else "arrowDown",
                        "text": "Buy" if is_buy else "Sell",
                        "side": order.side,
                    }
                )

        return Response({"strategy_id": strategy.pk, "source": source, "markers": markers})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"error": "invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        return Response(
            {
                "id": user.pk,
                "username": user.username,
                "is_trading_enabled": user.is_trading_enabled,
            }
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"status": "logged_out"})


@ensure_csrf_cookie
def csrf_token_view(request):
    return JsonResponse({"csrfToken": get_token(request)})
