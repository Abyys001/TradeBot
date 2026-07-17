from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SignumConfig, TelegramConfig
from .serializers import SignumConfigSerializer, TelegramConfigSerializer


class SignumConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cfg = SignumConfig.objects.filter(user=request.user).first()
        if cfg is None:
            return Response(
                {
                    "enabled": False,
                    "order_size_default": "80%",
                    "use_settings_bot_id": True,
                    "has_bot_id": False,
                    "has_webhook_url": False,
                }
            )
        return Response(SignumConfigSerializer(cfg).data)

    def post(self, request):
        cfg = SignumConfig.objects.filter(user=request.user).first()
        ser = SignumConfigSerializer(
            instance=cfg,
            data=request.data,
            partial=cfg is not None,
            context={"request": request},
        )
        ser.is_valid(raise_exception=True)
        if cfg is None:
            cfg = ser.save()
        else:
            cfg = ser.save()
        return Response(SignumConfigSerializer(cfg).data)

    def patch(self, request):
        cfg = SignumConfig.objects.filter(user=request.user).first()
        if cfg is None:
            return Response({"error": "not configured"}, status=404)
        ser = SignumConfigSerializer(cfg, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        cfg = ser.save()
        return Response(SignumConfigSerializer(cfg).data)


class TelegramConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cfg = TelegramConfig.objects.filter(user=request.user).first()
        if cfg is None:
            return Response(
                {"enabled": False, "chat_id": "", "events": [], "has_bot_token": False}
            )
        return Response(TelegramConfigSerializer(cfg).data)

    def post(self, request):
        cfg = TelegramConfig.objects.filter(user=request.user).first()
        ser = TelegramConfigSerializer(
            instance=cfg,
            data=request.data,
            partial=cfg is not None,
            context={"request": request},
        )
        ser.is_valid(raise_exception=True)
        cfg = ser.save()
        return Response(TelegramConfigSerializer(cfg).data)

    def patch(self, request):
        cfg = TelegramConfig.objects.filter(user=request.user).first()
        if cfg is None:
            return Response({"error": "not configured"}, status=404)
        ser = TelegramConfigSerializer(
            cfg, data=request.data, partial=True, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        cfg = ser.save()
        return Response(TelegramConfigSerializer(cfg).data)


class TelegramTestView(APIView):
    """Send a test message to confirm the bot token + chat id work."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .telegram import send_telegram_message

        text = request.data.get("text") or "✅ TradeBot Telegram test message."
        result = send_telegram_message(request.user, text, force=True)
        code = 200 if result.get("ok") else 400
        return Response(result, status=code)
