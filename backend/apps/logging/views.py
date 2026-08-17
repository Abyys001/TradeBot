from __future__ import annotations

import logging

from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.visibility import hidden_ids_for
from apps.logging.models import Category, Level, LogEntry
from apps.logging.serializers import LogEntrySerializer

# The table grows without bound (every engine/exchange/trade event is a row) and
# the frontend expects a plain array, not a paginated envelope — so instead of
# DRF pagination the view caps every response itself. Unbounded here previously
# meant the *entire* log history shipped to the browser on every request.
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000

#: Refuse `days=0`: it would delete the entire table under a name that reads
#: like housekeeping. Keeping the newest day is the smallest honest prune.
MIN_PRUNE_DAYS = 1

logger = logging.getLogger("apps.logging.admin")


class LogEntryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LogEntrySerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        qs = self._visible(LogEntry.objects.all())

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
            try:
                requested = int(account_id)
            except ValueError:
                qs = qs.none()
            else:
                # A hidden id must answer exactly like an id with no rows,
                # otherwise the filter is an existence oracle.
                qs = qs.none() if requested in self._hidden_ids else qs.filter(account_id=requested)

        exchange = self.request.query_params.get("exchange")
        if exchange:
            qs = qs.filter(exchange__iexact=exchange)

        request_id = self.request.query_params.get("request_id")
        if request_id:
            qs = qs.filter(request_id=request_id)

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

        # `-id` is not decoration: the cursor above is an *id*, so ordering by
        # timestamp alone left rows sharing a timestamp in an order the database
        # was free to change between two pages — which is how a keyset page can
        # both repeat a row and skip its neighbour.
        return qs.order_by("-timestamp", "-id")

    @cached_property
    def _hidden_ids(self) -> set[int]:
        """Cached for the request: every filter below consults it."""
        return hidden_ids_for(self.request.user)

    def _visible(self, qs):
        """Strip rows that would report a hidden account's existence.

        Two carriers, because a log row can name an account either way:

        1. ``account_id`` — the fan-out's per-leg warnings, and (since the
           access middleware tags them) any request whose URL named an account.
        2. ``trade_id`` — a trade every one of whose legs is hidden is not
           visible in history, so an engine row citing its id would be the only
           place it surfaced. Mirrors ``TradeViewSet.get_queryset``.

        Rows carrying neither are untouched: the vast majority of the table.
        Note this excludes *hidden* ids rather than keeping *known* ones — a row
        about an account that has since been deleted is still real history and
        stays readable.
        """
        hidden = self._hidden_ids
        if not hidden:
            return qs

        from apps.trading.models import Trade

        hidden_trades = Trade.objects.exclude(legs__account__hidden=False).values("pk")
        return qs.filter(Q(account_id__isnull=True) | ~Q(account_id__in=hidden)).filter(
            Q(trade_id__isnull=True) | ~Q(trade_id__in=hidden_trades)
        )

    def list(self, request: Request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        try:
            limit = int(request.query_params.get("limit", DEFAULT_LIMIT))
        except ValueError:
            limit = DEFAULT_LIMIT
        limit = max(1, min(limit, MAX_LIMIT))
        serializer = self.get_serializer(queryset[:limit], many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def facets(self, request: Request) -> Response:
        """The values the filter controls should offer.

        The panel used to hardcode its own two lists and they had drifted: two
        of the seven categories the backend writes (``AUTH``, ``MARKET_DATA``)
        were unreachable from the UI, so rows in them could not be filtered and
        rendered as an unlabelled colour. Serving the choices means one source
        of truth, and adding a category is a backend-only change.
        """
        return Response(
            {
                "levels": [lv.value for lv in Level],
                "categories": [cat.value for cat in Category],
            }
        )

    @action(detail=False, methods=["post"])
    def prune(self, request: Request) -> Response:
        raw = request.data.get("days", 30)
        try:
            days = int(raw)
        except (TypeError, ValueError):
            # A non-numeric `days` used to raise straight out of the view: a 500
            # on an endpoint whose job is deleting rows is the worst possible
            # place for an ambiguous outcome.
            return Response(
                {"detail": "days must be an integer"}, status=status.HTTP_400_BAD_REQUEST
            )
        if days < MIN_PRUNE_DAYS:
            return Response(
                {"detail": f"days must be at least {MIN_PRUNE_DAYS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cutoff = timezone.now() - timezone.timedelta(days=days)
        deleted, _ = LogEntry.objects.filter(timestamp__lt=cutoff).delete()
        # Deleting log history is itself an administrative act, and the access
        # middleware deliberately does not log this prefix — so the audit row is
        # written here or nowhere.
        logger.warning(
            "log history pruned: %s entries older than %s days deleted by %s",
            deleted,
            days,
            request.user.get_username(),
            extra={
                "category": Category.ADMIN,
                "context": {"days": days, "deleted": deleted, "cutoff": cutoff.isoformat()},
            },
        )
        return Response({"pruned": deleted})
