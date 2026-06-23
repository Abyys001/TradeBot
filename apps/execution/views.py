from django.db.models import Q

from rest_framework import mixins, viewsets

from .models import ExecutionLog, OrderRecord
from .serializers import ExecutionLogSerializer, OrderRecordSerializer


class OrderRecordViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Read-only listing of the user's order records."""

    serializer_class = OrderRecordSerializer

    def get_queryset(self):
        qs = OrderRecord.objects.filter(strategy__user=self.request.user)
        strategy_id = self.request.query_params.get("strategy")
        if strategy_id:
            qs = qs.filter(strategy_id=strategy_id)
        return qs


class ExecutionLogViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Read-only listing of the user's execution logs."""

    serializer_class = ExecutionLogSerializer

    def get_queryset(self):
        user = self.request.user
        qs = ExecutionLog.objects.filter(
            Q(strategy__user=user) | Q(strategy__isnull=True, payload__user_id=user.pk)
        )
        strategy_id = self.request.query_params.get("strategy")
        if strategy_id:
            qs = qs.filter(strategy_id=strategy_id)
        level = self.request.query_params.get("level")
        if level:
            qs = qs.filter(level=level)
        limit = self.request.query_params.get("limit")
        if limit:
            try:
                return qs[: int(limit)]
            except ValueError:
                pass
        return qs
