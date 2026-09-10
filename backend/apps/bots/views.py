"""``/api/bots/`` — CRUD, validate, backtest, start, stop, runs, bars, policy.

DRF where the endpoint only reads, plain async Django views where it routes —
the same split ``apps/trading`` uses, and for the same reason: DRF 3.15 has no
async view support, so a routing endpoint behind it would run the fan-out in a
worker thread and serialise the legs, which is exactly what the spec §4 deadline
cannot afford.

Every read surface here filters hidden accounts (Q27). In practice that is one
field — ``BotAction.legs`` — because a bot's other payloads carry no per-account
data at all; ``tests/test_account_access.py`` has a case for it, and that file is
the checklist when a new surface is added.
"""

from __future__ import annotations

import json
import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Prefetch, ProtectedError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.visibility import _filtered  # read surface only — see apps/bots/__init__.py
from apps.bots import drills, gate, jobs, lifecycle, narrate
from apps.bots.config import limits
from apps.bots.models import (
    BacktestJob,
    BacktestRun,
    Bot,
    BotAction,
    BotRun,
    BotState,
    InputPreset,
    StopReason,
    Strategy,
    StrategyVersion,
)
from apps.bots.serializers import (
    BacktestRunRowSerializer,
    BacktestRunSerializer,
    BotActionSerializer,
    BotBarSerializer,
    BotRunSerializer,
    BotSerializer,
    InputPresetSerializer,
    StrategyListSerializer,
    StrategySerializer,
    StrategyVersionSerializer,
)
from apps.core.auth import admin_required
from apps.pine.validate import validate
from apps.security import stepup

logger = logging.getLogger(__name__)


class StrategyViewSet(viewsets.ModelViewSet):
    queryset = Strategy.objects.prefetch_related("versions__bots")
    serializer_class = StrategySerializer
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        """``?compact=1`` on the list is the bots pages' shape — see the serializer.

        Only on ``list``: a retrieve is the editor asking for one strategy, and
        that one really does want every version's source.
        """
        if self.action == "list" and self.request.query_params.get("compact"):
            return StrategyListSerializer
        return StrategySerializer

    def get_queryset(self):
        if self.action == "list" and self.request.query_params.get("compact"):
            # No `versions__bots`: the compact shape carries no `used_by`, and
            # that prefetch walks every bot on the platform.
            return Strategy.objects.prefetch_related("versions")
        return super().get_queryset()

    def perform_create(self, serializer) -> None:
        serializer.save(created_by=self.request.user.get_username())

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Delete a strategy and its versions.

        ``StrategyVersion`` cascades, but ``Bot.strategy_version`` is
        ``PROTECT`` — a version a bot points at cannot vanish under it. So a
        strategy any bot was built from refuses deletion with a 409 that names
        the bots, rather than a 500 from the raw ``ProtectedError``. Delete
        those bots first.
        """
        strategy = self.get_object()
        try:
            strategy.delete()
        except ProtectedError as exc:
            bots = sorted({obj.name for obj in exc.protected_objects if isinstance(obj, Bot)})
            return Response(
                {
                    "code": "strategy_in_use",
                    "detail": (
                        "This strategy still has bots built from it: "
                        + ", ".join(bots)
                        + ". Delete them first."
                    ),
                    "bots": bots,
                },
                status=409,
            )
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def versions(self, request: Request, pk=None) -> Response:
        """Save a new version. **Immutable** — editing never rewrites one.

        A running bot points at a version, so a bot's behaviour cannot change
        under it because somebody saved in another tab, and a stored backtest
        still names source that is still exactly what produced it.
        """
        strategy = self.get_object()
        source = request.data.get("source", "")
        if not source.strip():
            return Response({"detail": "source is required"}, status=400)

        result = validate(source, limits=limits())
        latest = strategy.versions.order_by("-version").first()
        version = StrategyVersion.objects.create(
            strategy=strategy,
            version=(latest.version + 1) if latest else 1,
            source=source,
            parsed_ok=result.ok,
            validation_errors=[e.as_dict() for e in result.errors],
            validation_warnings=[w.as_dict() for w in result.warnings],
            inputs_schema=result.input_schema.as_dict(),
            properties=result.properties.as_dict(),
            property_notes={
                "live_departures": result.properties.live_departures(),
                "inert": result.properties.inert_here(),
            },
            created_by=request.user.get_username(),
        )
        return Response(StrategyVersionSerializer(version).data, status=201)


class BotViewSet(viewsets.ModelViewSet):
    # `runs` is prefetched **ordered**, because `get_latest_run` reads the
    # newest off the prefetched list. An `.order_by()` on the related manager
    # would discard the prefetch and cost one query per bot.
    queryset = Bot.objects.select_related("strategy_version__strategy").prefetch_related(
        Prefetch("runs", queryset=BotRun.objects.order_by("-started_at"))
    )
    serializer_class = BotSerializer
    permission_classes = [IsAdminUser]

    def perform_create(self, serializer) -> None:
        serializer.save(created_by=self.request.user.get_username())

    @action(detail=True, methods=["get"])
    def runs(self, request: Request, pk=None) -> Response:
        bot = self.get_object()
        return Response(BotRunSerializer(bot.runs.all()[:50], many=True).data)

    @action(detail=True, methods=["get"])
    def bars(self, request: Request, pk=None) -> Response:
        bot = self.get_object()
        run = bot.runs.order_by("-started_at").first()
        if run is None:
            return Response([])
        limit = min(int(request.query_params.get("limit", 500)), 2000)
        return Response(BotBarSerializer(run.bars.all()[:limit], many=True).data)

    @action(detail=True, methods=["get"])
    def actions(self, request: Request, pk=None) -> Response:
        """The action log, with fan-out legs. The one bot surface naming accounts.

        Also carries the price each decision was made at, looked up once for the
        whole page. A dry run has no fills to read a price back out of, so
        without this the paper log could say when a bot went long but never at
        what — which is most of what a paper run is for.
        """
        bot = self.get_object()
        run = bot.runs.order_by("-started_at").first()
        if run is None:
            return Response([])
        rows = list(BotAction.objects.filter(run=run).select_related("trade")[:200])
        prices = dict(
            run.bars.filter(bar_time__in=[row.bar_time for row in rows]).values_list(
                "bar_time", "close"
            )
        )
        return Response(
            BotActionSerializer(
                rows,
                many=True,
                context={
                    "hidden_ids": _filtered(request.user),
                    "bar_prices": prices,
                    "symbol": bot.symbol,
                    "interval": bot.interval,
                },
            ).data
        )

    @action(detail=True, methods=["get"])
    def journal(self, request: Request, pk=None) -> Response:
        """What the bot was thinking, bar by bar — see ``narrate.py``.

        The action log answers "what did it do"; on most bars the answer is
        "nothing", and *why* nothing is the question an operator actually has.
        Events are codes and parameters, never sentences: the panel renders them
        through i18n, which is the only way this reads in six languages.
        """
        bot = self.get_object()
        run = bot.runs.order_by("-started_at").first()
        if run is None:
            return Response({"events": [], "run": None})
        limit = min(int(request.query_params.get("limit", 300)), 1000)
        return Response(
            {"run": BotRunSerializer(run).data, "events": narrate.journal(run, limit=limit)}
        )

    @action(detail=True, methods=["get"])
    def logic(self, request: Request, pk=None) -> Response:
        """What makes this strategy trade, read back out of its own source.

        Not a paraphrase. The conditions come from the script's ``if`` tests as
        written, so a reader can check them against the source tab beside it —
        a plain-English summary of a strategy is the most convincing thing on
        the page to be wrong.
        """
        from apps.pine import explain

        bot = self.get_object()
        return Response(
            {
                "bot": bot.id,
                **explain.explain(bot.strategy_version.source).as_dict(),
            }
        )

    @action(detail=True, methods=["get"])
    def chart(self, request: Request, pk=None) -> Response:
        """Candles, the script's own plotted series, and where it acted.

        Two sources, and the difference is the point. At the bot's **own**
        interval the series are the values the runtime actually recorded, bar by
        bar (``BotBar.plots``) — what the bot really saw. At any other interval
        there is no such record, so the strategy is **replayed** over that
        timeframe purely to draw it, and the payload says ``replayed: true``.

        A replay changes nothing: it never touches the bot, its run, its
        position or its interval. Switching the timeframe on a chart must not be
        a trading control.
        """
        bot = self.get_object()
        interval = request.query_params.get("interval") or bot.interval
        limit = min(int(request.query_params.get("limit", 400)), 1500)
        try:
            payload = _chart_payload(bot, interval=interval, limit=limit)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(payload)

    @action(detail=True, methods=["get"])
    def accounts(self, request: Request, pk=None) -> Response:
        """Which connected accounts this bot would actually reach.

        A bot routes only to accounts with ``bot_trading_enabled`` on (the
        accounts page's second switch). That switch defaults **off**, so the
        commonest reason a working bot does nothing is that no account has
        opted in — and a bot page that did not say so left the operator
        debugging the strategy.
        """
        from apps.accounts.models import AccountStatus, ConnectedAccount

        hidden = _filtered(request.user)
        rows = ConnectedAccount.objects.exclude(id__in=hidden).order_by("label")
        return Response(
            {
                "accounts": [
                    {
                        "id": row.id,
                        "label": row.label,
                        "exchange": row.exchange,
                        "status": row.status,
                        "bot_trading_enabled": row.bot_trading_enabled,
                        "manual_trading_enabled": row.manual_trading_enabled,
                        "eligible": row.status == AccountStatus.ACTIVE and row.bot_trading_enabled,
                    }
                    for row in rows
                ]
            }
        )

    @action(detail=True, methods=["get"])
    def promotion(self, request: Request, pk=None) -> Response:
        """The Phase 7 gate with this bot's own measurements filled in."""
        return Response(gate.evaluate(self.get_object()))

    @action(detail=True, methods=["post"], url_path="gate")
    def set_gate(self, request: Request, pk=None) -> Response:
        """Turn the promotion gate off, or waive one row of it.

        ``{"enforced": false}`` is the admin saying this bot may go live without
        the measurements; ``{"waive": "soak", "on": true}`` says the same about
        one row. Both are stored on the bot, so a promotion that skipped the
        numbers is answerable afterwards rather than a dialog nobody logged.

        The rows keep being measured either way. A gate that stops counting the
        moment it stops binding would leave the operator with no reading at all.
        """
        bot = self.get_object()
        changed = []

        if "enforced" in request.data:
            bot.gate_enforced = bool(request.data["enforced"])
            changed.append("gate_enforced")

        key = request.data.get("waive")
        if key:
            keys = {row["key"] for row in gate.evaluate(bot)["rows"]}
            if key not in keys:
                return Response({"detail": f"no gate row called {key!r}"}, status=400)
            waived = set(bot.gate_waived or [])
            waived.add(key) if request.data.get("on", True) else waived.discard(key)
            bot.gate_waived = sorted(waived)
            changed.append("gate_waived")

        if not changed:
            return Response({"detail": "nothing to change"}, status=400)
        bot.save(update_fields=[*changed, "updated_at"])
        logger.info(
            "bot %s gate changed by %s: enforced=%s waived=%s",
            bot.id,
            request.user.get_username(),
            bot.gate_enforced,
            bot.gate_waived,
            extra={"category": "BOT"},
        )
        return Response({"gate": gate.evaluate(bot)})

    @action(detail=True, methods=["post"], url_path="acknowledge-adapters")
    def acknowledge_adapters(self, request: Request, pk=None) -> Response:
        """Tick (or untick) the one gate row that cannot be measured from inside.

        ``docs/adapters.md``'s blocker is a fact about the exchanges, not about
        this bot, so no counter can clear it — a person has to say they have run
        the adapters against a testnet. Keeping the row and making it tickable
        *here* is the difference between a gate and a dead end: the answer, who
        gave it and when are all recorded, and it can be taken back.
        """
        bot = self.get_object()
        on = bool(request.data.get("acknowledged", True))
        drills.acknowledge_adapters(bot, actor=request.user.get_username(), on=on)
        return Response({"risk_config": bot.risk_config, "gate": gate.evaluate(bot)})

    @action(detail=True, methods=["get"])
    def properties(self, request: Request, pk=None) -> Response:
        """TradingView's Properties tab for this bot, already resolved.

        The panel gets the *outcome* — one value per property, with the source
        that won it — rather than three dictionaries and the merge rule. The
        merge rule is ``properties.resolve`` and it exists once; a browser
        reimplementing it is a second place for platform → script → panel to be
        got wrong, and the report header would be the thing that disagreed.

        ``schema`` travels with it so the form is drawn from the same list the
        validator polices. ``live_departures`` and ``inert`` are the sentences
        that keep this honest: this tab configures the **backtest**, and every
        setting on it that live will not honour says so on its own row.
        """
        from apps.pine import properties as props

        bot = self.get_object()
        declared_raw = bot.strategy_version.properties or {}
        # `StrategyVersion.properties` is a resolved set stored as JSON, so it
        # carries every key. Only the ones the script actually set are the
        # script's opinion — the rest are the platform's and must not be
        # replayed as declarations, or every field would read "from the script".
        declared_keys = set(declared_raw.get("declared") or ())
        declared, _ = props.validate_overrides(
            {key: declared_raw.get(key) for key in declared_keys}
        )
        overrides, _ = props.validate_overrides(bot.property_overrides or {})

        resolved = props.resolve(declared=declared, overrides=overrides)
        return Response(
            {
                "bot": bot.id,
                "resolved": resolved.as_dict(),
                "overrides": props.serialise_overrides(overrides),
                "schema": props.schema_as_data(),
                "live_departures": resolved.live_departures(),
                "inert": resolved.inert_here(),
            }
        )

    @action(detail=True, methods=["get"])
    def inputs(self, request: Request, pk=None) -> Response:
        """The script's own settings for this bot, already resolved.

        The same shape as ``properties`` above and for the same reason: the
        panel is handed one value per input with the source that won it, not a
        schema and a dictionary of overrides and the rule for combining them.
        ``resolve_values`` is that rule and it exists once — a browser
        recomputing it is a second place for "the script said 65 and nobody
        changed it" to become "the operator chose 65".

        ``presets`` rides along because the form needs them on first paint, and
        a second request for four rows is a second spinner.
        """
        from apps.pine import inputs as pine_inputs

        bot = self.get_object()
        schema = pine_inputs.InputSchema.from_data(bot.strategy_version.inputs_schema)
        overrides, _ = pine_inputs.validate_values(schema, bot.input_values or {})
        return Response(
            {
                "bot": bot.id,
                "strategy_version": bot.strategy_version_id,
                # The preset endpoints key on the *strategy*, not the version —
                # a set of values outlives the revision it was typed against.
                "strategy": bot.strategy_version.strategy_id,
                "schema": schema.as_dict(),
                "resolved": pine_inputs.resolve_values(schema, overrides),
                "overrides": overrides,
                "presets": InputPresetSerializer(
                    bot.strategy_version.strategy.presets.all(), many=True
                ).data,
            }
        )


class InputPresetViewSet(viewsets.ModelViewSet):
    """Saved input sets, per strategy. ``?strategy=<id>`` to list one's own.

    Deliberately thin: a preset is a name and a dictionary, and the checking
    that matters happens where it is *applied* — against the version in hand,
    which is the only place that knows whether the script still has an input by
    that name.
    """

    queryset = InputPreset.objects.select_related("strategy")
    serializer_class = InputPresetSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        rows = super().get_queryset()
        strategy = self.request.query_params.get("strategy")
        return rows.filter(strategy_id=strategy) if strategy else rows

    def perform_create(self, serializer) -> None:
        serializer.save(created_by=self.request.user.get_username())


#: How many stored runs the history endpoint will hand back at once.
HISTORY_LIMIT = 200


class BacktestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Every backtest ever run, newest first.

    Stored rather than recomputed: a replay costs seconds and a download, and
    the number an operator acted on last week has to still be the number they
    saw. ``?strategy_version=`` narrows it to one version's own history.

    **Deletable**, unlike the action log. A backtest is a working note, not an
    audit record: nobody's capital moved because of a row here, and a history
    strip nobody can prune is one nobody reads after the twentieth experiment.
    ``BotAction`` is the thing that is kept forever (Q26), and it has no delete.

    The archived *candles* are never touched by a delete. They are the expensive
    half and they belong to the platform, not to any one report — throwing them
    away because a report was tidied would make the next run download them
    again, which is the opposite of why they are stored.
    """

    queryset = BacktestRun.objects.select_related("strategy_version__strategy").order_by(
        "-created_at"
    )
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=["delete"])
    def clear(self, request: Request) -> Response:
        """Delete a whole history at once — everything, or one version's.

        Same filters the list takes, so what is deleted is exactly what the
        panel was showing. Answers with the count, because "deleted" with no
        number is indistinguishable from "matched nothing".
        """
        rows = BacktestRun.objects.all()
        version = request.query_params.get("strategy_version")
        if version:
            rows = rows.filter(strategy_version_id=version)
        strategy = request.query_params.get("strategy")
        if strategy:
            rows = rows.filter(strategy_version__strategy_id=strategy)
        deleted, _ = rows.delete()
        return Response({"deleted": deleted})

    def get_serializer_class(self):
        # The list is a table of headline numbers; only the detail view renders
        # the curve and the trades, so only it pays for them.
        return BacktestRunSerializer if self.action == "retrieve" else BacktestRunRowSerializer

    def get_queryset(self):
        rows = super().get_queryset()
        version = self.request.query_params.get("strategy_version")
        if version:
            rows = rows.filter(strategy_version_id=version)
        strategy = self.request.query_params.get("strategy")
        if strategy:
            rows = rows.filter(strategy_version__strategy_id=strategy)
        # Capped rather than paginated: the panel reads this as a history strip,
        # and nobody scrolls to the two-hundredth backtest of a script. Only on
        # the list — `get_object` filters this queryset again, and a slice
        # cannot be filtered.
        return rows[:HISTORY_LIMIT] if self.action == "list" else rows


@api_view(["POST"])
@permission_classes([IsAdminUser])
def validate_source(request: Request) -> Response:
    """What the editor underlines. Never raises — every fault comes back as data.

    Deliberately the same call ``manage.py pine_check`` makes: if the command
    says a script is fine and the panel says it is not, one of them is wrong,
    rather than both being right about different things.
    """
    source = request.data.get("source", "")
    result = validate(source, limits=limits())
    return Response(result.as_dict())


@api_view(["GET"])
@permission_classes([IsAdminUser])
def policy(request: Request) -> Response:
    """``settings.BOT`` as the panel sees it — the decisions, live.

    Mirrors ``trading/policy/``. The two Q25 triggers that are absent are
    absent on purpose and say so, rather than appearing as a blank field
    somebody would later "fix" by giving them a number.

    Staff-gated like every other bot endpoint. It fell back to DRF's
    ``IsAuthenticated`` default, which on a platform with one shared staff login
    is the same set of people — but the test above is called
    ``test_every_read_endpoint_is_staff_only`` and this is what makes that true
    by construction rather than by there happening to be no other users.
    """
    values = settings.BOT
    return Response(
        {
            **{key: values[key] for key in sorted(values)},
            "non_configurable_stops": {
                "feed_gap": "any — the first unrepairable gap stops the bot (Q25)",
                "script_error": "any — the first runtime error stops the bot (Q25)",
            },
            "decisions": {
                "sizing": "Q20 — the platform sizes; a script's qty is ignored with a warning",
                "sltp": "Q21 — bot-level, a percent strategy.exit wins per trade",
                "contention": "Q22 — first claim wins; close-all and Stop-all stop every bot",
                "bar_timing": "Q23 — confirmed bars only",
                "subset": "Q24 — everything outside the v1 subset is rejected by name",
                "auto_stop": "Q25 — seven triggers, none of them auto-resume",
                "retention": "Q26 — every intent and action forever; bars by timeframe",
                "hidden_accounts": "Q27 — routed to identically, filtered on every read",
            },
        }
    )


# --- the routing half: plain async views, CSRF enforced ----------------------


def _body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@require_POST
@csrf_protect
@admin_required
async def start_bot(request: HttpRequest, pk: int) -> JsonResponse:
    """Move a bot into ``paper`` or ``live`` and start its task.

    ``live`` is refused unless the Phase 7 gate is met. Not a confirmation
    dialog — a gate that knows the numbers, and refuses while any row is unmet.
    """
    from apps.bots import supervisor

    bot = await sync_to_async(_get_bot)(pk)
    if bot is None:
        return JsonResponse({"detail": "no such bot"}, status=404)

    target = _body(request).get("state", BotState.PAPER)
    if target not in (BotState.PAPER, BotState.LIVE):
        return JsonResponse({"detail": "a bot can be started into paper or live"}, status=400)

    if target == BotState.LIVE:
        # Promoting a bot to live is the third thing step-up guards, alongside
        # credentials and money records: rare, deliberate, and expensive to
        # undo. Checked by hand rather than through the DRF mixin because this
        # is a plain async view — see apps.security.stepup.
        if not await sync_to_async(stepup.satisfied)(request):
            return JsonResponse(
                {
                    "detail": "confirm your password to put a bot live",
                    "code": "step_up_required",
                    "action": "bot_live",
                },
                status=403,
            )
        readiness = await sync_to_async(gate.evaluate)(bot)
        if not readiness["ready"]:
            return JsonResponse(
                {
                    "detail": "this bot has not met the promotion gate",
                    "code": "gate_unmet",
                    "gate": readiness,
                },
                status=409,
            )

    try:
        bot = await sync_to_async(lifecycle.transition)(bot, target)
    except lifecycle.IllegalTransition as exc:
        return JsonResponse({"detail": str(exc), "code": "illegal_transition"}, status=409)

    # Only one bot may run at a time. Deactivating the others *after* this
    # one's own transition and gate checks have already passed means a start
    # that is about to be refused (an illegal transition, an unmet live gate)
    # never takes down a bot that was working fine.
    deactivated = await sync_to_async(_other_running_ids)(bot.id)
    for other_id in deactivated:
        await supervisor.stop(
            other_id,
            reason=StopReason.MANUAL,
            detail=f"deactivated to activate “{bot.name}” — only one bot runs at a time",
        )

    run = await supervisor.start(bot)
    return JsonResponse(
        {"bot_id": bot.id, "state": bot.state, "run_id": run.id, "deactivated": deactivated}
    )


@require_POST
@csrf_protect
@admin_required
async def stop_bot(request: HttpRequest, pk: int) -> JsonResponse:
    from apps.bots import supervisor

    bot = await sync_to_async(_get_bot)(pk)
    if bot is None:
        return JsonResponse({"detail": "no such bot"}, status=404)

    detail = str(_body(request).get("reason", ""))[:200]
    await supervisor.stop(
        bot.id, reason=StopReason.MANUAL, detail=detail or "stopped from the panel"
    )
    return JsonResponse({"bot_id": bot.id, "state": BotState.STOPPED})


@require_POST
@csrf_protect
@admin_required
async def run_backtest(request: HttpRequest) -> JsonResponse:
    """Start a replay. Returns a **job**, not a report.

    A first run on a pair the archive has never seen spends most of its wall
    clock paging a public endpoint for history — up to
    ``backtest.DOWNLOAD_BUDGET_SECONDS`` of it. A request that returns after
    ninety seconds behind a spinner is indistinguishable from a hang, so the
    work moves to a thread and the panel polls ``backtest_job`` for a bar that
    actually moves. ``apps/bots/jobs.py`` owns the phases and their weights.

    ``{"wait": true}`` keeps the old synchronous shape for scripts and tests:
    the full report comes back in the response, exactly as before.
    """
    from apps.bots import backtest

    payload = _body(request)
    version_id = payload.get("strategy_version")
    version = await sync_to_async(_get_version)(version_id)
    if version is None:
        return JsonResponse({"detail": "no such strategy version"}, status=404)

    from decimal import InvalidOperation

    from apps.exchanges.base import MarketType

    # The Properties tab, third step of the merge. Sent explicitly by the
    # backtest form, or taken from the bot when the panel is replaying *that
    # bot* — a report run from a bot's page has to be captioned with the
    # properties that bot would run under, not the script's bare declaration.
    from apps.pine import properties as props

    overrides, property_errors = props.validate_overrides(payload.get("property_overrides"))
    if property_errors:
        return JsonResponse(
            {"detail": "bad strategy properties", "properties": property_errors}, status=400
        )
    if not overrides and payload.get("bot"):
        bot = await sync_to_async(_get_bot)(payload["bot"])
        if bot is not None:
            overrides, _ = props.validate_overrides(bot.property_overrides or {})
    payload = {**payload, "property_overrides": props.serialise_overrides(overrides)}

    # The author's half of the same dialog. Held to the version's own schema
    # here rather than at the runtime, where an out-of-range length is a wrong
    # report instead of a refusal — and a report is what a promotion is read off.
    from apps.pine import inputs as pine_inputs

    schema = pine_inputs.InputSchema.from_data(version.inputs_schema)
    values, input_errors = pine_inputs.validate_values(schema, payload.get("inputs"))
    if input_errors:
        return JsonResponse({"detail": "bad strategy inputs", "inputs": input_errors}, status=400)
    payload = {**payload, "inputs": values}

    user = await request.auser()
    if not payload.get("wait"):
        job = await sync_to_async(jobs.start)(version, payload, actor=user.get_username())
        return JsonResponse({"job_id": job.id, **jobs.state(job)}, status=202)

    try:
        report = await sync_to_async(backtest.run)(
            source=version.source,
            symbol=str(payload.get("symbol", "")).upper(),
            interval=str(payload.get("interval", "1h")),
            market=MarketType(payload.get("market", "futures")),
            from_time=int(payload["from_time"]),
            to_time=int(payload["to_time"]),
            leverage=int(payload.get("leverage", 1)),
            sl_pct=_decimal(payload.get("sl_pct")),
            tp_pct=_decimal(payload.get("tp_pct")),
            inputs=payload.get("inputs") or {},
            property_overrides=overrides,
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        return JsonResponse({"detail": f"bad request: {exc}"}, status=400)
    except backtest.BacktestError as exc:
        return JsonResponse({"detail": str(exc), "code": "backtest_failed"}, status=409)

    stored = await sync_to_async(jobs.store)(version, report, payload, user.get_username())
    return JsonResponse({"backtest_id": stored.id, **report.as_dict()})


@api_view(["GET"])
@permission_classes([IsAdminUser])
def strategy_version(request: Request, pk: int) -> Response:
    """One version, whole — source included.

    The bot detail page needs the exact source its own version pins, and that is
    the only reason it used to load every strategy on the platform. One row by
    id is the question it was actually asking.
    """
    version = StrategyVersion.objects.filter(pk=pk).prefetch_related("bots").first()
    if version is None:
        return Response({"detail": "no such version"}, status=404)
    return Response(StrategyVersionSerializer(version).data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def version_properties(request: Request, pk: int) -> Response:
    """The Properties tab for a strategy *version*, with no bot in the picture.

    The bot page reads ``/bots/<id>/properties/``, where the third step of the
    merge is that bot's saved overrides. The backtest form has no bot — it is
    about to run a version — so it needs the same schema and the same
    platform → script resolution with the overrides left to the caller, which
    holds them in the form and posts them with the run.

    Same ``properties.resolve``, same two note lists. A second merge rule for
    the second caller is how the report header and the form that produced it
    start disagreeing.
    """
    from apps.pine import properties as props

    version = StrategyVersion.objects.filter(pk=pk).first()
    if version is None:
        return Response({"detail": "no such strategy version"}, status=404)

    declared_raw = version.properties or {}
    # Only the keys the script actually set are the script's opinion; the rest
    # are the platform's, and replaying them as declarations would make every
    # field read "from the script".
    declared_keys = set(declared_raw.get("declared") or ())
    declared, _ = props.validate_overrides({key: declared_raw.get(key) for key in declared_keys})
    resolved = props.resolve(declared=declared, overrides={})
    return Response(
        {
            "strategy_version": version.id,
            "resolved": resolved.as_dict(),
            "overrides": {},
            "schema": props.schema_as_data(),
            "live_departures": resolved.live_departures(),
            "inert": resolved.inert_here(),
        }
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def version_inputs(request: Request, pk: int) -> Response:
    """The settings panel for a strategy *version*, with no bot in the picture.

    What the backtest form draws before a run: the same schema and the same
    defaults the bot page uses, with the overrides left to the caller, which
    holds them in the form and posts them with the run.
    """
    from apps.pine import inputs as pine_inputs

    version = StrategyVersion.objects.filter(pk=pk).select_related("strategy").first()
    if version is None:
        return Response({"detail": "no such strategy version"}, status=404)

    schema = pine_inputs.InputSchema.from_data(version.inputs_schema)
    return Response(
        {
            "strategy_version": version.id,
            "strategy": version.strategy_id,
            "schema": schema.as_dict(),
            "resolved": schema.defaults(),
            "overrides": {},
            "presets": InputPresetSerializer(version.strategy.presets.all(), many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def backtest_job(request: Request, pk: int) -> Response:
    """One job's progress. Polled by the panel roughly once a second."""
    job = BacktestJob.objects.filter(pk=pk).first()
    if job is None:
        return Response({"detail": "no such backtest job"}, status=404)
    return Response(jobs.state(job))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def backtest_coverage(request: Request) -> Response:
    """How much of a window the archive already holds, before anything is run.

    So the form can say "4,300 bars stored, about 1,200 to download" instead of
    making the operator discover it from how long the run takes. Cheap: one
    indexed count, no network.
    """
    from apps.bots.feed import interval_seconds
    from apps.exchanges import candlestore, marketdata
    from apps.exchanges.base import MarketType

    symbol = str(request.query_params.get("symbol", "")).upper()
    interval = str(request.query_params.get("interval", "1h"))
    if not symbol:
        return Response({"detail": "symbol is required"}, status=400)
    try:
        market = MarketType(request.query_params.get("market", "futures"))
        step = interval_seconds(interval)
        from_time = int(request.query_params["from_time"])
        to_time = int(request.query_params["to_time"])
    except (KeyError, TypeError, ValueError) as exc:
        return Response({"detail": f"bad request: {exc}"}, status=400)

    expected = max(1, (to_time - from_time) // step)
    stored = candlestore.read_window(
        symbol=symbol,
        interval=interval,
        market=market,
        limit=expected + 10,
        end=to_time,
        exchange=marketdata.pinned_provider(),
    )
    rows = list(stored[0]) if stored else []
    held = [candle for candle in rows if from_time <= candle.time <= to_time]
    return Response(
        {
            "symbol": symbol,
            "interval": interval,
            "expected": expected,
            "stored": len(held),
            "oldest": min((c.time for c in held), default=None),
            "newest": max((c.time for c in held), default=None),
            # A window this dense is served from the archive with no network
            # call at all — the same threshold `backtest._covers` applies.
            "cached": len(held) >= float(backtest_coverage_ratio()) * expected,
        }
    )


def backtest_coverage_ratio():
    from apps.bots.backtest import COVERAGE_RATIO

    return COVERAGE_RATIO


# --- drills: the safety machinery, fired on purpose --------------------------


def _decimal(value):
    from decimal import Decimal

    return None if value in (None, "") else Decimal(str(value))


def _get_bot(pk: int) -> Bot | None:
    return Bot.objects.filter(id=pk).select_related("strategy_version").first()


def _other_running_ids(bot_id: int) -> list[int]:
    """Every *other* bot currently paper or live — the ones about to lose the slot."""
    return list(
        Bot.objects.filter(state__in=[BotState.PAPER, BotState.LIVE])
        .exclude(id=bot_id)
        .values_list("id", flat=True)
    )


def _get_version(pk) -> StrategyVersion | None:
    return StrategyVersion.objects.filter(id=pk).first() if pk else None


def _chart_payload(bot: Bot, *, interval: str, limit: int) -> dict:
    """Candles, the script's plotted series, and the bars it acted on.

    Two paths, and the difference is stated in the payload rather than blurred:

      **The bot's own interval** reads ``BotBar`` — the values the runtime
      really recorded on the bars it really saw. Nothing is recomputed, so the
      chart cannot disagree with the journal beside it.

      **Any other interval** has no such record, so the strategy is replayed
      over that timeframe *for display only*. ``replayed`` is true, and nothing
      about the bot, its run, its position or its interval is touched.
    """
    from apps.bots.feed import interval_seconds, to_bar, warmup_bars_needed
    from apps.exchanges import candlestore, marketdata
    from apps.exchanges.base import MarketType

    interval_seconds(interval)  # raises ValueError on an interval nothing supports
    market = MarketType(bot.market)
    run = bot.runs.order_by("-started_at").first()
    own = interval == bot.interval

    if own and run is not None:
        rows = list(run.bars.order_by("-bar_time")[:limit])
        rows.reverse()
        if rows:
            return {
                "interval": interval,
                "replayed": False,
                "symbol": bot.symbol,
                "candles": [
                    {
                        "time": row.bar_time,
                        "open": str(row.open),
                        "high": str(row.high),
                        "low": str(row.low),
                        "close": str(row.close),
                        "volume": str(row.volume),
                    }
                    for row in rows
                ],
                "series": _series_from([(row.bar_time, row.plots or {}) for row in rows]),
                "markers": _markers_from_bars(rows) + _markers_from_actions(run, limit),
                "note": "",
            }

    # Nothing recorded at this interval — replay it, and say so.
    warmup = warmup_bars_needed(_longest_lookback_of(bot))
    stored = candlestore.read_window(
        symbol=bot.symbol,
        interval=interval,
        market=market,
        limit=limit + warmup,
        exchange=marketdata.pinned_provider(),
    )
    candles = list(stored[0]) if stored else []
    if not candles:
        return {
            "interval": interval,
            "replayed": True,
            "symbol": bot.symbol,
            "candles": [],
            "series": [],
            "markers": [],
            # Not an error. The archive fills as the platform runs, and a
            # timeframe nobody has looked at yet simply has no bars stored.
            "note": "no_history",
        }

    traced = _replay_for_display(bot, [to_bar(candle) for candle in candles], interval, warmup)
    drawn = candles[warmup:] or candles
    return {
        "interval": interval,
        "replayed": True,
        "symbol": bot.symbol,
        "candles": [
            {
                "time": candle.time,
                "open": str(candle.open),
                "high": str(candle.high),
                "low": str(candle.low),
                "close": str(candle.close),
                "volume": str(candle.volume),
            }
            for candle in drawn
        ],
        "series": _series_from([(time, plots) for time, plots, _ in traced]),
        "markers": _markers_from_trace(traced),
        "note": "",
    }


def _longest_lookback_of(bot: Bot) -> int:
    from apps.bots.backtest import _longest_lookback

    return _longest_lookback(validate(bot.strategy_version.source, limits=limits()))


def _replay_for_display(bot: Bot, bars, interval: str, warmup: int) -> list[tuple]:
    """Run the script over these bars purely to record what it plots.

    The *same* ``Runtime`` the live loop and the backtest use — there is only
    one — so the lines drawn here are the lines the bot would compute. What it
    is not is a decision: nothing is routed, nothing is stored, and the first
    ``warmup`` bars are dropped because their indicators have not converged.
    """
    from apps.pine.errors import PineError
    from apps.pine.runtime import Runtime
    from apps.pine.symbol import SymbolInfo, TimeframeInfo

    result = validate(bot.strategy_version.source, limits=limits())
    if not result.ok:
        return []
    runtime = Runtime(
        result.program,
        symbol=bot.symbol,
        inputs=bot.input_values or {},
        limits=limits(),
        symbol_info=SymbolInfo.for_symbol(bot.symbol, market=bot.market),
        timeframe=TimeframeInfo.for_interval(interval),
    )
    traced: list[tuple] = []
    for index, bar in enumerate(bars):
        try:
            outcome = runtime.run_bar(bar, ishistory=index < warmup)
        except PineError:
            # A script that fails on a timeframe it was never run on is a fact
            # about that timeframe, not an error worth a 500. Draw what it
            # managed and stop.
            break
        if index >= warmup:
            traced.append((bar.time, outcome.intent.as_dict()["plots"], outcome.intent.as_dict()))
    return traced


def _series_from(rows: list[tuple[int, dict]]) -> list[dict]:
    """Per-bar plot dictionaries → one array per named series, chart-ready.

    Sparse by construction: a bar where a series was ``na`` contributes no
    point, so a line breaks where the script had no value rather than being
    drawn through zero.
    """
    names: list[str] = []
    for _, plots in rows:
        for name in plots or {}:
            if name not in names:
                names.append(name)
    series = []
    for name in names:
        points = []
        for time, plots in rows:
            value = (plots or {}).get(name)
            if value is None or value == "":
                continue
            try:
                points.append({"time": time, "value": float(value)})
            except (TypeError, ValueError):
                continue
        if points:
            series.append({"name": name, "points": points})
    return series


def _markers_from_bars(rows) -> list[dict]:
    """Where the desired side changed. One marker per change, never per bar."""
    markers = []
    previous = None
    for row in rows:
        side = (row.intent or {}).get("side")
        if side != previous:
            markers.append(
                {
                    "time": row.bar_time,
                    "side": side,
                    "kind": "signal",
                    "reason": (row.intent or {}).get("reason") or "",
                }
            )
        previous = side
    return markers


def _markers_from_trace(traced: list[tuple]) -> list[dict]:
    markers = []
    previous = None
    for time, _, intent in traced:
        side = intent.get("side")
        if side != previous:
            markers.append(
                {
                    "time": time,
                    "side": side,
                    "kind": "signal",
                    "reason": intent.get("reason") or "",
                }
            )
        previous = side
    return markers


def _markers_from_actions(run, limit: int) -> list[dict]:
    """What was actually *routed*, as distinct from what was merely wanted.

    Both are drawn, and they are different marks: a signal the risk gate refused
    is a signal with no action beside it, which is exactly the picture an
    operator needs when a bot "did nothing".
    """
    return [
        {
            "time": action.bar_time,
            "side": (action.intent or {}).get("side"),
            "kind": action.action_type,
            "ok": action.ok,
            "reason": action.reason or "",
        }
        for action in run.actions.all()[:limit]
    ]
