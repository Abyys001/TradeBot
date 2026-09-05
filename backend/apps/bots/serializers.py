"""Read shapes for ``/api/bots/``.

Nothing here carries a credential and nothing carries a per-account number that
has not been filtered — Q27 puts the filtering on every bot *read* surface, and
``views.py`` applies it. A serializer that quietly widened one is the most
likely way that invariant gets broken, so the per-account fields live in exactly
one place: ``BotActionSerializer.legs``.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.bots.models import (
    BacktestRun,
    Bot,
    BotAction,
    BotBar,
    BotRun,
    Strategy,
    StrategyVersion,
)


class StrategyVersionSerializer(serializers.ModelSerializer):
    used_by = serializers.SerializerMethodField()

    class Meta:
        model = StrategyVersion
        fields = (
            "id",
            "version",
            "source",
            "parsed_ok",
            "validation_errors",
            "validation_warnings",
            "inputs_schema",
            "properties",
            "property_notes",
            "created_at",
            "created_by",
            "used_by",
        )

    def get_used_by(self, obj) -> list:
        return [{"id": bot.id, "name": bot.name, "state": bot.state} for bot in obj.bots.all()]


class StrategySerializer(serializers.ModelSerializer):
    versions = StrategyVersionSerializer(many=True, read_only=True)
    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = Strategy
        fields = (
            "id",
            "name",
            "description",
            "created_at",
            "created_by",
            "versions",
            "latest_version",
        )
        read_only_fields = ("created_at", "created_by")

    def get_latest_version(self, obj):
        """The newest version, whole.

        The panel builds every strategy-shaped control off this one field — the
        editor's source, the "does it validate" dot, and the id every bot and
        backtest is created from — so it is the object, not its number. A bare
        integer here is what left the backtest's strategy list empty.
        """
        latest = obj.versions.order_by("-version").first()
        return StrategyVersionSerializer(latest).data if latest else None


class BotSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy_version.strategy.name", read_only=True)
    version = serializers.IntegerField(source="strategy_version.version", read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    # Named to match the frontend's `BotSummary.latest_run` — the panel seeds
    # its per-bot run cache from this on every list load, socket pushes aside.
    latest_run = serializers.SerializerMethodField()

    class Meta:
        model = Bot
        fields = (
            "id",
            "name",
            "strategy_version",
            "strategy_name",
            "version",
            "symbol",
            "interval",
            "market",
            "leverage",
            "sl_pct",
            "tp_pct",
            "input_values",
            "risk_config",
            "state",
            "dry_run",
            "drills_fired",
            "created_at",
            "updated_at",
            "created_by",
            "latest_run",
        )
        read_only_fields = ("state", "dry_run", "created_by", "drills_fired")

    def get_latest_run(self, obj):
        run = obj.runs.order_by("-started_at").first()
        return BotRunSerializer(run).data if run else None


class BotRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotRun
        fields = (
            "id",
            "started_at",
            "stopped_at",
            "stop_reason",
            "stop_detail",
            "warmup_bars",
            "feed_source",
            "last_bar_time",
            "peak_equity",
            "consecutive_losses",
            "recoveries",
            "unplanned_recoveries",
            "feed_gaps",
            "feed_gaps_repaired",
            "halt_drills",
            "divergences",
            "bars_evaluated",
        )


class BotBarSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotBar
        fields = (
            "bar_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "plots",
            "intent",
            "evaluation_ms",
            "changed",
        )


class BotActionSerializer(serializers.ModelSerializer):
    """The one serializer carrying per-account data. ``legs`` is filtered in the view."""

    legs = serializers.SerializerMethodField()

    class Meta:
        model = BotAction
        fields = (
            "id",
            "bar_time",
            "action_type",
            "idempotency_key",
            "reason",
            "intent",
            "created_at",
            "dispatched_at",
            "settled_at",
            "trade",
            "ok",
            "error",
            "legs",
        )

    def get_legs(self, obj) -> list:
        hidden = self.context.get("hidden_ids") or set()
        legs = (obj.result or {}).get("legs", [])
        return [leg for leg in legs if leg.get("account_id") not in hidden]


class BacktestRunRowSerializer(serializers.ModelSerializer):
    """One line of backtest history.

    Deliberately without ``equity_curve`` and ``trade_log``: they are the bulk
    of a stored run and a list renders neither, so sending them turns opening
    the page into a megabyte download per row.
    """

    strategy_name = serializers.CharField(source="strategy_version.strategy.name", read_only=True)
    version = serializers.IntegerField(source="strategy_version.version", read_only=True)

    class Meta:
        model = BacktestRun
        fields = (
            "id",
            "strategy_version",
            "strategy_name",
            "version",
            "symbol",
            "interval",
            "market",
            "from_time",
            "to_time",
            "bars",
            "trades",
            "metrics",
            "intent_digest",
            "created_at",
            "created_by",
        )


class BacktestRunSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy_version.strategy.name", read_only=True)

    class Meta:
        model = BacktestRun
        fields = (
            "id",
            "strategy_version",
            "strategy_name",
            "symbol",
            "interval",
            "market",
            "from_time",
            "to_time",
            "input_values",
            "bars",
            "trades",
            "metrics",
            "assumptions",
            "equity_curve",
            "trade_log",
            "intent_digest",
            "created_at",
            "created_by",
        )
