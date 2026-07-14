from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ExchangeCredential
from .serializers import ExchangeCredentialSerializer
from .verification import verify_credential


class ExchangeCredentialViewSet(viewsets.ModelViewSet):
    """CRUD for the authenticated user's exchange credentials.

    Secrets go in (write-only) and are encrypted at rest; only metadata comes
    back out.
    """

    serializer_class = ExchangeCredentialSerializer

    def get_queryset(self):
        return ExchangeCredential.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Validate the credential against its exchange (Hyperliquid or Tabdeal)."""
        cred = self.get_object()
        ok, detail = verify_credential(cred)
        code = status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST
        return Response({"ok": ok, "detail": detail, "is_active": cred.is_active}, status=code)
