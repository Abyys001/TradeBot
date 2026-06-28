from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.strategies.models import Strategy

from .engine import compile
from .exceptions import PineError
from .models import Backtest
from .serializers import BacktestSerializer
from .tasks import run_backtest_stored_task, run_backtest_task


def _user_strategy(request, pk) -> Strategy:
    return get_object_or_404(Strategy, pk=pk, user=request.user)


def _optional_float(data, key: str) -> float | None:
    if key not in data or data[key] is None:
        return None
    return float(data[key])


class ValidateStrategyView(APIView):
    """POST /api/strategies/<id>/validate/ — compile + semantic check only."""

    def post(self, request, pk=None):
        strategy = _user_strategy(request, pk)
        try:
            compile(strategy.source)
        except PineError as exc:
            strategy.validation_status = "error"
            strategy.validation_error = str(exc)
            strategy.save(update_fields=["validation_status", "validation_error"])
            return Response(
                {"ok": False, "error": str(exc), "line": exc.line, "column": exc.column},
                status=status.HTTP_400_BAD_REQUEST,
            )
        strategy.validation_status = "ok"
        strategy.validation_error = ""
        strategy.save(update_fields=["validation_status", "validation_error"])
        return Response({"ok": True})


class BacktestStrategyView(APIView):
    """POST /api/strategies/<id>/backtest/ — enqueue a backtest.

    Body: {"symbol": "...", "timeframe": "...", "candles": [{open,high,low,close,volume}, ...]}
    """

    def post(self, request, pk=None):
        strategy = _user_strategy(request, pk)
        candles = request.data.get("candles") or []
        if not candles:
            return Response(
                {"error": "candles required"}, status=status.HTTP_400_BAD_REQUEST
            )
        bt = Backtest.objects.create(
            strategy=strategy,
            symbol=request.data.get("symbol", strategy.symbol),
            timeframe=request.data.get("timeframe", ""),
        )
        run_backtest_task.delay(
            bt.id,
            candles,
            commission=_optional_float(request.data, "commission"),
            slippage=_optional_float(request.data, "slippage"),
        )
        return Response({"backtest_id": bt.id}, status=status.HTTP_202_ACCEPTED)


class BacktestStoredStrategyView(APIView):
    """POST /api/strategies/<id>/backtest_stored/ — backtest over stored history.

    Body: {"coin": "BTC", "interval": "1h", "network": "mainnet", "start": <ms?>, "end": <ms?>,
           "commission": <float?>, "slippage": <float?>}
    """

    def post(self, request, pk=None):
        strategy = _user_strategy(request, pk)
        coin = request.data.get("coin") or strategy.symbol
        interval = request.data.get("interval") or strategy.timeframe
        network = request.data.get("network", "mainnet")
        if network not in {"mainnet", "testnet"}:
            return Response(
                {"error": f"invalid network: {network}"}, status=status.HTTP_400_BAD_REQUEST
            )
        if not coin or not interval:
            return Response(
                {"error": "coin and interval required"}, status=status.HTTP_400_BAD_REQUEST
            )
        bt = Backtest.objects.create(
            strategy=strategy,
            symbol=coin,
            timeframe=interval,
            network=network,
        )
        run_backtest_stored_task.delay(
            bt.id,
            coin,
            interval,
            request.data.get("start"),
            request.data.get("end"),
            network=network,
            commission=_optional_float(request.data, "commission"),
            slippage=_optional_float(request.data, "slippage"),
        )
        return Response({"backtest_id": bt.id}, status=status.HTTP_202_ACCEPTED)


class BacktestViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """GET /api/backtests/[<id>/] — status, metrics, trades."""

    serializer_class = BacktestSerializer

    def get_queryset(self):
        return Backtest.objects.filter(
            strategy__user=self.request.user
        ).prefetch_related("trades")

    @action(detail=True, methods=["post"], url_path="resolve-stale")
    def resolve_stale(self, request, pk=None):
        """Force-mark a stuck backtest as failed (e.g., Celery worker offline)."""
        bt = get_object_or_404(Backtest, pk=pk, strategy__user=request.user)
        if bt.status in (Backtest.Status.PENDING, Backtest.Status.RUNNING):
            bt.status = Backtest.Status.FAILED
            bt.error = "Resolved: backtest was stuck (Celery worker may be offline)"
            bt.save(update_fields=["status", "error"])
            return Response(BacktestSerializer(bt).data, status=status.HTTP_200_OK)
        return Response(
            {"error": f"backtest is already {bt.status}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=["post"], url_path="retry-stale")
    def retry_stale(self, request):
        """Re-queue all backtests stuck in pending/running for >5 minutes."""
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(minutes=5)
        stale = Backtest.objects.filter(
            strategy__user=request.user,
            status__in=(Backtest.Status.PENDING, Backtest.Status.RUNNING),
            created_at__lt=cutoff,
        )
        count = stale.count()
        stale.update(
            status=Backtest.Status.FAILED,
            error="Resolved: stuck (no completion in 5+ min)",
        )
        return Response({"resolved": count})
