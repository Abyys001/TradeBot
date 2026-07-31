from django.urls import path

from .views import (
    ArchiveImportView,
    HistoryCandlesView,
    HistoryCoverageView,
    HistoryDatasetsView,
    HistoryFundingView,
    HistoryGapsView,
    HistoryMarketsView,
    HistoryQualityView,
    MarketDataBackfillView,
    MarketDataCoverageView,
    MarketDataReadinessView,
    MarketDataSymbolsView,
    RecordedSymbolDetailView,
    RecordedSymbolListView,
)

urlpatterns = [
    path("history/datasets/", HistoryDatasetsView.as_view(), name="history-datasets"),
    path("history/candles/", HistoryCandlesView.as_view(), name="history-candles"),
    path("history/funding/", HistoryFundingView.as_view(), name="history-funding"),
    path("history/coverage/", HistoryCoverageView.as_view(), name="history-coverage"),
    path("history/gaps/", HistoryGapsView.as_view(), name="history-gaps"),
    path("history/quality/", HistoryQualityView.as_view(), name="history-quality"),
    path("history/markets/", HistoryMarketsView.as_view(), name="history-markets"),
    path("history/import-archive/", ArchiveImportView.as_view(), name="history-import-archive"),
    path("marketdata/readiness/", MarketDataReadinessView.as_view(), name="marketdata-readiness"),
    path("marketdata/coverage/", MarketDataCoverageView.as_view(), name="marketdata-coverage"),
    path("marketdata/symbols/", MarketDataSymbolsView.as_view(), name="marketdata-symbols"),
    path("marketdata/recorded/", RecordedSymbolListView.as_view(), name="marketdata-recorded"),
    path("marketdata/recorded/<int:pk>/", RecordedSymbolDetailView.as_view(), name="marketdata-recorded-detail"),
    path("marketdata/backfill/", MarketDataBackfillView.as_view(), name="marketdata-backfill"),
]
