from django.urls import path

from apps.trading.consumers import TradingConsumer

websocket_urlpatterns = [
    path("ws/trading/", TradingConsumer.as_asgi()),
]
