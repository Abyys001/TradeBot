from __future__ import annotations

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.logging.models import LogEntry
from apps.logging.serializers import LogEntrySerializer

# The table grows without bound (every engine/exchange/trade event is a row) and
# the frontend expects a plain array, not a paginated envelope — so instead of
# DRF pagination the view caps every response itself. Unbounded here previously
# meant the *entire* log history shipped to the browser on every request.
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


class LogEntryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LogEntrySerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        qs = LogEntry.objects.all()

        level = self.request.query_params.get("level")
        if level:
            qs = qs.filter(level=level.upper())

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category.upper())

        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(source__icontains=source)

        account_id = self.request.query_params.get("account_id")
        if account_id:
            qs = qs.filter(account_id=account_id)

        exchange = self.request.query_params.get("exchange")
        if exchange:
            qs = qs.filter(exchange__iexact=exchange)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(message__icontains=search)

        # Keyset pagination: "give me the page older than the last row I have",
        # so scrolling further back stays a cheap indexed query even once the
        # table holds millions of rows — unlike offset pagination, which gets
        # slower the deeper the admin scrolls.
        before_id = self.request.query_params.get("before_id")
        if before_id:
            try:
                qs = qs.filter(id__lt=int(before_id))
            except ValueError:
                pass

        return qs.order_by("-timestamp")

    def list(self, request: Request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        try:
            limit = int(request.query_params.get("limit", DEFAULT_LIMIT))
        except ValueError:
            limit = DEFAULT_LIMIT
        limit = max(1, min(limit, MAX_LIMIT))
        serializer = self.get_serializer(queryset[:limit], many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def prune(self, request: Request) -> Response:
        days = int(request.data.get("days", 30))
        cutoff = timezone.now() - timezone.timedelta(days=days)
        deleted, _ = LogEntry.objects.filter(timestamp__lt=cutoff).delete()
        return Response({"pruned": deleted})
