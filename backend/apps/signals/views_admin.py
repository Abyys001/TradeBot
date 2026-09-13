"""Managing sources from the panel. Staff-only, step-up on the dangerous half.

A signal source is a credential that moves positions, so creating one and
rotating its secret sit behind the same password prompt that guards exchange
credentials and putting a bot live (``apps.security.stepup``). Reading the
list and the event log does not — an operator watching what arrived should
never be asked for a password to do it.
"""

from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.security import stepup
from apps.signals.models import SignalEvent, SignalSource
from apps.signals.serializers import SignalEventSerializer, SignalSourceSerializer


class SignalSourceViewSet(viewsets.ModelViewSet):
    """CRUD over the sources, with the secret shown exactly once."""

    permission_classes = [IsAdminUser]
    serializer_class = SignalSourceSerializer
    queryset = SignalSource.objects.select_related("bot").all()

    def _step_up(self) -> Response | None:
        if stepup.satisfied(self.request):
            return None
        return Response(
            {
                "detail": "confirm your password to change a signal source",
                "code": "step_up_required",
                "action": "signal_source",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    def create(self, request, *args, **kwargs):
        refusal = self._step_up()
        if refusal is not None:
            return refusal
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        secret = SignalSource.new_secret()
        source = SignalSource(
            **serializer.validated_data,
            token=SignalSource.new_token(),
            created_by=getattr(request.user, "username", ""),
        )
        source.set_secret(secret)
        source.save()
        body = self.get_serializer(source).data
        # The one and only time. Named so the panel cannot mistake it for a
        # field it can re-read later.
        body["secret_shown_once"] = secret
        return Response(body, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        refusal = self._step_up()
        if refusal is not None:
            return refusal
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        refusal = self._step_up()
        if refusal is not None:
            return refusal
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        """A new secret. The old one stops working the instant this returns.

        Rotation is the only remediation for a leaked secret, so it is one
        button rather than a delete-and-recreate — recreating would issue a new
        token too, and the sender would need reconfiguring on both halves when
        only one of them was exposed.
        """
        refusal = self._step_up()
        if refusal is not None:
            return refusal
        source = self.get_object()
        secret = SignalSource.new_secret()
        source.set_secret(secret)
        source.save(update_fields=["secret_encrypted", "secret_fingerprint"])
        body = self.get_serializer(source).data
        body["secret_shown_once"] = secret
        return Response(body)


class SignalEventViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """The delivery log, newest first. Read-only by construction."""

    permission_classes = [IsAdminUser]
    serializer_class = SignalEventSerializer

    def get_queryset(self):
        queryset = SignalEvent.objects.select_related("source").all()
        source = self.request.query_params.get("source")
        if source:
            queryset = queryset.filter(source_id=source)
        bot = self.request.query_params.get("bot")
        if bot:
            queryset = queryset.filter(source__bot_id=bot)
        return queryset[:500]
