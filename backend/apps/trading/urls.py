from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.trading.market_views import (
    candles,
    market_sync,
    positions,
    symbols,
    ticker,
    tickers,
)
from apps.trading.order_views import (
    amend_position,
    close_position,
    open_position,
    refresh_balances_view,
)
from apps.trading.views import TradeViewSet, exchanges, policy, risk_preview, stop_all

router = DefaultRouter()
router.register("trades", TradeViewSet, basename="trade")

urlpatterns = [
    path("risk-preview/", risk_preview, name="risk-preview"),
    path("policy/", policy, name="policy"),
    path("stop-all/", stop_all, name="stop-all"),
    path("exchanges/", exchanges, name="exchanges"),
    path("orders/open/", open_position, name="order-open"),
    path("orders/<int:pk>/amend/", amend_position, name="order-amend"),
    path("orders/<int:pk>/close/", close_position, name="order-close"),
    path("balances/refresh/", refresh_balances_view, name="balances-refresh"),
    # Market data (spec §3): public prices, no credentials involved.
    path("market/candles/", candles, name="market-candles"),
    path("market/ticker/", ticker, name="market-ticker"),
    path("market/tickers/", tickers, name="market-tickers"),
    path("market/symbols/", symbols, name="market-symbols"),
    path("market/sync/", market_sync, name="market-sync"),
    path("positions/", positions, name="positions"),
    *router.urls,
]
