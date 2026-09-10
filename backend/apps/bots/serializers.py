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
    InputPreset,
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

        Read off the prefetched list rather than re-queried. ``.order_by()`` on
        a related manager **discards the prefetch**, so this was one extra query
        per strategy on a page that already fetches every version.
        """
        latest = _newest(obj)
        return StrategyVersionSerializer(latest).data if latest else None


def _newest(strategy):
    versions = list(strategy.versions.all())
    return max(versions, key=lambda row: row.version) if versions else None


class StrategyListSerializer(serializers.ModelSerializer):
    """A strategy as the *bots* pages need it: which script, and its newest id.

    The full shape carries every version with its whole Pine source, its
    validation report and its resolved properties. The strategies editor wants
    exactly that; the bots list and the backtest form want a name and an id, and
    downloading megabytes of source to draw a dropdown is what made ``/bots``
    open on a skeleton and need a refresh.
    """

    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = Strategy
        fields = ("id", "name", "description", "created_at", "created_by", "latest_version")

    def get_latest_version(self, obj):
        latest = _newest(obj)
        if latest is None:
            return None
        return {
            "id": latest.id,
            "version": latest.version,
            "parsed_ok": latest.parsed_ok,
            "created_at": latest.created_at,
        }


#: What a bot trades, and so what cannot change while it is paper or live.
#: ``name`` is deliberately absent: renaming a running bot changes nothing it does.
RUNNING_FROZEN = ("symbol", "interval", "market", "leverage", "sl_pct", "tp_pct")


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
            "property_overrides",
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
        """The newest run, off the prefetched list.

        ``obj.runs.order_by(...)`` discards the prefetch and re-queries — one
        extra round trip per bot on the list page, which is exactly the kind of
        thing that turns a fast page into a slow one as bots accumulate.
        """
        runs = list(obj.runs.all())
        run = max(runs, key=lambda row: row.started_at) if runs else None
        return BotRunSerializer(run).data if run else None

    def validate_property_overrides(self, value):
        """Refuse by name rather than storing something that reads back different.

        ``properties.resolve`` drops a bad key in silence on purpose — it runs
        behind a validator that has already named it. A form post is the other
        case: somebody is looking at the field, so an unusable value has to come
        back as an error against that field instead of vanishing into a default
        the next backtest would then be captioned with.
        """
        from apps.pine import properties as props

        clean, errors = props.validate_overrides(value)
        if errors:
            raise serializers.ValidationError([row["message"] for row in errors])
        return props.serialise_overrides(clean)

    def validate_interval(self, value):
        """Only a timeframe the feed can serve — native or folded (``feed_base``).

        Checked here rather than at start-up, where an unknown interval is a
        bot that refuses to run long after the form that produced it closed.
        """
        from apps.exchanges.feed_base import INTERVALS

        if value not in INTERVALS:
            raise serializers.ValidationError(f"unsupported interval {value!r}")
        return value

    def validate_market(self, value):
        from apps.exchanges.base import MarketType

        try:
            return MarketType(value).value
        except ValueError as exc:
            raise serializers.ValidationError(f"unsupported market {value!r}") from exc

    def validate(self, attrs):
        """Two object-level rules, because each needs the instance as well as the payload.

        **What a bot trades is frozen while it runs.** The pair, timeframe,
        market, leverage and levels may change on a draft or stopped bot, never
        under a paper or live one: its state machine would go on describing a
        market it is no longer trading. The panel greys those fields out, and
        this is what makes that true rather than cosmetic. The version is frozen
        always — it is the bot's identity, and a new script is a new bot.

        **Inputs are held to the schema of the version they will run against**,
        and on a PATCH only one of the two is in the payload — the other is on
        the instance. A bot whose inputs were checked against the wrong version's
        schema is a bot with an out-of-range length in it, which the runtime will
        happily use.
        """
        from apps.pine import inputs as pine_inputs

        if self.instance is not None:
            version = attrs.get("strategy_version")
            if version is not None and version != self.instance.strategy_version:
                raise serializers.ValidationError(
                    {"strategy_version": ["a bot's version is its identity — build a new bot"]}
                )
            if self.instance.is_running:
                moved = [
                    field
                    for field in RUNNING_FROZEN
                    if field in attrs and attrs[field] != getattr(self.instance, field)
                ]
                if moved:
                    raise serializers.ValidationError(
                        {field: ["stop the bot before changing this"] for field in moved}
                    )

        if "input_values" not in attrs:
            return attrs
        version = attrs.get("strategy_version") or getattr(self.instance, "strategy_version", None)
        if version is None:
            return attrs
        schema = pine_inputs.InputSchema.from_data(version.inputs_schema)
        clean, errors = pine_inputs.validate_values(schema, attrs["input_values"])
        if errors:
            raise serializers.ValidationError(
                {"input_values": [f"{row['name']}: {row['message']}" for row in errors]}
            )
        attrs["input_values"] = clean
        return attrs


class InputPresetSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy.name", read_only=True)

    class Meta:
        model = InputPreset
        fields = (
            "id",
            "strategy",
            "strategy_name",
            "name",
            "values",
            "created_at",
            "updated_at",
            "created_by",
        )
        read_only_fields = ("created_by",)

    def validate_values(self, value):
        """A preset is a plain name → value map and nothing else.

        Not checked against a schema here: a preset outlives the version it was
        saved from, and refusing to *store* one because the current script
        dropped an input would delete a set of settings the operator may want
        back on the next version. It is checked where it is applied.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError("must be an object of input name → value")
        return value


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
    """The one serializer carrying per-account data. ``legs`` is filtered in the view.

    ``side``, ``price``, ``symbol`` and ``interval`` are here for the dry-run
    case. A shadow action has no trade and no legs behind it — it is what the
    bot *would* have done — so without them the panel could say only that
    something happened at a time. What, at what price, on which instrument, is
    the whole content of a paper run, and it is read off the bar the decision
    was made on rather than recomputed.
    """

    legs = serializers.SerializerMethodField()
    side = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    symbol = serializers.SerializerMethodField()
    interval = serializers.SerializerMethodField()

    class Meta:
        model = BotAction
        fields = (
            "id",
            "bar_time",
            "action_type",
            "idempotency_key",
            "reason",
            "intent",
            "side",
            "price",
            "symbol",
            "interval",
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

    def get_side(self, obj) -> str | None:
        return (obj.intent or {}).get("side")

    def get_price(self, obj) -> str | None:
        """The close of the bar this action was decided on, as a string.

        Decimal all the way to the wire, same rule as every other price on this
        platform. ``None`` when the bar was trimmed by retention — an old row
        with no price is honest; an invented one is not.
        """
        prices = self.context.get("bar_prices") or {}
        value = prices.get(obj.bar_time)
        return None if value is None else str(value)

    def get_symbol(self, obj) -> str:
        return self.context.get("symbol", "")

    def get_interval(self, obj) -> str:
        return self.context.get("interval", "")


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
