"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.credentials.urls")),
    path("api/", include("apps.strategies.urls")),
    path("api/", include("apps.execution.urls")),
    path("api/", include("apps.transpiler.urls")),
    path("api/", include("apps.dashboard.urls")),
    path("api/", include("apps.exchange.urls")),
    path("api/", include("apps.paper.urls")),
    path("api/", include("apps.optimizer.urls")),
    path("api/", include("apps.pro.urls")),
    path("api/", include("apps.integrations.urls")),
    path("api/", include("apps.telegram.urls")),
    path("api/", include("apps.copytrading.urls")),
]
