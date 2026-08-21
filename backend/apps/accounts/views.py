from __future__ import annotations

import logging
from decimal import Decimal

from asgiref.sync import async_to_sync
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.accounts import bookkeeping
from apps.accounts.ledger import ROLES, get_split, ledger_snapshot
from apps.accounts.models import (
    AccountStatus,
    ConnectedAccount,
    DetectedMovement,
    DetectionStatus,
    Exchange,
    FundMovement,
    LedgerEvent,
    Notification,
)
from apps.accounts.report import account_report
from apps.accounts.serializers import (
    ConnectedAccountCreateSerializer,
    ConnectedAccountSerializer,
    DetectedMovementSerializer,
    FundMovementEditSerializer,
    FundMovementSerializer,
    LedgerEventSerializer,
    NotificationSerializer,
    ProfitSplitSerializer,
)
from apps.accounts.visibility import _check, accessible
from apps.core.money import D
from apps.exchanges.base import AdapterError, NotSupported, WithdrawalPermissionError
from apps.exchanges.registry import build_adapter

logger = logging.getLogger(__name__)

#: The audit trail only ever grows. The panel asks for the newest page, so the
#: view caps itself rather than shipping the whole history on every request —
#: the same reasoning as ``apps.logging.views``.
EVENT_LIMIT = 200

#: How many already-decided detections the panel gets back. Enough to review
#: an unattended day of classifier verdicts, not the whole archive.
RESOLVED_LIMIT = 25
EVENT_MAX = 1000


def _split_value(row, role: str) -> str:
    """One split percentage as the two-decimal string the column stores."""
    return str(D(getattr(row, role)).quantize(Decimal("0.01")))


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
        """Filter accounts by caller access before every detail route."""
        return accessible(self.request.user, ConnectedAccount.objects.all())

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

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """Everything this one connection has done — the per-account page.

        Detail route, so ``get_queryset`` has already narrowed it to what the
        caller may see: an account they cannot list is a 404 here too, not a
        readable report behind a guessed id.
        """
        return Response(account_report(self.get_object()))

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
        if not _check(self.request.user):
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


class LedgerViewSet(viewsets.ViewSet):
    """Financial management: cash flows, balances, PnL and the profit split."""

    permission_classes = [IsAdminUser]

    def list(self, request):
        accounts = accessible(request.user, ConnectedAccount.objects.all())
        return Response(ledger_snapshot(accounts))

    @action(detail=False, methods=["get", "post"], url_path="movements")
    def movements(self, request):
        if request.method == "POST":
            return self._create_movement(request)
        return self._list_movements(request)

    def _movement_queryset(self, request):
        return FundMovement.objects.filter(
            account__in=accessible(request.user, ConnectedAccount.objects.all())
        ).select_related("account")

    def _list_movements(self, request):
        queryset = self._movement_queryset(request)
        account_id = request.query_params.get("account")
        if account_id:
            visible = accessible(request.user, ConnectedAccount.objects.all())

            get_object_or_404(visible, id=account_id)
            queryset = queryset.filter(account_id=account_id)
        return Response(FundMovementSerializer(queryset, many=True).data)

    def _create_movement(self, request):
        serializer = FundMovementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account = data["account"]
        visible = accessible(request.user, ConnectedAccount.objects.all())
        get_object_or_404(visible, id=account.id)
        movement = bookkeeping.create_movement(
            account=account,
            kind=data["kind"],
            amount=data["amount"],
            actor=request.user.get_username(),
            asset=data.get("asset") or "USDT",
            occurred_at=data.get("occurred_at"),
            note=data.get("note", ""),
        )
        return Response(
            FundMovementSerializer(movement).data, status=status.HTTP_201_CREATED
        )

    @action(
        detail=False,
        methods=["patch", "delete"],
        url_path=r"movements/(?P<movement_pk>[0-9]+)",
    )
    def movement_detail(self, request, movement_pk=None):
        """Edit or delete one recorded cash flow.

        Both are audited rather than silent: a mistyped deposit is exactly the
        thing an operator needs to be able to fix, and exactly the thing the
        next person needs to be able to see was fixed.
        """
        movement = get_object_or_404(self._movement_queryset(request), id=movement_pk)
        actor = request.user.get_username()

        if request.method == "DELETE":
            bookkeeping.delete_movement(movement, actor=actor)
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = FundMovementEditSerializer(movement, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        movement = bookkeeping.edit_movement(
            movement, actor=actor, changes=serializer.validated_data
        )
        return Response(FundMovementSerializer(movement).data)

    # --- auto-detected movements ------------------------------------------

    def _detection_queryset(self, request):
        return DetectedMovement.objects.filter(
            account__in=accessible(request.user, ConnectedAccount.objects.all())
        ).select_related("account")

    @action(detail=False, methods=["get"], url_path="detections")
    def detections(self, request):
        """Balance changes the closed trades do not explain (see ``detection``).

        Defaults to the pending ones — the queue that needs an answer. Pass
        ``?status=all`` for the resolved history alongside them.
        """
        queryset = self._detection_queryset(request)
        wanted = request.query_params.get("status", DetectionStatus.PENDING)
        if wanted == "resolved":
            # The classifier decides most of these by itself, so "what did it
            # decide while I was away" is a real question. Capped, newest first:
            # the panel wants the recent calls it might want to overturn, not
            # the archive.
            queryset = queryset.exclude(status=DetectionStatus.PENDING).order_by(
                "-resolved_at", "-id"
            )[:RESOLVED_LIMIT]
        elif wanted != "all":
            queryset = queryset.filter(status=wanted)
        return Response(DetectedMovementSerializer(queryset, many=True).data)

    @action(
        detail=False,
        methods=["post"],
        url_path=r"detections/(?P<detection_pk>[0-9]+)/accept",
    )
    def detection_accept(self, request, detection_pk=None):
        """Book the proposal, with whatever the operator corrected in it."""
        detection = get_object_or_404(self._detection_queryset(request), id=detection_pk)
        serializer = FundMovementEditSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = serializer.validated_data
        try:
            movement = bookkeeping.accept_detection(
                detection,
                actor=request.user.get_username(),
                kind=changes.get("kind"),
                amount=changes.get("amount"),
                occurred_at=changes.get("occurred_at"),
                note=changes.get("note", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(FundMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=["post"],
        url_path=r"detections/(?P<detection_pk>[0-9]+)/attribute",
    )
    def detection_attribute(self, request, detection_pk=None):
        """Resolve it as the trade's own doing — no cash flow is recorded.

        The other half of the answer the panel offers. Accepting books a deposit
        or withdrawal and moves invested capital; this leaves capital alone so
        the change lands in PnL, which is where a trade result belongs.
        """
        detection = get_object_or_404(self._detection_queryset(request), id=detection_pk)
        try:
            detection = bookkeeping.attribute_detection(
                detection,
                actor=request.user.get_username(),
                note=str(request.data.get("note", ""))[:200],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(DetectedMovementSerializer(detection).data)

    @action(
        detail=False,
        methods=["post"],
        url_path=r"detections/(?P<detection_pk>[0-9]+)/reopen",
    )
    def detection_reopen(self, request, detection_pk=None):
        """Put a resolved row back in the queue, undoing anything it booked."""
        detection = get_object_or_404(self._detection_queryset(request), id=detection_pk)
        detection = bookkeeping.reopen_detection(
            detection,
            actor=request.user.get_username(),
            note=str(request.data.get("note", ""))[:200],
        )
        return Response(DetectedMovementSerializer(detection).data)

    @action(
        detail=False,
        methods=["post"],
        url_path=r"detections/(?P<detection_pk>[0-9]+)/dismiss",
    )
    def detection_dismiss(self, request, detection_pk=None):
        detection = get_object_or_404(self._detection_queryset(request), id=detection_pk)
        try:
            detection = bookkeeping.dismiss_detection(
                detection,
                actor=request.user.get_username(),
                note=str(request.data.get("note", ""))[:200],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(DetectedMovementSerializer(detection).data)

    # --- audit trail -------------------------------------------------------

    @action(detail=False, methods=["get"], url_path="events")
    def events(self, request):
        """Who changed the money record, when, and from what to what.

        Capped rather than paginated, like the system log: this table only
        grows, and the panel wants the newest page, not all of history.
        """
        queryset = LedgerEvent.objects.all()
        if not _check(request.user):
            queryset = queryset.exclude(account__hidden=True)
        account_id = request.query_params.get("account")
        if account_id:
            visible = accessible(request.user, ConnectedAccount.objects.all())
            get_object_or_404(visible, id=account_id)
            queryset = queryset.filter(account_id=account_id)
        try:
            limit = min(int(request.query_params.get("limit", EVENT_LIMIT)), EVENT_MAX)
        except ValueError:
            limit = EVENT_LIMIT
        return Response(LedgerEventSerializer(queryset[:limit], many=True).data)

    @action(detail=False, methods=["get", "post"], url_path="split")
    def split(self, request):
        row = get_split()
        if request.method == "POST":
            # Quantised both sides: the seeded row holds the default as a
            # string, the saved one a Decimal, and "60" vs "60.00" is not a
            # change to anybody's share.
            before = {role: _split_value(row, role) for role in ROLES}
            serializer = ProfitSplitSerializer(row, data=request.data)
            serializer.is_valid(raise_exception=True)
            row = serializer.save(updated_by=request.user.get_username())
            bookkeeping.record_split_change(
                before=before,
                after={role: _split_value(row, role) for role in ROLES},
                actor=request.user.get_username(),
            )
            return Response(serializer.data)
        return Response(ProfitSplitSerializer(row).data)
