from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import (
    ConnectedAccount,
    DetectedMovement,
    FundMovement,
    LedgerEvent,
    Notification,
    ProfitSplit,
)
from apps.accounts.visibility import _check


class ConnectedAccountSerializer(serializers.ModelSerializer):
    """Read serializer. Deliberately exposes no credential field of any kind."""

    exchange_label = serializers.CharField(source="get_exchange_display", read_only=True)
    balance_is_usdt = serializers.BooleanField(read_only=True)
    is_tradeable = serializers.BooleanField(read_only=True)

    class Meta:
        model = ConnectedAccount
        fields = [
            "id",
            "label",
            "exchange",
            "exchange_label",
            "status",
            "testnet",
            "hidden",
            "wallet_address",
            "credential_expires_at",
            "key_fingerprint",
            "withdrawal_check_passed",
            # When the spec §7 check last ran. Distinct from the verdict: five
            # exchanges publish no permission endpoint, so "checked but
            # unprovable" is a real state and the panel should be able to say
            # *when* rather than only *whether*.
            "withdrawal_checked_at",
            "last_balance",
            "last_balance_asset",
            "last_balance_at",
            "balance_is_usdt",
            "is_tradeable",
            "last_error",
            "created_at",
        ]
        read_only_fields = fields


class ConnectedAccountCreateSerializer(serializers.ModelSerializer):
    """Write serializer. Credentials come in, are encrypted, and never come back."""

    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_passphrase = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ConnectedAccount
        fields = [
            "id",
            "label",
            "exchange",
            "testnet",
            "hidden",
            "wallet_address",
            "credential_expires_at",
            "api_key",
            "api_secret",
            "api_passphrase",
        ]

    def validate_hidden(self, value: bool) -> bool:
        """Only the one viewer may mark an account hidden, or unmark one.

        Both directions are gated. Setting it is obvious; clearing it matters
        just as much, because an account that could be un-hidden by anyone else
        is an account anyone else can reveal. In practice a non-viewer can never
        reach a hidden row at all — ``get_queryset`` filters it out and
        ``get_object`` 404s — so this is the second lock on the same door,
        covering the create path where there is no object to filter yet.
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if _check(user):
            return value
        if value or (self.instance is not None and self.instance.hidden):
            raise serializers.ValidationError(
                "You are not allowed to change this account's visibility."
            )
        return value

    def create(self, validated_data: dict) -> ConnectedAccount:
        credentials = {
            "api_key": validated_data.pop("api_key", ""),
            "api_secret": validated_data.pop("api_secret", ""),
            "passphrase": validated_data.pop("api_passphrase", ""),
        }
        account = ConnectedAccount(**validated_data)
        account.set_credentials(**credentials)
        # Spec §7: the withdrawal check runs against the live exchange in
        # ConnectedAccountViewSet.perform_create via the adapter, and only then
        # is withdrawal_check_passed set. Paper accounts skip it.
        account.save()
        return account


class NotificationSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "account", "message", "code", "created_at", "dismissed_at", "is_active"]
        read_only_fields = fields


class FundMovementSerializer(serializers.ModelSerializer):
    """Read + create. Amount is always positive; the direction lives in ``kind``."""

    account_label = serializers.CharField(source="account.label", read_only=True)

    class Meta:
        model = FundMovement
        fields = [
            "id",
            "account",
            "account_label",
            "kind",
            "amount",
            "asset",
            "occurred_at",
            "note",
            "source",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
        ]
        read_only_fields = [
            "id",
            "account_label",
            "source",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
        ]

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("amount must be positive")
        return value


class FundMovementEditSerializer(serializers.ModelSerializer):
    """The edit surface. The account is fixed — see ``bookkeeping.EDITABLE``."""

    class Meta:
        model = FundMovement
        fields = ["kind", "amount", "asset", "occurred_at", "note"]
        extra_kwargs = {field: {"required": False} for field in fields}

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("amount must be positive")
        return value


class DetectedMovementSerializer(serializers.ModelSerializer):
    """A proposal, with the whole subtraction shown so it can be checked.

    ``delta = trade_pnl + manual_net + unexplained`` — the operator can see
    which part of the balance change the platform could account for and which
    part it is asking about.
    """

    account_label = serializers.CharField(source="account.label", read_only=True)
    exchange = serializers.CharField(source="account.exchange", read_only=True)
    exchange_label = serializers.CharField(
        source="account.get_exchange_display", read_only=True
    )
    amount = serializers.DecimalField(max_digits=24, decimal_places=8, read_only=True)

    class Meta:
        model = DetectedMovement
        fields = [
            "id",
            "account",
            "account_label",
            "exchange",
            "exchange_label",
            "previous_equity",
            "current_equity",
            "delta",
            "trade_pnl",
            "manual_net",
            "unexplained",
            "amount",
            "suggested_kind",
            "asset",
            "window_start",
            "observed_at",
            "status",
            "resolved_at",
            "resolved_by",
            "movement",
        ]
        read_only_fields = fields


class LedgerEventSerializer(serializers.ModelSerializer):
    """The audit trail, read-only. ``actor`` is blank when the platform acted."""

    class Meta:
        model = LedgerEvent
        fields = [
            "id",
            "actor",
            "action",
            "account",
            "account_label",
            "movement_id",
            "detection_id",
            "kind",
            "amount",
            "before",
            "after",
            "note",
            "created_at",
        ]
        read_only_fields = fields


class ProfitSplitSerializer(serializers.ModelSerializer):
    """Read + write. The three percentages must sum to 100."""

    class Meta:
        model = ProfitSplit
        fields = ["investor", "trader", "programmer", "updated_at", "updated_by"]
        read_only_fields = ["updated_at", "updated_by"]

    def validate(self, attrs: dict) -> dict:
        investor = attrs.get("investor", getattr(self.instance, "investor", None))
        trader = attrs.get("trader", getattr(self.instance, "trader", None))
        programmer = attrs.get("programmer", getattr(self.instance, "programmer", None))
        if None in (investor, trader, programmer):
            return attrs
        for name, value in (("investor", investor), ("trader", trader), ("programmer", programmer)):
            if value < 0 or value > 100:
                raise serializers.ValidationError({name: "must be between 0 and 100"})
        if investor + trader + programmer != 100:
            raise serializers.ValidationError(
                {"investor": "percentages must sum to 100"}
            )
        return attrs
