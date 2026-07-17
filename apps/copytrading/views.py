"""Copy-trading REST API.

Admin endpoints (``IsAdmin``): manage investors, publish/unpublish master
strategies, configure fees, read the fee ledger. Investor endpoints
(``IsInvestor``): browse published masters, subscribe/unsubscribe, and view
their own mirrored positions and fees owed.
"""
from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin, IsInvestor
from apps.strategies.models import Strategy

from .models import FeeConfig, FeeLedger, InvestorPosition, Subscription
from .serializers import (
    FeeConfigSerializer,
    FeeLedgerSerializer,
    InvestorPositionSerializer,
    MasterStrategySerializer,
    SubscriptionSerializer,
)


# ---- Admin -------------------------------------------------------------
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


# ---- Investor ----------------------------------------------------------
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
