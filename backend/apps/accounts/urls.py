from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.accounts.auth_views import csrf, login_view, logout_view, me
from apps.accounts.views import ConnectedAccountViewSet, LedgerViewSet, NotificationViewSet

router = DefaultRouter()
router.register("accounts", ConnectedAccountViewSet, basename="account")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("ledger", LedgerViewSet, basename="ledger")

urlpatterns = [
    path("auth/csrf/", csrf, name="csrf"),
    path("auth/login/", login_view, name="login"),
    path("auth/logout/", logout_view, name="logout"),
    path("auth/me/", me, name="me"),
    *router.urls,
]
