from rest_framework import serializers

from .models import ExchangeCredential


class ExchangeCredentialSerializer(serializers.ModelSerializer):
    """Agent key is write-only; never returned in API responses."""

    agent_private_key = serializers.CharField(
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
            "network",
            "permissions",
            "is_active",
            "last_verified_at",
            "created_at",
            "agent_private_key",
        ]
        read_only_fields = [
            "is_active",
            "last_verified_at",
            "created_at",
            "permissions",
            "agent_address",
        ]

    def create(self, validated_data):
        key = validated_data.pop("agent_private_key", None)
        if not key:
            raise serializers.ValidationError(
                {"agent_private_key": "This field is required."}
            )
        cred = ExchangeCredential(user=self.context["request"].user, **validated_data)
        cred.set_agent_key(key)
        cred.save()
        return cred

    def update(self, instance, validated_data):
        key = validated_data.pop("agent_private_key", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if key:
            instance.set_agent_key(key)
        instance.save()
        return instance
