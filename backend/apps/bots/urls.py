from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.bots.views import (
    BacktestViewSet,
    BotViewSet,
    StrategyViewSet,
    policy,
    run_backtest,
    start_bot,
    stop_bot,
    validate_source,
)

router = DefaultRouter()
router.register("strategies", StrategyViewSet, basename="strategy")
router.register("bots", BotViewSet, basename="bot")
router.register("backtests", BacktestViewSet, basename="backtest")

urlpatterns = [
    path("policy/", policy, name="bots-policy"),
    path("validate/", validate_source, name="bots-validate"),
    # Routing endpoints are plain async views with CSRF enforced — the same
    # split apps/trading uses, because DRF 3.15 cannot run an async view and
    # the fan-out deadline cannot afford a worker thread.
    path("backtest/", run_backtest, name="bots-backtest"),
    path("bots/<int:pk>/start/", start_bot, name="bots-start"),
    path("bots/<int:pk>/stop/", stop_bot, name="bots-stop"),
    *router.urls,
]
