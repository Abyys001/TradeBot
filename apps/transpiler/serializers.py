from rest_framework import serializers

from .models import Backtest, BacktestTrade


class BacktestTradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BacktestTrade
        fields = [
            "side", "entry_price", "exit_price", "size", "pnl",
            "gross_pnl", "commission",
            "entry_bar", "exit_bar", "stop_px", "limit_px", "exit_reason",
            "entry_time", "exit_time",
        ]


class BacktestSerializer(serializers.ModelSerializer):
    trades = BacktestTradeSerializer(many=True, read_only=True)

    class Meta:
        model = Backtest
        fields = [
            "id", "strategy", "status", "symbol", "timeframe", "network",
            "initial_balance",
            "range_start", "range_end", "metrics", "error", "created_at",
            "trades",
        ]
        read_only_fields = fields
