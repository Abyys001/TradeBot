from django.urls import path

from .views import (
    JournalView,
    MarketplaceDetailView,
    MarketplaceImportView,
    MarketplaceView,
    ReplayDetailView,
    ReplayStepView,
    ReplayView,
    StrategyVersionDetailView,
    StrategyVersionRestoreView,
    StrategyVersionsView,
)

urlpatterns = [
    path("pro/strategies/<int:strategy_id>/versions/", StrategyVersionsView.as_view(), name="strategy-versions"),
    path(
        "pro/strategies/<int:strategy_id>/versions/<int:version>/",
        StrategyVersionDetailView.as_view(),
        name="strategy-version-detail",
    ),
    path(
        "pro/strategies/<int:strategy_id>/versions/<int:version>/restore/",
        StrategyVersionRestoreView.as_view(),
        name="strategy-version-restore",
    ),
    path("pro/journal/", JournalView.as_view(), name="trade-journal"),
    path("pro/marketplace/", MarketplaceView.as_view(), name="marketplace"),
    path("pro/marketplace/<int:package_id>/", MarketplaceDetailView.as_view(), name="marketplace-detail"),
    path("pro/marketplace/<int:package_id>/import/", MarketplaceImportView.as_view(), name="marketplace-import"),
    path("pro/replay/", ReplayView.as_view(), name="replay"),
    path("pro/replay/<int:session_id>/", ReplayDetailView.as_view(), name="replay-detail"),
    path("pro/replay/<int:session_id>/step/", ReplayStepView.as_view(), name="replay-step"),
]
