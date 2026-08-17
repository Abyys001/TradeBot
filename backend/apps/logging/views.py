from __future__ import annotations

from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.logging.models import LogEntry
from apps.logging.serializers import LogEntrySerializer


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

        return qs.order_by("-timestamp")

    @action(detail=False, methods=["post"])
    def prune(self, request: Request) -> Response:
        days = int(request.data.get("days", 30))
        cutoff = timezone.now() - timezone.timedelta(days=days)
        deleted, _ = LogEntry.objects.filter(timestamp__lt=cutoff).delete()
        return Response({"pruned": deleted})
