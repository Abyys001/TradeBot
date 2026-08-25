"""The bot's own halt (Q25), on top of the platform-wide one.

The two answer different questions. The §7 kill switch answers "the admin wants
everything stopped". This answers **"nobody is awake and this bot is behaving in
a way that means something is wrong"** — which is the whole premise of removing
the human from the loop: a bug does not cost one bad trade, it costs one bad
trade per bar, forever, at 99% of every partner's balance.

Every trigger is **auto-stop, never auto-pause-and-resume.** A bot that stopped
itself is restarted by a person who has read why. Two of the seven are not
numbers and are not configurable — an unrepairable feed gap and a runtime error
in the script are both "any, the first one", because a setting there would be a
setting for how much silent disagreement with the market is acceptable.

The halt is the exception that is *not* a stop: under ``killswitch.is_on()`` the
bot **pauses**, it does not error. Stopping every bot when the admin pulls the
switch is Q22's job and it happens in ``killswitch.set_stop_all`` — not here,
where it would fire on every bar of a halt somebody meant to be temporary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from apps.bots.models import Bot, BotAction, BotRun, StopReason
from apps.bots.translate import Action

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class Decision:
    """What the gate says about one action."""

    allowed: bool
    #: True when the bot must stop, not merely skip this action.
    stop: bool = False
    reason: str = ""
    code: str = ""

    @property
    def paused(self) -> bool:
        return not self.allowed and not self.stop


ALLOW = Decision(allowed=True)


def limit_for(bot: Bot, key: str):
    """A per-bot override, or the ``settings.BOT`` default.

    Phase 10 requires these be set deliberately for a strategy rather than left
    at the defaults, which is why ``risk_config`` is per bot and why the
    promotion gate can tell whether it was filled in.
    """
    if key in (bot.risk_config or {}):
        return bot.risk_config[key]
    return settings.BOT[key]


class RiskGate:
    """Sits between the translator and ``services.*``. Everything passes through."""

    def __init__(self, bot: Bot, run: BotRun) -> None:
        self.bot = bot
        self.run = run

    # --- per-bar checks, before the script even sees the bar ----------------

    async def before_bar(self, *, bar_time: int) -> Decision:
        halted = await sync_to_async(_halted)()
        if halted:
            # Pause, do not error and do not stop. The bot resumes when the halt
            # clears — unless Q22's wiring already stopped it, which is the case
            # whenever the halt came from the panel or from close-all.
            return Decision(
                allowed=False, reason="platform halt is on (spec §7)", code="halt"
            )

        window = (self.bot.risk_config or {}).get("trading_window")
        if window and not _inside_window(window, bar_time):
            return Decision(
                allowed=False,
                reason=f"outside this bot's trading window {window}",
                code="outside_window",
            )
        return ALLOW

    # --- the Q25 triggers ---------------------------------------------------

    async def check_triggers(self, *, now=None) -> Decision:
        """The four countable triggers. Feed gaps and script errors arrive as
        exceptions and stop the bot at their raise site; state disagreement is
        checked by ``recovery`` after its second pass."""
        run = self.run
        moment = now or timezone.now()

        cap = int(limit_for(self.bot, "MAX_CONSECUTIVE_LOSSES"))
        if cap and run.consecutive_losses >= cap:
            return Decision(
                allowed=False,
                stop=True,
                reason=f"{run.consecutive_losses} losing trades in a row (limit {cap})",
                code=StopReason.CONSECUTIVE_LOSSES,
            )

        drawdown_cap = Decimal(str(limit_for(self.bot, "MAX_DRAWDOWN_PCT")))
        drawdown = await self._drawdown_pct()
        if drawdown_cap > ZERO and drawdown is not None and drawdown >= drawdown_cap:
            return Decision(
                allowed=False,
                stop=True,
                reason=f"down {drawdown:.2f}% from this bot's own peak (limit {drawdown_cap}%)",
                code=StopReason.DRAWDOWN,
            )

        rate_cap = int(limit_for(self.bot, "MAX_TRADES_PER_HOUR"))
        if rate_cap:
            recent = await sync_to_async(_actions_since)(run, moment - timedelta(hours=1))
            if recent > rate_cap:
                return Decision(
                    allowed=False,
                    stop=True,
                    reason=f"{recent} trades in the last hour (limit {rate_cap})",
                    code=StopReason.TRADE_RATE,
                )

        stale = await self._no_bars_for(moment)
        if stale is not None:
            return stale

        return ALLOW

    async def _drawdown_pct(self) -> Decimal | None:
        equity = await sync_to_async(_run_equity)(self.run)
        if equity is None:
            return None
        peak = self.run.peak_equity
        if peak is None or peak <= ZERO:
            return ZERO
        return (peak - equity) / peak * HUNDRED

    async def _no_bars_for(self, moment) -> Decision | None:
        """A feed that has gone quiet is not a feed that is working slowly.

        Measured from the last bar the bot *evaluated*, not from the last poll:
        a poll that keeps returning the same stale bar looks healthy from the
        socket's side and is exactly the silence this catches.
        """
        multiple = int(limit_for(self.bot, "NO_BAR_TIMEOUT_MULTIPLE"))
        if not multiple or self.run.last_bar_time is None:
            return None
        from apps.bots.feed import interval_seconds

        step = interval_seconds(self.bot.interval)
        deadline = self.run.last_bar_time + step * (multiple + 1)
        if moment.timestamp() > deadline:
            return Decision(
                allowed=False,
                stop=True,
                reason=(
                    f"no confirmed bar for more than {multiple}× the {self.bot.interval} "
                    f"timeframe — the last one was at {self.run.last_bar_time}"
                ),
                code=StopReason.NO_BARS,
            )
        return None

    # --- per-action checks --------------------------------------------------

    async def check_action(self, action: Action, *, bar_close: Decimal) -> Decision:
        """Everything that depends on *what* is about to be sent."""
        if action.type != "open":
            # An amend or a close reduces or protects exposure. Refusing one on
            # a price check would leave a position unprotected to defend against
            # a stale feed, which is the wrong trade of the two.
            return ALLOW

        drift = await self._price_drift(bar_close)
        cap = Decimal(str(settings.BOT["MAX_PRICE_DRIFT_PCT"]))
        if drift is not None and cap > ZERO and drift > cap:
            return Decision(
                allowed=False,
                stop=True,
                reason=(
                    f"the bar's close is {drift:.2f}% from the live ticker (limit {cap}%) "
                    f"— that is a stale feed or a mis-mapped symbol, not a market move"
                ),
                code=StopReason.RISK_GATE,
            )

        cap_accounts = int(settings.BOT["MAX_ACCOUNTS"])
        if cap_accounts:
            from apps.trading.services import eligible_accounts

            eligible = len(await eligible_accounts())
            if eligible > cap_accounts:
                return Decision(
                    allowed=False,
                    stop=True,
                    reason=(
                        f"{eligible} accounts are eligible and BOT_MAX_ACCOUNTS is "
                        f"{cap_accounts} — the canary cap is set, so this bot must not "
                        f"fan out wider"
                    ),
                    code=StopReason.RISK_GATE,
                )

        max_notional = (self.bot.risk_config or {}).get("max_notional")
        if max_notional:
            notional = await sync_to_async(_planned_notional)(self.bot)
            if notional > Decimal(str(max_notional)):
                return Decision(
                    allowed=False,
                    stop=True,
                    reason=(
                        f"this entry would commit {notional:.2f} USDT across all accounts, "
                        f"over this bot's {max_notional} cap"
                    ),
                    code=StopReason.RISK_GATE,
                )
        return ALLOW

    async def _price_drift(self, bar_close: Decimal) -> Decimal | None:
        """The bar's close against the live ticker, as a percentage.

        Catches two different faults with one number: a feed that has stopped
        moving, and a symbol that maps to a different instrument on the venue
        than on the data source. Both look like a perfectly ordinary signal.
        """
        if bar_close is None or bar_close <= ZERO:
            return None
        price = await sync_to_async(_ticker_price)(self.bot.symbol, self.bot.market)
        if price is None or price <= ZERO:
            return None
        return abs(price - bar_close) / bar_close * HUNDRED


# --- the reads, off the event loop ------------------------------------------


def _halted() -> bool:
    from apps.trading import killswitch

    # Reused, never re-read: there is exactly one path to the halt.
    return killswitch.is_on()


def _actions_since(run: BotRun, moment) -> int:
    return BotAction.objects.filter(
        run=run, action_type="open", dispatched_at__gte=moment
    ).count()


def _run_equity(run: BotRun) -> Decimal | None:
    """Total equity across the accounts this bot's trades touched.

    Deliberately *not* filtered by ``accounts.visibility`` — Q27 puts that on
    read surfaces, and a drawdown limit that ignored a hidden account would be a
    risk limit measuring the wrong book.
    """
    from apps.accounts.models import AccountStatus, ConnectedAccount

    rows = ConnectedAccount.objects.filter(status=AccountStatus.ACTIVE).values_list(
        "last_balance", flat=True
    )
    values = [Decimal(str(v)) for v in rows if v is not None]
    return sum(values, ZERO) if values else None


def _planned_notional(bot: Bot) -> Decimal:
    """What an entry would commit across every eligible account, at spec §5 sizing."""
    from apps.accounts.models import AccountStatus, ConnectedAccount

    fraction = Decimal(str(settings.TRADING["BALANCE_FRACTION"]))
    total = ZERO
    for balance in ConnectedAccount.objects.filter(status=AccountStatus.ACTIVE).values_list(
        "last_balance", flat=True
    ):
        if balance is None:
            continue
        total += Decimal(str(balance)) * fraction * Decimal(bot.leverage)
    return total


def _ticker_price(symbol: str, market: str) -> Decimal | None:
    from apps.exchanges.base import MarketType
    from apps.exchanges.marketdata import get_ticker

    try:
        payload = get_ticker(symbol=symbol, market=MarketType(market))
    except Exception:  # noqa: BLE001 - no ticker is not a drift, it is no reading
        return None
    price = payload.get("price")
    return Decimal(str(price)) if price is not None else None


def _inside_window(window: dict, bar_time: int) -> bool:
    """An optional per-bot UTC window: ``{"days": [1..7], "from": "08:00", "to": "16:00"}``.

    UTC because everything internal is; the panel renders local time. A window
    interpreted in the host's timezone would move when the VPS did.
    """
    from datetime import UTC, datetime

    moment = datetime.fromtimestamp(bar_time, tz=UTC)
    days = window.get("days")
    if days and moment.isoweekday() not in days:
        return False
    start, end = window.get("from"), window.get("to")
    if not start or not end:
        return True
    current = moment.strftime("%H:%M")
    if start <= end:
        return start <= current < end
    # A window that wraps midnight.
    return current >= start or current < end
