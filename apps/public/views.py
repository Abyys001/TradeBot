from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.copytrading.models import CopySubscription, CopyTrade, EquitySnapshot
from apps.strategies.models import Strategy

from .models import Lead
from .serializers import LeadSerializer

DISCLAIMER = "Past performance is not indicative of future results."
PERFORMANCE_CACHE_KEY = "public:performance:v1"
PERFORMANCE_CACHE_TTL = 300
EQUITY_CURVE_DAYS = 90

# Never expose an exact small headcount — band it so a handful of investors
# can't be individually singled out by cross-referencing the aggregate PnL.
_INVESTOR_BANDS = [(0, "0"), (1, "1-9"), (10, "10-25"), (26, "26-50"), (51, "51-100"), (101, "100+")]


def _band_investor_count(n: int) -> str:
    band = _INVESTOR_BANDS[0][1]
    for floor, label in _INVESTOR_BANDS:
        if n >= floor:
            band = label
    return band


def _compute_performance() -> dict:
    active_subs = CopySubscription.objects.filter(is_active=True)
    closed_trades = CopyTrade.objects.filter(
        subscription__in=active_subs, status=CopyTrade.Status.CLOSED
    )

    totals = closed_trades.aggregate(
        gross_pnl_sum=Sum("gross_pnl"),
        platform_share=Sum("platform_share_amount"),
        total=Count("id"),
        wins=Count("id", filter=Q(gross_pnl__gt=0)),
    )
    gross_pnl = totals["gross_pnl_sum"] or Decimal("0")
    platform_share = totals["platform_share"] or Decimal("0")
    total_trades = totals["total"] or 0
    wins = totals["wins"] or 0
    net_pnl = gross_pnl - platform_share
    win_rate = round(wins / total_trades, 4) if total_trades else 0.0

    investor_count = active_subs.values("credential__user").distinct().count()
    active_strategies = Strategy.objects.filter(status=Strategy.Status.ACTIVE).count()

    since = timezone.now() - timedelta(days=EQUITY_CURVE_DAYS)
    curve = (
        EquitySnapshot.objects.filter(subscription__in=active_subs, captured_at__gte=since)
        .annotate(day=TruncDate("captured_at"))
        .values("day")
        .annotate(equity=Sum("equity"))
        .order_by("day")
    )
    equity_curve = [
        {"date": row["day"].isoformat(), "equity": round(float(row["equity"] or 0), 2)}
        for row in curve
    ]

    return {
        "as_of": timezone.now().isoformat(),
        "since_days": EQUITY_CURVE_DAYS,
        "headline": {
            "net_realized_pnl": str(round(net_pnl, 2)),
            "win_rate": win_rate,
            "total_closed_trades": total_trades,
            "active_strategies": active_strategies,
            "active_investors_band": _band_investor_count(investor_count),
        },
        "equity_curve": equity_curve,
        "disclaimer": DISCLAIMER,
    }


class PublicPerformanceView(APIView):
    """Public, read-only, sanitized platform-performance snapshot for the marketing site.

    Deliberately never exposes per-investor or per-subscription rows — only
    platform-wide totals and a banded investor count, to avoid re-identifying
    individual investors' account sizes via the aggregate numbers.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_performance"

    def get(self, request):
        payload = cache.get(PERFORMANCE_CACHE_KEY)
        if payload is None:
            payload = _compute_performance()
            cache.set(PERFORMANCE_CACHE_KEY, payload, PERFORMANCE_CACHE_TTL)
        # Belt-and-suspenders: guarantee the disclaimer ships even if a stale
        # cached payload predates it.
        payload = {**payload, "disclaimer": DISCLAIMER}
        return Response(payload)


class LeadCreateView(APIView):
    """Public 'Request Access' lead capture from the landing page."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "lead_submit"

    def post(self, request):
        serializer = LeadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        honeypot = data.pop("website", "")

        if honeypot:
            # Silently drop bot submissions without tipping them off.
            return Response({"status": "received"}, status=201)

        email = data.get("email", "")
        dedup_key = f"lead:throttle:{email}"
        if email and not cache.add(dedup_key, 1, timeout=600):
            return Response({"status": "received"}, status=201)

        Lead.objects.create(**data)
        return Response({"status": "received"}, status=201)
