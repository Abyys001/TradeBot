from rest_framework import serializers

from .models import Exchange, ExchangeCredential


class ExchangeCredentialSerializer(serializers.ModelSerializer):
    """Secrets are write-only; never returned in API responses.

    Required fields depend on ``exchange``:
      - Hyperliquid: ``agent_private_key`` + ``wallet_address``
      - Tabdeal:     ``api_key`` + ``api_secret``
    """

    agent_private_key = serializers.CharField(
        write_only=True, required=False, trim_whitespace=False
    )
    api_secret = serializers.CharField(
        write_only=True, required=False, trim_whitespace=False
    )

    class Meta:
        model = ExchangeCredential
        fields = [
            "id",
            "exchange",
            "label",
            "wallet_address",
            "agent_address",
            "api_key",
            "network",
            "permissions",
            "is_active",
            "last_verified_at",
            "created_at",
            "agent_private_key",
            "api_secret",
        ]
        read_only_fields = [
            "is_active",
            "last_verified_at",
            "created_at",
            "permissions",
            "agent_address",
        ]

    def _validate_for_exchange(self, exchange, *, agent_key, api_key, api_secret, partial):
        """Enforce the per-exchange required secret set (skip on partial update)."""
        if partial:
            return
        if exchange == Exchange.HYPERLIQUID:
            if not agent_key:
                raise serializers.ValidationError(
                    {"agent_private_key": "Required for Hyperliquid."}
                )
        elif exchange == Exchange.TABDEAL:
            errors = {}
            if not api_key:
                errors["api_key"] = "Required for Tabdeal."
            if not api_secret:
                errors["api_secret"] = "Required for Tabdeal."
            if errors:
                raise serializers.ValidationError(errors)

    def create(self, validated_data):
        agent_key = validated_data.pop("agent_private_key", None)
        api_secret = validated_data.pop("api_secret", None)
        exchange = validated_data.get("exchange", Exchange.HYPERLIQUID)
        self._validate_for_exchange(
            exchange,
            agent_key=agent_key,
            api_key=validated_data.get("api_key"),
            api_secret=api_secret,
            partial=False,
        )
        cred = ExchangeCredential(user=self.context["request"].user, **validated_data)
        if agent_key:
            cred.set_agent_key(agent_key)
        if api_secret:
            cred.set_api_secret(api_secret)
        cred.save()
        return cred

    def update(self, instance, validated_data):
        agent_key = validated_data.pop("agent_private_key", None)
        api_secret = validated_data.pop("api_secret", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if agent_key:
            instance.set_agent_key(agent_key)
        if api_secret:
            instance.set_api_secret(api_secret)
        instance.save()
        return instance
