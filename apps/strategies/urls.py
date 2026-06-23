from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import StartStrategyView, StopStrategyView, StrategyViewSet

router = DefaultRouter()
router.register("strategies", StrategyViewSet, basename="strategy")

urlpatterns = [
    path("strategies/<int:pk>/start/", StartStrategyView.as_view(), name="strategy-start"),
    path("strategies/<int:pk>/stop/", StopStrategyView.as_view(), name="strategy-stop"),
] + router.urls
