from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(
    "telegram/whitelist", views.AlertWhitelistViewSet, basename="telegram-whitelist"
)

urlpatterns = [
    path(
        "telegram/config/",
        views.TelegramConfigViewSet.as_view({"get": "list", "post": "create"}),
        name="telegram-config",
    ),
    path(
        "telegram/config/test/",
        views.TelegramConfigViewSet.as_view({"post": "test"}),
        name="telegram-config-test",
    ),
] + router.urls
