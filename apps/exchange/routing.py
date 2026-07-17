from django.urls import re_path

from .consumers import DashboardConsumer, ExchangeConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/exchange/(?P<credential_id>\d+)/$",
        ExchangeConsumer.as_asgi(),
    ),
    re_path(r"^ws/dashboard/$", DashboardConsumer.as_asgi()),
]
