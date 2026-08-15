from django.contrib import admin
from django.urls import include, path

from apps.core.health import health

urlpatterns = [
    path("admin/", admin.site.urls),
    # Unauthenticated on purpose: a container healthcheck carries no session.
    # It reports whether each dependency answered and nothing else — see
    # apps/core/health.py for what it must never say.
    path("api/health/", health, name="health"),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/trading/", include("apps.trading.urls")),
]
