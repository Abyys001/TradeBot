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
        if not strategy.credential.is_active:
            errors.append("credential is not active")
        if not strategy.user.is_trading_enabled:
            errors.append("trading is disabled for this user")
        if not strategy.source.strip():
            errors.append("strategy source is empty")

        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        start_live_strategy_task.delay(strategy.pk)
        return Response({"status": "starting"}, status=status.HTTP_202_ACCEPTED)


class StopStrategyView(APIView):
    """POST /api/strategies/<id>/stop/ — stop live execution."""

    def post(self, request, pk=None):
        strategy = _user_strategy(request, pk)
        stop_live_strategy_task.delay(strategy.pk)
        return Response({"status": "stopping"}, status=status.HTTP_202_ACCEPTED)
