from rest_framework import serializers

from .models import Strategy, StrategyState


def sync_primary_from_live_config(validated_data: dict) -> dict:
    """Sync legacy symbol/timeframe from live_config primary selections."""
    live_config = validated_data.get("live_config")
    if not live_config:
        return validated_data
    symbols = live_config.get("symbols") or []
    timeframes = live_config.get("timeframes") or []
    if symbols:
        validated_data["symbol"] = symbols[0]
    if timeframes:
        validated_data["timeframe"] = timeframes[0]
    return validated_data


class StrategyStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StrategyState
        fields = [
            "position", "last_signal", "pnl",
            "live_started_at", "last_bar_ts", "live_error",
            "updated_at",
        ]


class StrategySerializer(serializers.ModelSerializer):
    state = StrategyStateSerializer(read_only=True)

    class Meta:
        model = Strategy
        fields = [
            "id",
            "credential",
            "name",
            "type",
            "symbol",
            "market_type",
            "params",
            "status",
            "source",
            "validation_status",
            "validation_error",
            "timeframe",
            "warmup_bars",
            "live_config",
            "created_at",
            "updated_at",
            "state",
        ]
        read_only_fields = [
            "created_at", "updated_at", "validation_status", "validation_error",
        ]

    def validate_credential(self, credential):
        if credential is None:
            return None
        # A user may only attach their own credential.
        if credential.user_id != self.context["request"].user.id:
            raise serializers.ValidationError("Credential does not belong to you.")
        return credential

    def create(self, validated_data):
        validated_data = sync_primary_from_live_config(validated_data)
        return Strategy.objects.create(
            user=self.context["request"].user, **validated_data
        )

    def update(self, instance, validated_data):
        validated_data = sync_primary_from_live_config(validated_data)
        return super().update(instance, validated_data)
