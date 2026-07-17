import logging

import requests
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AlertWhitelist, TelegramConfig
from .serializers import AlertWhitelistSerializer, TelegramConfigSerializer
from .telegram import TELEGRAM_API_BASE, send_message

logger = logging.getLogger(__name__)


class TelegramConfigViewSet(viewsets.GenericViewSet):
    serializer_class = TelegramConfigSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        config, _ = TelegramConfig.objects.get_or_create(user=self.request.user)
        return config

    def list(self, request):
        config = self.get_object()
        serializer = self.get_serializer(config)
        data = serializer.data
        data["has_bot_token"] = bool(config.bot_token)
        return Response(data)

    def create(self, request):
        config = self.get_object()
        serializer = self.get_serializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        data = serializer.data
        data["has_bot_token"] = bool(config.bot_token)
        return Response(data)

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
        text = "<b>✅ Test Notification</b>\nYour Algo Trader Telegram integration is working correctly."
        sent = 0
        for entry in whitelist:
            if send_message(config.bot_token, entry.chat_id, text):
                sent += 1
        return Response({"sent": sent, "total": whitelist.count()})

    @action(detail=False, methods=["get"])
    def status(self, request):
        config = self.get_object()
        if not config.bot_token:
            return Response(
                {"valid": False, "configured": False, "error": "No bot token set"}
            )
        try:
            resp = requests.get(
                f"{TELEGRAM_API_BASE}{config.bot_token}/getMe", timeout=10
            )
            data = resp.json()
            if data.get("ok"):
                bot = data.get("result", {})
                return Response(
                    {
                        "valid": True,
                        "configured": config.enabled,
                        "username": bot.get("username"),
                        "first_name": bot.get("first_name"),
                    }
                )
            return Response(
                {
                    "valid": False,
                    "configured": config.enabled,
                    "error": data.get("description", "Invalid token"),
                }
            )
        except requests.RequestException as e:
            logger.warning("telegram getMe failed: %s", e)
            return Response(
                {"valid": False, "configured": config.enabled, "error": str(e)}
            )


class AlertWhitelistViewSet(viewsets.ModelViewSet):
    serializer_class = AlertWhitelistSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AlertWhitelist.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
