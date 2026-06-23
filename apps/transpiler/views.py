from rest_framework import mixins, status, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.strategies.models import Strategy

from .engine import compile
from .exceptions import PineError
from .models import Backtest
from .serializers import BacktestSerializer
from .tasks import run_backtest_task


def _user_strategy(request, pk) -> Strategy:
    return get_object_or_404(Strategy, pk=pk, user=request.user)


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
        run_backtest_task.delay(bt.id, candles)
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
