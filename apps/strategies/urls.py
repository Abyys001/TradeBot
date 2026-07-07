from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import StartStrategyView, StopStrategyView, StrategyEnginesView, StrategyPositionsView, StrategyViewSet

router = DefaultRouter()
router.register("strategies", StrategyViewSet, basename="strategy")

urlpatterns = [
    path("strategies/engines/", StrategyEnginesView.as_view(), name="strategy-engines"),
    path("strategies/<int:pk>/start/", StartStrategyView.as_view(), name="strategy-start"),
    path("strategies/<int:pk>/stop/", StopStrategyView.as_view(), name="strategy-stop"),
    path("strategies/<int:pk>/positions/", StrategyPositionsView.as_view(), name="strategy-positions"),
] + router.urls
