from rest_framework import serializers

from .models import Exchange, ExchangeCredential


class ExchangeCredentialSerializer(serializers.ModelSerializer):
    """Secrets are write-only; never returned in API responses."""

    agent_private_key = serializers.CharField(
        write_only=True, required=False, trim_whitespace=False
    )
    api_key = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    api_secret = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = ExchangeCredential
        fields = [
            "id",
            "exchange",
            "label",
            "wallet_address",
            "agent_address",
            "network",
            "permissions",
            "is_active",
            "last_verified_at",
            "created_at",
            "agent_private_key",
            "api_key",
            "api_secret",
        ]
        read_only_fields = [
            "is_active",
            "last_verified_at",
            "created_at",
            "permissions",
            "agent_address",
        ]

    def create(self, validated_data):
        agent_key = validated_data.pop("agent_private_key", None)
        api_key = validated_data.pop("api_key", None)
        api_secret = validated_data.pop("api_secret", None)
        cred = ExchangeCredential(user=self.context["request"].user, **validated_data)

        if validated_data.get("exchange") == Exchange.TABDEAL:
            if not api_key or not api_secret:
                raise serializers.ValidationError(
                    {"api_key": "api_key and api_secret are required for Tabdeal credentials."}
                )
            cred.set_api_credentials(api_key, api_secret)
        else:
            if not agent_key:
                raise serializers.ValidationError(
                    {"agent_private_key": "This field is required."}
                )
            cred.set_agent_key(agent_key)

        cred.save()
        return cred

    def update(self, instance, validated_data):
        agent_key = validated_data.pop("agent_private_key", None)
        api_key = validated_data.pop("api_key", None)
        api_secret = validated_data.pop("api_secret", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if agent_key:
            instance.set_agent_key(agent_key)
        if api_key and api_secret:
            instance.set_api_credentials(api_key, api_secret)
        instance.save()
        return instance
