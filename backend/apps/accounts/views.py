from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from django.conf import settings
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
from apps.accounts.visibility import can_see_hidden, visible_accounts
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


def after_connect(account: ConnectedAccount) -> None:
    """Start downloading that exchange's pairs and history (see catalogue.py).

    This is the moment the platform first *has* an exchange to ask. The panel's
    pair list and price feed both come from here, so a connect is what turns an
    empty picker into a real one — and the accounts page shows the download's
    progress rather than leaving the admin guessing.
    """
    from django.core.cache import cache

    from apps.exchanges.catalogue import start_sync

    # The feed picks its provider from the connected exchanges; that lookup is
    # cached, and a new account must not wait out the TTL to be quoted from.
    cache.delete("md:connected")
    if not settings.MARKET_DATA.get("AUTO_SYNC"):
        return
    try:
        start_sync()
    except Exception:  # noqa: BLE001 - a download must never fail a connect
        logger.exception("could not start the market data download")


def _record_check(account: ConnectedAccount, *, passed: bool, note: str) -> None:
    """Store the outcome of a §7 check. The timestamp is what ``clean()`` gates on."""
    account.withdrawal_check_passed = passed
    account.last_error = note
    account.withdrawal_checked_at = timezone.now()
    account.save(
        update_fields=["withdrawal_check_passed", "last_error", "withdrawal_checked_at"]
    )


def _refuse(account: ConnectedAccount, exc: Exception) -> None:
    """Spec §7: a key proven withdrawable never routes an order again.

    The row is kept (unlike at connect time, where nothing had been built yet)
    so the admin can see *why* it stopped and fix the key on the exchange.
    """
    account.status = AccountStatus.PAUSED
    account.withdrawal_check_passed = False
    account.last_error = str(exc)
    account.withdrawal_checked_at = timezone.now()
    account.save(
        update_fields=[
            "status",
            "withdrawal_check_passed",
            "last_error",
            "withdrawal_checked_at",
        ]
    )


class ConnectedAccountViewSet(viewsets.ModelViewSet):
    """Spec §6: add, pause, resume, delete — each its own control in the UI."""

    queryset = ConnectedAccount.objects.all()

    def get_queryset(self):
        """One chokepoint for hidden accounts across this whole viewset.

        list, retrieve, balances, pause, resume, verify and destroy all route
        through here, so a hidden account is not merely absent from the list —
        it 404s on every detail route for anyone who is not the viewer. Nothing
        below this line has to remember the rule.
        """
        return visible_accounts(self.request.user, ConnectedAccount.objects.all())

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
            account.withdrawal_checked_at = timezone.now()
            account.save(update_fields=["withdrawal_check_passed", "withdrawal_checked_at"])
            after_connect(account)
            return

        try:
            passed, note = verify_account(account)
        except WithdrawalPermissionError as exc:
            account.delete()
            raise serializers.ValidationError({"api_key": str(exc)}) from exc
        except Exception as exc:  # noqa: BLE001 - surface, do not half-create
            account.delete()
            raise serializers.ValidationError({"detail": f"could not connect: {exc}"}) from exc

        _record_check(account, passed=passed, note=note)
        account.status = AccountStatus.ACTIVE if passed else AccountStatus.PAUSED
        account.full_clean()
        account.save(update_fields=["status"])
        after_connect(account)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Re-run the spec §7 permission check on demand."""
        account = self.get_object()
        try:
            passed, note = verify_account(account)
        except WithdrawalPermissionError as exc:
            _refuse(account, exc)
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        _record_check(account, passed=passed, note=note)
        return Response(ConnectedAccountSerializer(account).data)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        account = self.get_object()
        account.status = AccountStatus.PAUSED
        account.save(update_fields=["status", "updated_at"])
        return Response(ConnectedAccountSerializer(account).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """Spec §6 resume — and spec §7 re-checked on the way back in.

        A key's permissions can change while the account sits paused, and this
        is the moment it starts routing partner capital again, so the check
        runs here too. A key that has *gained* withdrawal rights is refused:
        the account stays paused rather than becoming active.
        """
        account = self.get_object()
        if account.exchange != Exchange.PAPER:
            try:
                passed, note = verify_account(account)
            except WithdrawalPermissionError as exc:
                _refuse(account, exc)
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            # An unprovable check (no permission endpoint) still resumes: five
            # of the eight exchanges publish nothing, and refusing them all
            # would be a stricter rule than §7 states. It resumes flagged.
            _record_check(account, passed=passed, note=note)

        account.status = AccountStatus.ACTIVE
        # Spec §6: a resumed account rejoins from the next trade, never an open
        # one, so its eligibility clock restarts here.
        account.eligible_from = timezone.now()
        account.full_clean()
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
        if not can_see_hidden(self.request.user):
            # A failure notice names its account. ``exclude`` rather than
            # ``filter(account__hidden=False)`` because ``account`` is nullable
            # and a notification with no account belongs to everyone.
            queryset = queryset.exclude(account__hidden=True)
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
