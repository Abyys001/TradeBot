from rest_framework import serializers

from apps.credentials.models import ExchangeCredential

from .models import (
    CopyTrade,
    EquitySnapshot,
    FeeConfig,
    FeeLedger,
    FeeLedgerEntry,
    InvestorPosition,
    PlatformFeeConfig,
    Subscription,
)


class MasterStrategySerializer(serializers.Serializer):
    """Read-only view of a published master strategy for the marketplace."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    symbol = serializers.CharField()
    market_type = serializers.CharField()
    timeframe = serializers.CharField()
    status = serializers.CharField()


class SubscriptionSerializer(serializers.ModelSerializer):
    master_name = serializers.CharField(source="master_strategy.name", read_only=True)
    master_symbol = serializers.CharField(source="master_strategy.symbol", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "master_strategy",
            "master_name",
            "master_symbol",
            "credential",
            "sizing_mode",
            "risk_pct",
            "fixed_notional",
            "leverage",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_master_strategy(self, value):
        if not (value.is_master and value.published):
            raise serializers.ValidationError("Strategy is not an available master.")
        return value

    def validate_credential(self, value):
        # Investors may only bind their own credentials.
        if value.user_id != self.context["request"].user.id:
            raise serializers.ValidationError("Credential does not belong to you.")
        return value


class InvestorPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvestorPosition
        fields = ["id", "subscription", "coin", "size", "entry_price", "opened_at"]


class FeeLedgerSerializer(serializers.ModelSerializer):
    investor = serializers.CharField(source="subscription.investor.username", read_only=True)

    class Meta:
        model = FeeLedger
        fields = [
            "id",
            "subscription",
            "investor",
            "realized_pnl",
            "high_water_mark",
            "fee_accrued",
            "fee_rate",
            "updated_at",
        ]


class FeeConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeConfig
        fields = ["fee_rate", "updated_at"]
        read_only_fields = ["updated_at"]


class PlatformFeeConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformFeeConfig
        fields = ("share_pct", "destination_exchange", "destination_account", "updated_at")
        read_only_fields = ("updated_at",)


class CopyTradeSerializer(serializers.ModelSerializer):
    pair = serializers.CharField(source="entry_order.pair", read_only=True)
    side = serializers.CharField(source="entry_order.side", read_only=True)
    entry_price = serializers.DecimalField(source="entry_order.avg_fill_price", max_digits=24, decimal_places=8, read_only=True)
    exit_price = serializers.DecimalField(source="exit_order.avg_fill_price", max_digits=24, decimal_places=8, read_only=True)

    class Meta:
        model = CopyTrade
        fields = (
            "id", "pair", "side", "entry_price", "exit_price", "status",
            "gross_pnl", "platform_share_amount", "opened_at", "closed_at",
        )


class EquitySnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = EquitySnapshot
        fields = ("balance", "equity", "captured_at")


class FeeLedgerEntrySerializer(serializers.ModelSerializer):
    investor = serializers.CharField(source="subscription.credential.user.username", read_only=True)

    class Meta:
        model = FeeLedgerEntry
        fields = ("id", "investor", "amount", "share_pct", "status", "accrued_at", "settled_at")
