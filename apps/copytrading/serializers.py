from rest_framework import serializers

from .models import CopyTrade, EquitySnapshot, FeeLedgerEntry, PlatformFeeConfig


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
