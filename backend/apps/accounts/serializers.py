from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import ConnectedAccount, Notification


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
            "wallet_address",
            "credential_expires_at",
            "api_key",
            "api_secret",
            "api_passphrase",
        ]

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
