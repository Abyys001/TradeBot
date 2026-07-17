from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views
from .views import (
    AdminFeeConfigView,
    AdminFeeLedgerView,
    AdminInvestorListView,
    AdminPublishStrategyView,
    MasterMarketplaceView,
    MyFeesView,
    MyPositionsView,
    SubscriptionViewSet,
)

router = DefaultRouter()
router.register(r"copytrading/subscriptions", SubscriptionViewSet, basename="subscription")

urlpatterns = [
    # Admin (Hyperliquid)
    path("copytrading/admin/investors/", AdminInvestorListView.as_view()),
    path("copytrading/admin/strategies/<int:pk>/publish/", AdminPublishStrategyView.as_view()),
    path("copytrading/admin/fee-config/", AdminFeeConfigView.as_view()),
    path("copytrading/admin/fee-ledger/", AdminFeeLedgerView.as_view()),
    # Investor (Hyperliquid)
    path("copytrading/marketplace/", MasterMarketplaceView.as_view()),
    path("copytrading/my/positions/", MyPositionsView.as_view()),
    path("copytrading/my/fees/", MyFeesView.as_view()),
    # Investor (Tabdeal)
    path("copytrading/my/summary/", views.MyCopySummaryView.as_view(), name="copy-my-summary"),
    path("copytrading/my/trades/", views.MyCopyTradesView.as_view(), name="copy-my-trades"),
    path("copytrading/my/equity/", views.MyCopyEquityView.as_view(), name="copy-my-equity"),
    # Admin (Tabdeal)
    path("copytrading/fee-config/", views.FeeConfigView.as_view(), name="copy-fee-config"),
    path("copytrading/admin/overview/", views.AdminCopyOverviewView.as_view(), name="copy-admin-overview"),
    path("copytrading/admin/ledger/", views.AdminTabdealFeeLedgerView.as_view(), name="copy-admin-ledger"),
    path("copytrading/admin/strategy-pnl/", views.AdminStrategyPnlView.as_view(), name="copy-admin-strategy-pnl"),
    *router.urls,
]
