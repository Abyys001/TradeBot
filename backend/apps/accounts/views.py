from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange, Notification
from apps.accounts.serializers import (
    ConnectedAccountCreateSerializer,
    ConnectedAccountSerializer,
    NotificationSerializer,
)
from apps.exchanges.base import AdapterError, NotSupported, WithdrawalPermissionError
from apps.exchanges.registry import build_adapter

logger = logging.getLogger(__name__)


def verify_account(account: ConnectedAccount) -> tuple[bool, str]:
    """Spec §7 gate. Returns (withdrawal_check_passed, note).

    Three outcomes:
      - verified non-withdrawable -> (True, "")
      - proven withdrawable       -> raises, the account is refused outright
      - exchange exposes no key-permission endpoint -> (False, note); the
        account is usable but flagged in the panel, because a silent True here
        would be a lie about a hard security requirement.
    """
    adapter = build_adapter(account)

    async def run() -> None:
        try:
            await adapter.verify_credentials()
        finally:
            await adapter.close()

    try:
        async_to_sync(run)()
    except WithdrawalPermissionError:
        raise
    except NotSupported as exc:
        return False, str(exc)
    except AdapterError as exc:
        return False, str(exc)
    return True, ""


class ConnectedAccountViewSet(viewsets.ModelViewSet):
    """Spec §6: add, pause, resume, delete — each its own control in the UI."""

    queryset = ConnectedAccount.objects.all()

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ConnectedAccountCreateSerializer
        return ConnectedAccountSerializer

    def perform_create(self, serializer) -> None:
        """Verify the credential against the live exchange before it is usable.

        Spec §7: a key with withdrawal rights is refused outright — the account
        row is deleted rather than left half-created.
        """
        account = serializer.save()
        if account.exchange == Exchange.PAPER:
            account.withdrawal_check_passed = True
            account.save(update_fields=["withdrawal_check_passed"])
            return

        try:
            passed, note = verify_account(account)
        except WithdrawalPermissionError as exc:
            account.delete()
            raise serializers.ValidationError({"api_key": str(exc)}) from exc
        except Exception as exc:  # noqa: BLE001 - surface, do not half-create
            account.delete()
            raise serializers.ValidationError({"detail": f"could not connect: {exc}"}) from exc

        account.withdrawal_check_passed = passed
        account.last_error = note
        account.status = AccountStatus.ACTIVE if passed else AccountStatus.PAUSED
        account.save(update_fields=["withdrawal_check_passed", "last_error", "status"])

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Re-run the spec §7 permission check on demand."""
        account = self.get_object()
        try:
            passed, note = verify_account(account)
        except WithdrawalPermissionError as exc:
            account.status = AccountStatus.PAUSED
            account.withdrawal_check_passed = False
            account.last_error = str(exc)
            account.save(update_fields=["status", "withdrawal_check_passed", "last_error"])
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        account.withdrawal_check_passed = passed
        account.last_error = note
        account.save(update_fields=["withdrawal_check_passed", "last_error"])
        return Response(ConnectedAccountSerializer(account).data)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        account = self.get_object()
        account.status = AccountStatus.PAUSED
        account.save(update_fields=["status", "updated_at"])
        return Response(ConnectedAccountSerializer(account).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        account = self.get_object()
        account.status = AccountStatus.ACTIVE
        # Spec §6: a resumed account rejoins from the next trade, never an open
        # one, so its eligibility clock restarts here.
        account.eligible_from = timezone.now()
        account.save(update_fields=["status", "eligible_from", "updated_at"])
        return Response(ConnectedAccountSerializer(account).data)

    @action(detail=False, methods=["get"])
    def balances(self, request):
        """Spec §6: the admin sees every account's balance at all times."""
        accounts = self.get_queryset()
        return Response(
            {
                "accounts": ConnectedAccountSerializer(accounts, many=True).data,
                # Q4: anything not in USDT is surfaced rather than silently traded.
                "non_usdt": [
                    {"id": a.id, "label": a.label, "asset": a.last_balance_asset}
                    for a in accounts
                    if a.last_balance_asset and not a.balance_is_usdt
                ],
            }
        )


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Spec §4: failure notices persist until dismissed by hand."""

    serializer_class = NotificationSerializer

    def get_queryset(self):
        queryset = Notification.objects.all()
        if self.request.query_params.get("active") == "true":
            queryset = queryset.filter(dismissed_at__isnull=True)
        return queryset

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        notification = self.get_object()
        if notification.is_active:
            notification.dismissed_at = timezone.now()
            notification.save(update_fields=["dismissed_at"])
        return Response(NotificationSerializer(notification).data, status=status.HTTP_200_OK)
