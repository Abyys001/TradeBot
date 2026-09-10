from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.bots.views import (
    BacktestViewSet,
    BotViewSet,
    InputPresetViewSet,
    StrategyViewSet,
    backtest_coverage,
    backtest_job,
    policy,
    run_backtest,
    start_bot,
    stop_bot,
    strategy_version,
    validate_source,
    version_inputs,
    version_properties,
)

router = DefaultRouter()
router.register("strategies", StrategyViewSet, basename="strategy")
router.register("bots", BotViewSet, basename="bot")
router.register("backtests", BacktestViewSet, basename="backtest")
router.register("presets", InputPresetViewSet, basename="input-preset")

urlpatterns = [
    path("policy/", policy, name="bots-policy"),
    path("validate/", validate_source, name="bots-validate"),
    # Routing endpoints are plain async views with CSRF enforced — the same
    # split apps/trading uses, because DRF 3.15 cannot run an async view and
    # the fan-out deadline cannot afford a worker thread.
    path("backtest/", run_backtest, name="bots-backtest"),
    # The progress bar's two reads. Both cheap: one row, and one indexed count.
    path("backtest/jobs/<int:pk>/", backtest_job, name="bots-backtest-job"),
    path("backtest/coverage/", backtest_coverage, name="bots-backtest-coverage"),
    # The same Properties tab, for a version with no bot behind it — what the
    # backtest form edits before a run.
    path("versions/<int:pk>/properties/", version_properties, name="bots-version-properties"),
    # The author's half of the same dialog, for the same caller: the backtest
    # form draws a version's inputs before there is a bot to hang them on.
    path("versions/<int:pk>/inputs/", version_inputs, name="bots-version-inputs"),
    # One version by id, source included — what the bot detail page reads
    # instead of downloading every strategy on the platform.
    path("versions/<int:pk>/", strategy_version, name="bots-version"),
    path("bots/<int:pk>/start/", start_bot, name="bots-start"),
    path("bots/<int:pk>/stop/", stop_bot, name="bots-stop"),
    *router.urls,
]
