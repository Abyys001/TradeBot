"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.credentials.urls")),
    path("api/", include("apps.strategies.urls")),
    path("api/", include("apps.execution.urls")),
    path("api/", include("apps.transpiler.urls")),
    path("api/", include("apps.dashboard.urls")),
]
