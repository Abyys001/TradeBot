from rest_framework.routers import DefaultRouter

from .views import ExecutionLogViewSet, OrderRecordViewSet

router = DefaultRouter()
router.register("orders", OrderRecordViewSet, basename="order")
router.register("logs", ExecutionLogViewSet, basename="log")

urlpatterns = router.urls
