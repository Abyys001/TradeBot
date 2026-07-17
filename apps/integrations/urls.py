from django.urls import path

from .views import SignumConfigView, TelegramConfigView, TelegramTestView

urlpatterns = [
    path("signum/", SignumConfigView.as_view(), name="signum-config"),
    path("telegram/", TelegramConfigView.as_view(), name="telegram-config"),
    path("telegram/test/", TelegramTestView.as_view(), name="telegram-test"),
]
