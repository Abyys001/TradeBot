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
from django.db.models import ProtectedError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.visibility import _filtered  # read surface only — see apps/bots/__init__.py
from apps.bots import gate, lifecycle
from apps.bots.config import limits
from apps.bots.models import (
    BacktestRun,
    Bot,
    BotAction,
    BotState,
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
            inputs_schema=[i.as_dict() for i in result.inputs],
            properties=result.properties.as_dict(),
            property_notes={
                "live_departures": result.properties.live_departures(),
                "inert": result.properties.inert_here(),
            },
            created_by=request.user.get_username(),
        )
        return Response(StrategyVersionSerializer(version).data, status=201)


class BotViewSet(viewsets.ModelViewSet):
    queryset = Bot.objects.select_related("strategy_version__strategy").prefetch_related("runs")
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
        """The action log, with fan-out legs. The one bot surface naming accounts."""
        bot = self.get_object()
        run = bot.runs.order_by("-started_at").first()
        if run is None:
            return Response([])
        rows = BotAction.objects.filter(run=run).select_related("trade")[:200]
        return Response(
            BotActionSerializer(
                rows, many=True, context={"hidden_ids": _filtered(request.user)}
            ).data
        )

    @action(detail=True, methods=["get"])
    def promotion(self, request: Request, pk=None) -> Response:
        """The Phase 7 gate with this bot's own measurements filled in."""
        return Response(gate.evaluate(self.get_object()))

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


#: How many stored runs the history endpoint will hand back at once.
HISTORY_LIMIT = 200


class BacktestViewSet(viewsets.ReadOnlyModelViewSet):
    """Every backtest ever run, newest first.

    Stored rather than recomputed: a replay costs seconds and a download, and
    the number an operator acted on last week has to still be the number they
    saw. ``?strategy_version=`` narrows it to one version's own history.
    """

    queryset = BacktestRun.objects.select_related("strategy_version__strategy").order_by(
        "-created_at"
    )
    permission_classes = [IsAdminUser]

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
    """Replay a version over stored history and store the report.

    Async because a long replay would otherwise hold a worker thread, and
    because the same endpoint may need to reach the public feed when the archive
    does not cover the window.
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

    user = await request.auser()
    stored = await sync_to_async(_store_backtest)(version, report, payload, user.get_username())
    return JsonResponse({"backtest_id": stored.id, **report.as_dict()})


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


def _store_backtest(version, report, payload, actor: str) -> BacktestRun:
    data = report.as_dict()
    return BacktestRun.objects.create(
        strategy_version=version,
        symbol=report.symbol,
        interval=report.interval,
        market=payload.get("market", "futures"),
        from_time=report.from_time,
        to_time=report.to_time,
        input_values=payload.get("inputs") or {},
        bars=report.bars,
        trades=len(report.trades),
        metrics=data["metrics"],
        # The sentences travel with the numbers. Reopening a stored run has to
        # show the same header the run was read under, and `lines()` is derived
        # from wording that will be edited — a row rebuilt from today's code
        # would caption last month's report with this month's assumptions.
        assumptions={**data["assumptions"], "lines": report.assumptions.lines()},
        equity_curve=data["equity_curve"],
        trade_log=data["trades"],
        intent_digest=report.intent_digest,
        created_by=actor,
    )
