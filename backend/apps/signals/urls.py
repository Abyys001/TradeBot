from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.signals.views import receive
from apps.signals.views_admin import SignalEventViewSet, SignalSourceViewSet

router = DefaultRouter()
router.register("sources", SignalSourceViewSet, basename="signal-source")
router.register("events", SignalEventViewSet, basename="signal-event")

urlpatterns = [
    # The inbound endpoint. Unauthenticated by necessity and CSRF-exempt —
    # every other control is inside the request itself (apps/signals/auth.py).
    # A plain async view rather than DRF for the same reason the trading
    # routing endpoints are: it awaits a fan-out, and DRF 3.15 cannot.
    path("hooks/<str:token>/", receive, name="signals-receive"),
    *router.urls,
]
