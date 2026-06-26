from django.urls import path

from .views import (
    AnalyticsView,
    CandlesView,
    HealthView,
    KillSwitchView,
    LoginView,
    LogoutView,
    MarkersView,
    MeView,
    OverviewView,
    csrf_token_view,
)

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("me/kill-switch/", KillSwitchView.as_view(), name="kill-switch"),
    path("health/", HealthView.as_view(), name="health"),
    path("overview/", OverviewView.as_view(), name="overview"),
    path("analytics/", AnalyticsView.as_view(), name="analytics"),
    path("candles/", CandlesView.as_view(), name="candles"),
    path("markers/", MarkersView.as_view(), name="markers"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/csrf/", csrf_token_view, name="auth-csrf"),
]
