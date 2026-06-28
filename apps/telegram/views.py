from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AlertWhitelist, TelegramConfig
from .serializers import AlertWhitelistSerializer, TelegramConfigSerializer
from .telegram import send_message


class TelegramConfigViewSet(viewsets.GenericViewSet):
    serializer_class = TelegramConfigSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        config, _ = TelegramConfig.objects.get_or_create(user=self.request.user)
        return config

    def list(self, request):
        config = self.get_object()
        serializer = self.get_serializer(config)
        return Response(serializer.data)

    def create(self, request):
        config = self.get_object()
        serializer = self.get_serializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def test(self, request):
        config = self.get_object()
        if not config.enabled or not config.bot_token:
            return Response(
                {"error": "Telegram not configured"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        whitelist = AlertWhitelist.objects.filter(user=request.user, enabled=True)
        if not whitelist.exists():
            return Response(
                {"error": "No whitelisted chats"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        text = "<b>✅ Test Notification</b>\nYour TradeBot Telegram integration is working correctly."
        sent = 0
        for entry in whitelist:
            if send_message(config.bot_token, entry.chat_id, text):
                sent += 1
        return Response({"sent": sent, "total": whitelist.count()})


class AlertWhitelistViewSet(viewsets.ModelViewSet):
    serializer_class = AlertWhitelistSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AlertWhitelist.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
