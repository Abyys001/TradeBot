from __future__ import annotations

from rest_framework import serializers

from apps.trading.models import Trade, TradeLeg


class TradeLegSerializer(serializers.ModelSerializer):
    account_label = serializers.CharField(source="account.label", read_only=True)
    exchange = serializers.CharField(source="account.exchange", read_only=True)

    class Meta:
        model = TradeLeg
        fields = [
            "id",
            "account",
            "account_label",
            "exchange",
            "ok",
            "error",
            "error_code",
            "dispatch_ms",
            "qty",
            "entry_price",
            "exit_price",
            "margin",
            "stop_loss",
            "take_profit",
            "sltp_attached",
            "sltp_verified",
            "pnl",
            "opened_at",
            "closed_at",
        ]
        read_only_fields = fields


class TradeSerializer(serializers.ModelSerializer):
    legs = TradeLegSerializer(many=True, read_only=True)
    # Null on the manual path — unchanged. Present here so the chart can label
    # this trade's entry/exit markers with the bot's own name instead of "you",
    # through the exact same marker mechanism a manual trade uses (bots.md §7).
    bot_name = serializers.CharField(source="bot_run.bot.name", read_only=True, default=None)

    class Meta:
        model = Trade
        fields = [
            "id",
            "symbol",
            "side",
            "market",
            "leverage",
            "sl_pct",
            "tp_pct",
            "sltp_basis",
            "admin_entry_price",
            "status",
            "opened_at",
            "closed_at",
            "fanout_ms",
            "bot_run",
            "bot_name",
            "legs",
        ]
        read_only_fields = fields
