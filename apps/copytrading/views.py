"""Copy-trading REST API: investor summaries, admin fee config/overview,
master marketplace, subscriptions, positions, and ledger management.

Supports both Hyperliquid (IsAdmin/IsInvestor) and Tabdeal (IsAdminRole) endpoints.
"""
from __future__ import annotations

from django.db.models import Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin, IsAdminRole, IsInvestor
from apps.strategies.models import Strategy

from .models import (
    CopySubscription,
    CopyTrade,
    EquitySnapshot,
    FeeConfig,
    FeeLedger,
    FeeLedgerEntry,
    InvestorPosition,
    PlatformFeeConfig,
    Subscription,
)
from .serializers import (
    CopyTradeSerializer,
    EquitySnapshotSerializer,
    FeeConfigSerializer,
    FeeLedgerEntrySerializer,
    FeeLedgerSerializer,
    InvestorPositionSerializer,
    MasterStrategySerializer,
    PlatformFeeConfigSerializer,
    SubscriptionSerializer,
)


# ---- Hyperliquid Admin -------------------------------------------------
class AdminInvestorListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        investors = User.objects.filter(role=User.Role.INVESTOR).order_by("username")
        data = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_trading_enabled": u.is_trading_enabled,
                "subscriptions": u.subscriptions.count(),
            }
            for u in investors
        ]
        return Response(data)


class AdminPublishStrategyView(APIView):
    """Toggle a strategy's master/published flags (admin owns it)."""

    permission_classes = [IsAdmin]

    def post(self, request, pk):
        strategy = Strategy.objects.filter(pk=pk, user=request.user).first()
        if strategy is None:
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        strategy.is_master = bool(request.data.get("is_master", True))
        strategy.published = bool(request.data.get("published", True))
        strategy.save(update_fields=["is_master", "published"])
        return Response(
            {"id": strategy.id, "is_master": strategy.is_master, "published": strategy.published}
        )


class AdminFeeConfigView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(FeeConfigSerializer(FeeConfig.get_solo()).data)

    def patch(self, request):
        cfg = FeeConfig.get_solo()
        ser = FeeConfigSerializer(cfg, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class AdminFeeLedgerView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        ledgers = FeeLedger.objects.select_related(
            "subscription__investor"
        ).order_by("-fee_accrued")
        return Response(FeeLedgerSerializer(ledgers, many=True).data)


# ---- Hyperliquid Investor -----------------------------------------------
class MasterMarketplaceView(APIView):
    """Published master strategies an investor can subscribe to."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        masters = Strategy.objects.filter(is_master=True, published=True).order_by("name")
        return Response(MasterStrategySerializer(masters, many=True).data)


class SubscriptionViewSet(viewsets.ModelViewSet):
    """An investor's own subscriptions."""

    serializer_class = SubscriptionSerializer
    permission_classes = [IsInvestor]

    def get_queryset(self):
        return Subscription.objects.filter(investor=self.request.user).select_related(
            "master_strategy", "credential"
        )

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        sub = self.get_object()
        sub.is_active = False
        sub.save(update_fields=["is_active"])
        return Response({"id": sub.id, "is_active": sub.is_active})

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        sub = self.get_object()
        sub.is_active = True
        sub.save(update_fields=["is_active"])
        return Response({"id": sub.id, "is_active": sub.is_active})


class MyPositionsView(APIView):
    permission_classes = [IsInvestor]

    def get(self, request):
        positions = InvestorPosition.objects.filter(
            subscription__investor=request.user
        ).select_related("subscription")
        return Response(InvestorPositionSerializer(positions, many=True).data)


class MyFeesView(APIView):
    permission_classes = [IsInvestor]

    def get(self, request):
        ledgers = FeeLedger.objects.filter(subscription__investor=request.user)
        return Response(FeeLedgerSerializer(ledgers, many=True).data)


# ---- Tabdeal helpers ----------------------------------------------------
def _investor_subs(user):
    return CopySubscription.objects.filter(credential__user=user)


# ---- Tabdeal Investor ---------------------------------------------------
class MyCopySummaryView(APIView):
    """Investor's own copy-trading performance summary."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        subs = _investor_subs(request.user)
        closed = CopyTrade.objects.filter(subscription__in=subs, status=CopyTrade.Status.CLOSED)
        realized = closed.aggregate(t=Sum("gross_pnl"))["t"] or 0
        fees = FeeLedgerEntry.objects.filter(subscription__in=subs).aggregate(t=Sum("amount"))["t"] or 0
        fees_owed = FeeLedgerEntry.objects.filter(
            subscription__in=subs, status=FeeLedgerEntry.Status.ACCRUED
        ).aggregate(t=Sum("amount"))["t"] or 0
        open_trades = CopyTrade.objects.filter(subscription__in=subs, status=CopyTrade.Status.OPEN).count()
        return Response(
            {
                "subscriptions": subs.filter(is_active=True).count(),
                "realized_pnl": str(realized),
                "net_pnl": str(realized - fees),
                "fees_total": str(fees),
                "fees_owed": str(fees_owed),
                "open_trades": open_trades,
                "closed_trades": closed.count(),
            }
        )


class MyCopyTradesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subs = _investor_subs(request.user)
        trades = (
            CopyTrade.objects.filter(subscription__in=subs)
            .select_related("entry_order", "exit_order")
            .order_by("-opened_at")[:200]
        )
        return Response(CopyTradeSerializer(trades, many=True).data)


class MyCopyEquityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subs = _investor_subs(request.user)
        snaps = (
            EquitySnapshot.objects.filter(subscription__in=subs)
            .order_by("captured_at")[:500]
        )
        return Response(EquitySnapshotSerializer(snaps, many=True).data)


# ---- Tabdeal Admin ------------------------------------------------------
class FeeConfigView(APIView):
    """Admin get/update of the platform performance-fee destination + rate."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        cfg, _ = PlatformFeeConfig.objects.get_or_create(owner=request.user)
        return Response(PlatformFeeConfigSerializer(cfg).data)

    def put(self, request):
        cfg, _ = PlatformFeeConfig.objects.get_or_create(owner=request.user)
        ser = PlatformFeeConfigSerializer(cfg, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class AdminCopyOverviewView(APIView):
    """Admin view of all investor subscriptions, PnL, and accrued fees."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        subs = (
            CopySubscription.objects.select_related("credential__user", "signal")
            .all()
            .order_by("credential__user__username")
        )
        rows = []
        total_realized = 0
        total_fees = 0
        for sub in subs:
            realized = CopyTrade.objects.filter(
                subscription=sub, status=CopyTrade.Status.CLOSED
            ).aggregate(t=Sum("gross_pnl"))["t"] or 0
            fees = FeeLedgerEntry.objects.filter(subscription=sub).aggregate(t=Sum("amount"))["t"] or 0
            open_ct = CopyTrade.objects.filter(subscription=sub, status=CopyTrade.Status.OPEN).count()
            total_realized += realized
            total_fees += fees
            rows.append(
                {
                    "subscription_id": sub.id,
                    "investor": sub.credential.user.username,
                    "signal": sub.signal.name,
                    "is_active": sub.is_active,
                    "trading_enabled": sub.credential.user.is_trading_enabled,
                    "high_water_mark": str(sub.high_water_mark),
                    "realized_pnl": str(realized),
                    "fees_accrued": str(fees),
                    "open_trades": open_ct,
                }
            )
        owed = FeeLedgerEntry.objects.filter(status=FeeLedgerEntry.Status.ACCRUED).aggregate(t=Sum("amount"))["t"] or 0
        return Response(
            {
                "investors": rows,
                "totals": {
                    "investor_count": subs.values("credential__user").distinct().count(),
                    "realized_pnl": str(total_realized),
                    "fees_accrued": str(total_fees),
                    "fees_owed": str(owed),
                },
            }
        )


class AdminStrategyPnlView(APIView):
    """Admin: combined realized PnL per owned strategy (for the bot-cards page)."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        from apps.strategies.models import Strategy

        strategy_ids = Strategy.objects.filter(user=request.user).values_list("id", flat=True)
        rows = (
            CopyTrade.objects.filter(
                subscription__signal__strategy_id__in=strategy_ids,
                status=CopyTrade.Status.CLOSED,
            )
            .values("subscription__signal__strategy_id")
            .annotate(realized_pnl=Sum("gross_pnl"))
        )
        pnl = {
            str(r["subscription__signal__strategy_id"]): str(r["realized_pnl"] or 0)
            for r in rows
        }
        return Response({"pnl": pnl})


class AdminTabdealFeeLedgerView(APIView):
    """Admin list of fee ledger entries; POST marks entries settled."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        entries = (
            FeeLedgerEntry.objects.select_related("subscription__credential__user")
            .order_by("-accrued_at")[:500]
        )
        return Response(FeeLedgerEntrySerializer(entries, many=True).data)

    def post(self, request):
        """Mark a set of ledger entries as settled (off-platform collection done)."""
        from django.utils import timezone

        ids = request.data.get("ids") or []
        updated = FeeLedgerEntry.objects.filter(
            id__in=ids, status=FeeLedgerEntry.Status.ACCRUED
        ).update(status=FeeLedgerEntry.Status.SETTLED, settled_at=timezone.now())
        return Response({"settled": updated})
