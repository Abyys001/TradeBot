from django.urls import path

from .views import SignumConfigView

urlpatterns = [
    path("signum/", SignumConfigView.as_view(), name="signum-config"),
]
