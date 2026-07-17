from rest_framework.routers import DefaultRouter

from .views import ExchangeCredentialViewSet

router = DefaultRouter()
router.register("credentials", ExchangeCredentialViewSet, basename="credential")

urlpatterns = router.urls
