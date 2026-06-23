from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BacktestStrategyView, BacktestViewSet, ValidateStrategyView

router = DefaultRouter()
router.register("backtests", BacktestViewSet, basename="backtest")

urlpatterns = [
    path("strategies/<int:pk>/validate/", ValidateStrategyView.as_view(), name="strategy-validate"),
    path("strategies/<int:pk>/backtest/", BacktestStrategyView.as_view(), name="strategy-backtest"),
] + router.urls
