from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ArchiveImportView,
    HistoryCandlesView,
    HistoryCoverageView,
    HistoryDatasetsView,
    HistoryDownloadViewSet,
    HistoryFundingView,
    HistoryGapsView,
    HistoryMarketsView,
    HistoryQualityView,
)

router = DefaultRouter()
router.register("history/downloads", HistoryDownloadViewSet, basename="history-download")

urlpatterns = [
    path("history/datasets/", HistoryDatasetsView.as_view(), name="history-datasets"),
    path("history/candles/", HistoryCandlesView.as_view(), name="history-candles"),
    path("history/funding/", HistoryFundingView.as_view(), name="history-funding"),
    path("history/coverage/", HistoryCoverageView.as_view(), name="history-coverage"),
    path("history/gaps/", HistoryGapsView.as_view(), name="history-gaps"),
    path("history/quality/", HistoryQualityView.as_view(), name="history-quality"),
    path("history/markets/", HistoryMarketsView.as_view(), name="history-markets"),
    path("history/import-archive/", ArchiveImportView.as_view(), name="history-import-archive"),
    path("", include(router.urls)),
]
