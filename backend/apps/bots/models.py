"""What a bot is, what it did, and what it decided — persisted.

Retention follows Q26, and the split is deliberate:

  **``BotAction`` and the intent that produced it are kept forever.** That is
  the audit trail — what the bot decided, when, why, and which legs came back —
  and it is small. Nothing about accountability depends on the bars.

  **``BotBar`` is the volume** (1,440 rows a day per bot at 1m) and is trimmed:
  everything at 15m and above, and at 1m/5m only the bars where a signal or a
  plot value changed, plus a rolling seven-day window for debugging.

``BotAction.idempotency_key`` is ``UNIQUE`` at the database level rather than
checked in application code, because the case it defends against is a **restart
in the middle of a fan-out** — and at that moment there is no application logic
running to do the checking.
"""

from __future__ import annotations

from django.db import models


class BotState(models.TextChoices):
    """The lifecycle, as a real state machine (``lifecycle.py`` holds the edges).

    ``stopped → live`` is deliberately not a transition. A bot that stopped
    itself is restarted by a person who has read why, and the way back to real
    money runs through paper.
    """

    DRAFT = "draft"
    PAPER = "paper"
    LIVE = "live"
    STOPPED = "stopped"


class StopReason(models.TextChoices):
    """Q25's seven triggers, plus the two a person causes.

    Every one is auto-stop, never auto-pause-and-resume: a bot that stopped
    itself is restarted by a person who has read why.
    """

    CONSECUTIVE_LOSSES = "consecutive_losses"
    DRAWDOWN = "drawdown"
    FEED_GAP = "feed_gap"
    SCRIPT_ERROR = "script_error"
    STATE_DISAGREEMENT = "state_disagreement"
    TRADE_RATE = "trade_rate"
    NO_BARS = "no_bars"
    #: Not a Q25 trigger. Q22's most important line: a halt that flattens
    #: positions while a bot is still evaluating is a halt that re-enters ninety
    #: seconds later, which is not a halt.
    HALT = "halt"
    MANUAL = "manual"
    RISK_GATE = "risk_gate"


class ActionType(models.TextChoices):
    OPEN = "open"
    AMEND = "amend"
    CLOSE = "close"
    #: A scale-out: take a share off and keep the rest running (Q33). Distinct
    #: from CLOSE because the trade stays open and the idempotency key is keyed
    #: on the type — a TP1 and a stop on the same bar must not collide.
    REDUCE = "reduce"
    #: Recorded, routed nowhere — a dry-run bot's would-have-been (Phase 7).
    SHADOW = "shadow"


class Strategy(models.Model):
    """A named script. Its *versions* hold the source; this holds the identity."""

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "strategies"

    def __str__(self) -> str:
        return self.name


class StrategyVersion(models.Model):
    """**Immutable.** Editing a strategy makes a new version, never an edit.

    A running bot points at a version, so a bot's behaviour cannot change under
    it because somebody saved in another tab. It is also what makes a backtest
    reproducible: the report names the version, and that version's source is
    still exactly what produced it.
    """

    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    source = models.TextField()
    parsed_ok = models.BooleanField(default=False)
    validation_errors = models.JSONField(default=list, blank=True)
    validation_warnings = models.JSONField(default=list, blank=True)
    inputs_schema = models.JSONField(default=list, blank=True)
    #: TradingView's Properties tab as ``strategy()`` declared it, resolved over
    #: the platform's defaults, plus the two lists that say which of them the
    #: bot will not honour. Stored with the version rather than recomputed,
    #: because the version is immutable and this is part of what it *is* — a
    #: report from three weeks ago has to be readable against the properties it
    #: was produced with, not against whatever the parser says today.
    properties = models.JSONField(default=dict, blank=True)
    property_notes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["strategy", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["strategy", "version"], name="bots_version_unique_per_strategy"
            )
        ]

    def __str__(self) -> str:
        return f"{self.strategy.name} v{self.version}"


class Bot(models.Model):
    """One strategy version, on one symbol and timeframe, with its own settings.

    ``leverage``, ``sl_pct`` and ``tp_pct`` sit here and not in the script (Q21)
    — exactly as the order ticket carries them, and identical across accounts
    like every other trade (§5). A percent ``strategy.exit`` in the script wins
    for that trade only.
    """

    strategy_version = models.ForeignKey(
        StrategyVersion, on_delete=models.PROTECT, related_name="bots"
    )
    name = models.CharField(max_length=120)
    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=6, default="1h")
    market = models.CharField(max_length=10, default="futures")

    leverage = models.PositiveSmallIntegerField(default=1)
    sl_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    tp_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    input_values = models.JSONField(default=dict, blank=True)
    #: Per-bot overrides of the Q25 defaults in ``settings.BOT``. Phase 10
    #: requires these be set deliberately rather than left empty.
    risk_config = models.JSONField(default=dict, blank=True)
    #: TradingView's Properties tab, as *this bot* overrides it — the third and
    #: last step of ``properties.resolve`` (platform → script → panel).
    #:
    #: On the bot rather than on the version because a version is immutable and
    #: shared: two bots may run the same script against different simulated
    #: capital, and pinning the numbers to the version would make one of them
    #: rewrite the other's backtest. Only the keys actually overridden are
    #: stored, so a script that later declares one of these still wins over the
    #: platform default without the panel having to be re-saved.
    #:
    #: Backtest-facing only. Nothing in the live path reads it — spec §5 sizes
    #: from each account's real balance, and ``live_departures()`` is what says
    #: so on screen.
    property_overrides = models.JSONField(default=dict, blank=True)

    state = models.CharField(max_length=10, choices=BotState.choices, default=BotState.DRAFT)
    #: Phase 7's shadow mode: evaluate, log what would have happened, route
    #: nothing. One branch in the risk gate, and it is the only evidence that
    #: any of this works before it touches capital.
    dry_run = models.BooleanField(default=True)

    #: Which Q25 triggers have been fired deliberately in a drill. The Phase 7
    #: gate requires all seven, and it reads this rather than trusting a memory.
    drills_fired = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["state"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.symbol} {self.interval})"

    @property
    def is_running(self) -> bool:
        return self.state in (BotState.PAPER, BotState.LIVE)


class BotRun(models.Model):
    """One continuous session of a bot.

    A run **survives a process restart** — the supervisor recovers into the same
    run and increments ``recoveries``. That is what lets the Phase 7 gate ask
    for "14 days continuous" and "≥3 restarts survived" from the same row; a new
    run per process start would make the first requirement unmeetable by
    construction.
    """

    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="runs")
    started_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    stop_reason = models.CharField(
        max_length=24, choices=StopReason.choices, blank=True, default=""
    )
    stop_detail = models.TextField(blank=True)

    warmup_bars = models.PositiveIntegerField(default=0)
    #: "stream" or "poll" — the bot knows which it is on and says so (Phase 3).
    feed_source = models.CharField(max_length=12, blank=True)
    last_bar_time = models.BigIntegerField(null=True, blank=True)

    peak_equity = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    consecutive_losses = models.PositiveIntegerField(default=0)

    # --- the Phase 7 gate's measurements, recorded rather than remembered ---
    recoveries = models.PositiveIntegerField(default=0)
    unplanned_recoveries = models.PositiveIntegerField(default=0)
    feed_gaps = models.PositiveIntegerField(default=0)
    feed_gaps_repaired = models.PositiveIntegerField(default=0)
    halt_drills = models.PositiveIntegerField(default=0)
    divergences = models.PositiveIntegerField(default=0)
    bars_evaluated = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["bot", "-started_at"])]

    def __str__(self) -> str:
        return f"run {self.id} of {self.bot_id}"

    @property
    def is_open(self) -> bool:
        return self.stopped_at is None


class BotBar(models.Model):
    """One evaluated bar. Trimmed per Q26 — see ``retention.py``."""

    run = models.ForeignKey(BotRun, on_delete=models.CASCADE, related_name="bars")
    bar_time = models.BigIntegerField()
    open = models.DecimalField(max_digits=24, decimal_places=8)
    high = models.DecimalField(max_digits=24, decimal_places=8)
    low = models.DecimalField(max_digits=24, decimal_places=8)
    close = models.DecimalField(max_digits=24, decimal_places=8)
    volume = models.DecimalField(max_digits=30, decimal_places=8, default=0)
    plots = models.JSONField(default=dict, blank=True)
    intent = models.JSONField(default=dict, blank=True)
    evaluation_ms = models.FloatField(null=True, blank=True)
    #: True when this bar's signal or a plot value differs from the one before
    #: it. Q26 keeps these at 1m and 5m and trims the rest.
    changed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-bar_time"]
        constraints = [
            models.UniqueConstraint(fields=["run", "bar_time"], name="bots_bar_unique_per_run")
        ]
        indexes = [models.Index(fields=["run", "-bar_time"])]


class BotAction(models.Model):
    """Something the bot asked the platform to do. **Kept forever** (Q26).

    ``idempotency_key`` is written *before* dispatch and is ``UNIQUE``. That is
    the only thing standing between a restart mid-fan-out and a double entry:
    on recovery the row already exists, the insert fails, and the action is
    reconciled instead of re-sent.
    """

    run = models.ForeignKey(BotRun, on_delete=models.CASCADE, related_name="actions")
    bar_time = models.BigIntegerField()
    action_type = models.CharField(max_length=8, choices=ActionType.choices)
    idempotency_key = models.CharField(max_length=120, unique=True)

    intent = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    trade = models.ForeignKey(
        "trading.Trade",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_actions",
    )
    ok = models.BooleanField(default=False)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["run", "-bar_time"]),
            models.Index(fields=["run", "settled_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action_type} @ {self.bar_time}"

    @property
    def unsettled(self) -> bool:
        """Dispatched, and its outcome never written back.

        This is the shape a restart mid-fan-out leaves behind, and the one
        ``recovery.py`` reconciles through ``confirm_open`` before the bot is
        allowed to do anything else.
        """
        return self.dispatched_at is not None and self.settled_at is None


class BacktestRun(models.Model):
    """A stored backtest report.

    Not in ``bot-mode.md`` §6.1's list, and here anyway for two reasons: the
    panel needs somewhere to read a report from, and Phase 10 gates going live
    on "a backtest over ≥ 2 years or ≥ 500 trades" — a requirement nobody can
    check against a number that was printed to a terminal once.
    """

    strategy_version = models.ForeignKey(
        StrategyVersion, on_delete=models.CASCADE, related_name="backtests"
    )
    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=6)
    market = models.CharField(max_length=10, default="futures")
    from_time = models.BigIntegerField()
    to_time = models.BigIntegerField()
    input_values = models.JSONField(default=dict, blank=True)

    bars = models.PositiveIntegerField(default=0)
    trades = models.PositiveIntegerField(default=0)
    metrics = models.JSONField(default=dict, blank=True)
    #: The fill assumptions this report was produced under. Stored with it, not
    #: re-derived at read time: a settings change must not silently restate what
    #: an old report meant.
    assumptions = models.JSONField(default=dict, blank=True)
    equity_curve = models.JSONField(default=list, blank=True)
    trade_log = models.JSONField(default=list, blank=True)
    intent_digest = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"backtest {self.symbol} {self.interval} ({self.trades} trades)"
