from rest_framework.routers import DefaultRouter

from apps.logging.views import LogEntryViewSet

router = DefaultRouter()
router.register("logs", LogEntryViewSet, basename="logentry")

urlpatterns = [
    *router.urls,
]
