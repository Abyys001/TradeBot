from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SignumConfig
from .serializers import SignumConfigSerializer


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
