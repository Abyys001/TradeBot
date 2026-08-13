"""Trades and per-account legs (spec §8 trade history)."""

from __future__ import annotations

from django.db import models

from apps.accounts.models import ConnectedAccount


class KillSwitch(models.Model):
    """Spec §7: the platform-wide emergency halt, as a row rather than a redeploy.

    ``STOP_ALL=true`` in the environment pins it on and the API cannot turn it
    off — a deployment-level halt must not be clearable from a browser. This row
    is the runtime half: the admin flips it from the panel and new routing stops
    on the next order. Closing and amending open positions keep working, which
    is the point (see ``apps.trading.killswitch``).
    """

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1)
    stop_all = models.BooleanField(default=False)
    reason = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    #: Username, not a FK: this row outlives the account that set it and is read
    #: on the routing path, where a join is pure cost.
    updated_by = models.CharField(max_length=150, blank=True)

    def __str__(self) -> str:
        return f"stop_all={self.stop_all}"


class TradeStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class Trade(models.Model):
    """One admin action, fanned out to many accounts."""

    symbol = models.CharField(max_length=32)
    side = models.CharField(max_length=8)
    market = models.CharField(max_length=10, default="futures")
    leverage = models.PositiveSmallIntegerField(default=1)
    sl_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    tp_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    # The basis in force when this trade was opened (Q5a). Recorded per trade so
    # history stays interpretable if the setting is ever changed.
    sltp_basis = models.CharField(max_length=10, default="price")
    admin_entry_price = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True
    )
    status = models.CharField(max_length=8, choices=TradeStatus.choices, default=TradeStatus.OPEN)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    fanout_ms = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return f"{self.symbol} {self.side} x{self.leverage} ({self.status})"


class TradeLeg(models.Model):
    """One account's participation. Spec §8 wants pair, time and PnL per account."""

    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="legs")
    account = models.ForeignKey(
        ConnectedAccount, on_delete=models.CASCADE, related_name="trade_legs"
    )

    ok = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    dispatch_ms = models.FloatField(null=True, blank=True)

    qty = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    entry_price = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    exit_price = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    margin = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    take_profit = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    # False means the entry filled but SL/TP did not attach (Q5e).
    sltp_attached = models.BooleanField(default=False)
    pnl = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["trade", "account"], name="one_leg_per_account")
        ]

    def __str__(self) -> str:
        return f"{self.account.label}: {self.trade.symbol}"


class ExchangeSymbol(models.Model):
    """One tradeable pair as **the exchange itself lists it**.

    The picker used to be a curated list of ten. It is now whatever the
    connected exchanges say they list, downloaded at connect time by
    ``exchanges.catalogue`` and served by ``/market/symbols/`` — so nothing is
    tradeable until an account is connected: without credentials there is no
    exchange to ask, and inventing a catalogue would be the same lie as
    inventing a price. Tick/step/minimum rules ride along so the ticket can
    size against the real grid without a round trip per keystroke.
    """

    exchange = models.CharField(max_length=20)
    symbol = models.CharField(max_length=32)
    base = models.CharField(max_length=20)
    quote = models.CharField(max_length=20)
    market = models.CharField(max_length=10)
    #: The exchange's own name for it (BTC-USDT-SWAP, XBTUSDTM, BTC_USDT, BTC).
    native_symbol = models.CharField(max_length=48, blank=True)

    price_tick = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    qty_step = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    min_qty = models.DecimalField(max_digits=24, decimal_places=12, null=True, blank=True)
    min_notional = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    max_leverage = models.PositiveIntegerField(default=0)
    #: 24h quote volume, when the exchange publishes it. Ranks the backfill.
    volume_24h = models.DecimalField(max_digits=30, decimal_places=4, null=True, blank=True)

    active = models.BooleanField(default=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["symbol"]
        constraints = [
            models.UniqueConstraint(
                fields=["exchange", "market", "symbol"], name="unique_symbol_per_exchange"
            )
        ]
        indexes = [models.Index(fields=["market", "active", "-volume_24h"])]

    def __str__(self) -> str:
        return f"{self.exchange}:{self.symbol}"


class StoredCandle(models.Model):
    """A downloaded bar. Real exchange data, kept so the chart can look back.

    The live feed answers "what is it now"; a year of history cannot be pulled
    on every chart pan, so it is downloaded once per pair per interval
    (``exchanges.catalogue``) and read from here when the chart pans back or
    the live feed is down. Provenance stays attached (``exchange``) — a stored
    bar is old, never invented, and the payload is labelled ``live: false``.
    """

    exchange = models.CharField(max_length=20)
    symbol = models.CharField(max_length=32)
    market = models.CharField(max_length=10)
    interval = models.CharField(max_length=6)
    #: Bar open time, UNIX seconds — what the chart indexes on.
    open_time = models.BigIntegerField()

    open = models.DecimalField(max_digits=24, decimal_places=8)
    high = models.DecimalField(max_digits=24, decimal_places=8)
    low = models.DecimalField(max_digits=24, decimal_places=8)
    close = models.DecimalField(max_digits=24, decimal_places=8)
    volume = models.DecimalField(max_digits=30, decimal_places=8, default=0)

    class Meta:
        ordering = ["open_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["exchange", "market", "symbol", "interval", "open_time"],
                name="unique_bar_per_series",
            )
        ]
        indexes = [models.Index(fields=["symbol", "interval", "market", "open_time"])]

    def __str__(self) -> str:
        return f"{self.symbol} {self.interval} @{self.open_time}"


class SyncPhase(models.TextChoices):
    SYMBOLS = "symbols", "Downloading pairs"
    CANDLES = "candles", "Downloading history"
    DONE = "done", "Complete"


class SyncStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


class MarketDataSync(models.Model):
    """Progress of the download the accounts page shows as a bar.

    One row per run. It exists because the first connect pulls a year of
    history for the top pairs, which takes minutes to an hour — long enough
    that a silent spinner is indistinguishable from a hang. The accounts page
    polls ``/market/sync/`` and draws it as a bar.
    """

    exchange = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=SyncStatus.choices, default=SyncStatus.PENDING)
    phase = models.CharField(max_length=10, choices=SyncPhase.choices, default=SyncPhase.SYMBOLS)

    symbols_found = models.PositiveIntegerField(default=0)
    #: Units are (pair x interval) series, the thing the bar actually counts.
    series_total = models.PositiveIntegerField(default=0)
    series_done = models.PositiveIntegerField(default=0)
    bars_written = models.PositiveBigIntegerField(default=0)

    detail = models.CharField(max_length=200, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    @property
    def percent(self) -> int:
        """0-100. Pair download is the first tenth; history is the rest."""
        if self.status == SyncStatus.DONE:
            return 100
        if self.phase == SyncPhase.SYMBOLS:
            return 5 if self.status == SyncStatus.RUNNING else 0
        if not self.series_total:
            return 10
        return 10 + int(90 * min(self.series_done, self.series_total) / self.series_total)

    def __str__(self) -> str:
        return f"{self.exchange} {self.status} {self.percent}%"
