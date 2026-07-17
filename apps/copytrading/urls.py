from django.urls import path
from rest_framework.routers import DefaultRouter

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
    # Admin
    path("copytrading/admin/investors/", AdminInvestorListView.as_view()),
    path("copytrading/admin/strategies/<int:pk>/publish/", AdminPublishStrategyView.as_view()),
    path("copytrading/admin/fee-config/", AdminFeeConfigView.as_view()),
    path("copytrading/admin/fee-ledger/", AdminFeeLedgerView.as_view()),
    # Investor
    path("copytrading/marketplace/", MasterMarketplaceView.as_view()),
    path("copytrading/my/positions/", MyPositionsView.as_view()),
    path("copytrading/my/fees/", MyFeesView.as_view()),
    *router.urls,
]
