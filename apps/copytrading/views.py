"""Copy-trading REST API: investor summaries + admin fee config/overview."""
from __future__ import annotations

from django.db.models import Count, Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole

from .models import (
    CopySubscription,
    CopyTrade,
    EquitySnapshot,
    FeeLedgerEntry,
    PlatformFeeConfig,
)
from .serializers import (
    CopyTradeSerializer,
    EquitySnapshotSerializer,
    FeeLedgerEntrySerializer,
    PlatformFeeConfigSerializer,
)


def _investor_subs(user):
    return CopySubscription.objects.filter(credential__user=user)


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


class AdminFeeLedgerView(APIView):
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
