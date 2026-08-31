"""Connected accounts (spec §6).

One row per partner account. Credentials are ciphertext at rest (spec §7) and
are only ever decrypted inside an adapter at signing time.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core import crypto
from apps.core.money import ZERO, D


class Exchange(models.TextChoices):
    HYPERLIQUID = "hyperliquid", "Hyperliquid"
    BYBIT = "bybit", "Bybit"
    BINANCE = "binance", "Binance"
    OKX = "okx", "OKX"
    GATEIO = "gateio", "Gate.io"
    KUCOIN = "kucoin", "KuCoin"
    TOOBIT = "toobit", "Toobit"
    LBANK = "lbank", "LBank"
    PAPER = "paper", "Paper (demo)"


class AccountStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    ERROR = "error", "Error"


class ConnectedAccount(models.Model):
    """An isolated connection. Never shares credentials, clients, or limits."""

    label = models.CharField(max_length=80)
    exchange = models.CharField(max_length=20, choices=Exchange.choices)
    status = models.CharField(
        max_length=10, choices=AccountStatus.choices, default=AccountStatus.ACTIVE
    )
    testnet = models.BooleanField(default=False)

    hidden = models.BooleanField(
        default=False,
        db_index=True,
    )

    # --- who may enter a *new* trade on this account -----------------------
    # Two independent switches, not one "trading enabled" flag: an account can
    # take the admin's own manual entries, a bot's, both, or neither. Neither
    # one affects an amend or a close on a trade this account already holds a
    # leg of — `eligible_accounts` resolves those from the leg, not from these
    # fields, so flipping a switch mid-trade never strands a live position.
    #
    # Manual defaults on: every account already trades manually today, and
    # flipping this to opt-in on upgrade would silently pause every one of
    # them. Bot defaults off: a bot fanning out to an account nobody opted in
    # is the one mistake this field exists to prevent.
    manual_trading_enabled = models.BooleanField(default=True)
    bot_trading_enabled = models.BooleanField(default=False)

    # --- credentials, encrypted at rest (spec §7) --------------------------
    api_key_encrypted = models.TextField(blank=True)
    api_secret_encrypted = models.TextField(blank=True)
    # OKX/KuCoin need a passphrase; Hyperliquid stores an agent private key here.
    api_passphrase_encrypted = models.TextField(blank=True)
    # Hyperliquid: the master account address that /info queries must use —
    # querying the agent address returns empty results.
    wallet_address = models.CharField(max_length=64, blank=True)
    # Hyperliquid agent approvals expire (max 180 days) and must be renewed.
    credential_expires_at = models.DateTimeField(null=True, blank=True)

    key_fingerprint = models.CharField(max_length=16, blank=True, editable=False)
    withdrawal_check_passed = models.BooleanField(
        default=False,
        help_text="Spec §7: verified trade-only, no withdrawal rights.",
    )
    withdrawal_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When the spec §7 permission check last ran against the exchange. "
            "Null means never — see clean()."
        ),
    )

    # --- reporting ---------------------------------------------------------
    last_balance = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    last_balance_asset = models.CharField(max_length=12, blank=True)
    last_balance_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    # Equity, not free margin. ``last_balance`` is what the exchange says is
    # *available*, which drops the moment margin is locked into a position —
    # useless for spotting a cash flow. Equity only moves on PnL, fees, funding
    # and money actually entering or leaving, which is what the detector reads
    # (apps/accounts/detection.py).
    last_equity = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)

    # The detector's cursor: the last reading taken while this account held no
    # open leg. Both ends of every comparison are flat, so no unrealised PnL is
    # ever inside the window and a market swing can never read as a deposit.
    # Null means the ledger has not started for this account yet — the first
    # flat reading seeds it and proposes nothing, because "from now on" is the
    # only honest start for a record that has no history behind it.
    ledger_cursor_equity = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True
    )
    ledger_cursor_at = models.DateTimeField(null=True, blank=True)

    # Spec §6: when this account became eligible to join a trade. Set on
    # connect and moved forward on resume, so the panel and the audit trail can
    # answer "since when". It is *not* what enforces the rule — enforcement is
    # leg-based in ``trading.services.eligible_accounts``: an amend or close
    # only reaches accounts already holding a filled leg of that trade, so an
    # account that connected or resumed later has nothing to join. That is the
    # stricter test of the two, and the one with tests behind it.
    eligible_from = models.DateTimeField(auto_now_add=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["exchange", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["exchange", "label"], name="unique_account_label_per_exchange"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_exchange_display()} — {self.label}"

    # --- credential access -------------------------------------------------

    def set_credentials(
        self, *, api_key: str = "", api_secret: str = "", passphrase: str = ""
    ) -> None:
        self.api_key_encrypted = crypto.encrypt(api_key)
        self.api_secret_encrypted = crypto.encrypt(api_secret)
        self.api_passphrase_encrypted = crypto.encrypt(passphrase)
        self.key_fingerprint = crypto.fingerprint(api_key or passphrase)

    @property
    def api_key(self) -> str:
        return crypto.decrypt(self.api_key_encrypted)

    @property
    def api_secret(self) -> str:
        return crypto.decrypt(self.api_secret_encrypted)

    @property
    def api_passphrase(self) -> str:
        return crypto.decrypt(self.api_passphrase_encrypted)

    # --- state -------------------------------------------------------------

    @property
    def is_tradeable(self) -> bool:
        return self.status == AccountStatus.ACTIVE

    @property
    def balance_is_usdt(self) -> bool:
        # Q4: non-USDT accounts are surfaced on the dashboard, not traded.
        return (self.last_balance_asset or "").upper() == "USDT"

    @property
    def credential_days_left(self) -> int | None:
        """Whole days until ``credential_expires_at``; ``None`` when unset."""
        from apps.accounts import credentials

        return credentials.days_left(self)

    @property
    def credential_state(self) -> str:
        """``""`` / ``"expiring"`` / ``"expired"`` — see ``accounts.credentials``.

        Reported, never enforced. An expiring credential still trades, and an
        expired one fails at the exchange through the same path as any other
        failed leg. Nothing here excludes an account from a fan-out.
        """
        from apps.accounts import credentials

        return credentials.state(self)

    def clean(self) -> None:
        """Spec §7: no real account routes orders unchecked.

        The guard is on ``withdrawal_checked_at``, not on
        ``withdrawal_check_passed``. Only Bybit, OKX, Binance and KuCoin publish
        key permissions at all; requiring a *passed* check would make the other
        four exchanges unusable, which is not what §7 asks. What §7 asks is
        that the check is run and a proven-withdrawable key is refused — the
        refusal happens in ``accounts.views.verify_account``, and this makes
        sure no path skips the call and activates an unchecked credential.
        """
        if (
            self.status == AccountStatus.ACTIVE
            and self.exchange != Exchange.PAPER
            and self.withdrawal_checked_at is None
        ):
            raise ValidationError(
                {
                    "withdrawal_checked_at": (
                        "Spec §7: an account cannot be activated before its "
                        "credentials have been checked against the exchange."
                    )
                }
            )


class Notification(models.Model):
    """Spec §4: failed-order notice that stays until the admin dismisses it."""

    account = models.ForeignKey(
        ConnectedAccount, on_delete=models.CASCADE, related_name="notifications", null=True
    )
    message = models.TextField()
    code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_active(self) -> bool:
        return self.dismissed_at is None


class FundMovementType(models.TextChoices):
    DEPOSIT = "deposit", "Deposit"
    WITHDRAWAL = "withdrawal", "Withdrawal"


class FundMovementSource(models.TextChoices):
    MANUAL = "manual", "Recorded by hand"
    DETECTED = "detected", "Accepted from a detection"


class FundMovement(models.Model):
    """One recorded deposit or withdrawal against an account.

    Cash flows are entered by hand — the platform's keys are trade-only (spec
    §7), so no exchange API can tell us who moved money in or out. The account's
    ``last_balance`` stays the exchange's live number; this table is the history
    that turns that number into invested capital and PnL (``apps.accounts.ledger``).

    A row may also arrive from ``DetectedMovement``: the platform notices equity
    moving by more than the closed trades explain, works out that it was a
    transfer rather than the trade (``apps.accounts.classify``) and books it.
    ``created_by`` is blank on those — the platform, not an operator — and the
    decision is reversible from the panel. Either way every change to a row here
    is an entry in ``LedgerEvent``.
    """

    account = models.ForeignKey(
        ConnectedAccount, on_delete=models.CASCADE, related_name="fund_movements"
    )
    kind = models.CharField(max_length=12, choices=FundMovementType.choices)
    source = models.CharField(
        max_length=8,
        choices=FundMovementSource.choices,
        default=FundMovementSource.MANUAL,
        help_text="Typed in by an operator, or accepted from a detection.",
    )
    amount = models.DecimalField(
        max_digits=24,
        decimal_places=8,
        help_text="Always positive; the direction lives in ``kind``.",
    )
    asset = models.CharField(max_length=12, default="USDT")
    #: When the money actually moved. Defaults to now but is backfillable: the
    #: ledger is "record from here on", so entries may be dated in the past.
    occurred_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    #: Usernames, not FKs: these rows outlive the operator accounts that made
    #: them, and the full trail lives in ``LedgerEvent`` either way.
    created_by = models.CharField(max_length=150, blank=True)
    updated_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [models.Index(fields=["account", "occurred_at"])]

    def clean(self) -> None:
        if self.amount is not None and self.amount <= ZERO:
            raise ValidationError({"amount": "amount must be positive"})

    def __str__(self) -> str:
        return f"{self.kind} {self.amount} {self.asset} @ {self.account.label}"


class ProfitSplit(models.Model):
    """The profit split: one global set of percentages for the three roles.

    Applies to profit only — the investor keeps their capital, and each role's
    share of an account's *positive* PnL is ``pnl * pct / 100``. Read via
    ``apps.accounts.ledger.get_split``; the percentages are edited from the
    panel's Settings page. ``singleton=1`` mirrors ``KillSwitch``.
    """

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1)
    investor = models.DecimalField(max_digits=5, decimal_places=2)
    trader = models.DecimalField(max_digits=5, decimal_places=2)
    programmer = models.DecimalField(max_digits=5, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)
    #: Username, not a FK: this row outlives the account that set it.
    updated_by = models.CharField(max_length=150, blank=True)

    def clean(self) -> None:
        if None in (self.investor, self.trader, self.programmer):
            return
        for field in ("investor", "trader", "programmer"):
            value = D(getattr(self, field))
            if value < ZERO or value > Decimal("100"):
                raise ValidationError({field: "must be between 0 and 100"})
        total = D(self.investor) + D(self.trader) + D(self.programmer)
        if total != Decimal("100"):
            raise ValidationError({"investor": "percentages must sum to 100"})

    def __str__(self) -> str:
        return f"split investor={self.investor} trader={self.trader} programmer={self.programmer}"


class LedgerAction(models.TextChoices):
    """Every way the money record can change. One row per change, forever."""

    DETECTED = "detected", "Detected by the platform"
    CREATED = "created", "Recorded by hand"
    EDITED = "edited", "Edited"
    DELETED = "deleted", "Deleted"
    ACCEPTED = "accepted", "Detection accepted"
    DISMISSED = "dismissed", "Detection dismissed"
    ATTRIBUTED = "attributed", "Attributed to trading"
    REOPENED = "reopened", "Decision reopened"
    SPLIT = "split", "Profit split changed"


class LedgerEvent(models.Model):
    """The audit trail: who changed which money record, when, and to what.

    Append-only by convention — nothing in the codebase updates or deletes a
    row here. The account and movement are recorded as *ids plus labels* rather
    than only as foreign keys, because the trail has to stay readable after the
    thing it describes is gone; a deletion is exactly the event worth keeping.
    """

    actor = models.CharField(
        max_length=150,
        blank=True,
        help_text="Username. Blank means the platform itself, not an operator.",
    )
    action = models.CharField(max_length=12, choices=LedgerAction.choices)
    account = models.ForeignKey(
        ConnectedAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_events",
    )
    account_label = models.CharField(max_length=80, blank=True)
    #: Plain integers: the rows they point at may be deleted, and the trail of a
    #: deletion is worthless if it deletes itself with the row.
    movement_id = models.IntegerField(null=True, blank=True)
    detection_id = models.IntegerField(null=True, blank=True)
    kind = models.CharField(max_length=12, blank=True)
    amount = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    #: The changed fields only, as {field: value}. ``before`` is null on a
    #: create, ``after`` is null on a delete.
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["account", "created_at"])]

    def __str__(self) -> str:
        who = self.actor or "platform"
        return f"{who} {self.action} {self.kind} {self.amount} @ {self.account_label}"


class MovementClass(models.TextChoices):
    """What an unexplained balance change actually was.

    The two are not opinions about the same event, they are different
    events: ``TRADE`` means the exchange's number moved because the
    position did, so invested capital is untouched and PnL already carries
    it; ``INVESTOR`` means somebody moved cash, so capital changes and PnL
    must not absorb it. Booking one as the other is a wrong PnL either way.
    """

    TRADE = "trade", "Trade result"
    INVESTOR = "investor", "Investor cash flow"


class DetectionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Booked as a cash flow"
    ATTRIBUTED = "trade", "Attributed to the trade"
    DISMISSED = "dismissed", "Dismissed"


class DetectedMovement(models.Model):
    """A balance change the platform cannot explain with trades.

    Produced by ``apps.accounts.detection``, then answered by
    ``apps.accounts.classify``: was it the trade, or somebody's cash? Nothing
    here reaches ``account_ledger`` until that question is resolved — by the
    classifier where the evidence is clear, by a person where it is not.

    The three numbers are kept side by side on purpose — ``delta`` is what the
    exchange's equity did, ``trade_pnl`` and ``manual_net`` are what the record
    already explains, and ``unexplained`` is the remainder being proposed. An
    operator can check the arithmetic without leaving the row.
    """

    account = models.ForeignKey(
        ConnectedAccount, on_delete=models.CASCADE, related_name="detections"
    )
    previous_equity = models.DecimalField(max_digits=24, decimal_places=8)
    current_equity = models.DecimalField(max_digits=24, decimal_places=8)
    delta = models.DecimalField(max_digits=24, decimal_places=8)
    trade_pnl = models.DecimalField(max_digits=24, decimal_places=8, default=Decimal("0"))
    manual_net = models.DecimalField(max_digits=24, decimal_places=8, default=Decimal("0"))
    #: Signed. Positive proposes a deposit, negative a withdrawal.
    unexplained = models.DecimalField(max_digits=24, decimal_places=8)
    suggested_kind = models.CharField(max_length=12, choices=FundMovementType.choices)
    asset = models.CharField(max_length=12, default="USDT")

    # --- what the platform thinks this was (apps.accounts.classify) --------
    #: Trade result or somebody's cash. ``TRADE`` is the standing default: a
    #: balance that moves on a trading account moved because of the trade
    #: unless something says otherwise.
    suggested_class = models.CharField(
        max_length=10, choices=MovementClass.choices, default=MovementClass.TRADE
    )
    #: Which rule decided it, as a code the panel translates. Kept rather than
    #: a sentence so the reasoning survives a language change and can be
    #: grepped when a verdict looks wrong.
    classification_reason = models.CharField(max_length=32, blank=True)
    #: Whether the rule that fired is one the platform may act on by itself.
    #: A low-confidence verdict is still shown and still pre-selected; it just
    #: waits for a person under the default ``LEDGER_AUTO_RESOLVE=safe``.
    confident = models.BooleanField(default=False)
    #: The isolation evidence, kept as the counts it was decided from: how many
    #: *other* accounts were readable and flat in the same sweep, and how many
    #: of those moved the same way. One account moving while its peers did not
    #: is the signature of an investor transfer; a fan-out moves all of them.
    peers_observed = models.PositiveSmallIntegerField(default=0)
    peers_moved = models.PositiveSmallIntegerField(default=0)
    #: Did this account have any trade activity near the window at all. No
    #: trade means nothing but a transfer can have moved the number.
    traded_in_window = models.BooleanField(default=False)
    #: Resolved by the classifier rather than by a person. The row still shows
    #: up in the panel, and the decision can be reopened.
    auto_resolved = models.BooleanField(default=False)

    #: The window the comparison covers: the last reading the account was flat
    #: at, to this one. Both ends flat, so no unrealised PnL is inside it.
    window_start = models.DateTimeField(null=True, blank=True)
    observed_at = models.DateTimeField(default=timezone.now)

    status = models.CharField(
        max_length=10, choices=DetectionStatus.choices, default=DetectionStatus.PENDING
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=150, blank=True)
    movement = models.ForeignKey(
        FundMovement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detections",
    )

    class Meta:
        ordering = ["-observed_at", "-id"]
        indexes = [models.Index(fields=["status", "observed_at"])]

    @property
    def amount(self) -> Decimal:
        """The proposal as a positive number; the direction is ``suggested_kind``."""
        return abs(D(self.unexplained))

    @property
    def is_pending(self) -> bool:
        return self.status == DetectionStatus.PENDING

    def __str__(self) -> str:
        return f"{self.suggested_kind} {self.amount} @ {self.account_id} ({self.status})"


class PanelSession(models.Model):
    """Who is on the panel right now, one row per browser session.

    Everyone signs in as the same staff user, so "who is logged in" cannot be
    answered from the user table — it is a question about sessions. This is the
    per-session half: when that browser signed in, when it was last seen, from
    where, and on what.

    The session key itself is **never stored**: it is the cookie, and a table of
    live cookies is a table of ready-made logins. Only its SHA-256 is kept,
    which is enough to match a request to its row and useless to anyone reading
    the database.
    """

    #: sha256 of the Django session key — never the key itself.
    session_hash = models.CharField(max_length=64, unique=True, editable=False)
    #: Snapshot, not a join: the name typed at the login prompt stays readable
    #: after the user row is renamed or deleted.
    username = models.CharField(max_length=150)
    user = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="panel_sessions"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self) -> str:
        return f"{self.username} @ {self.ip_address or '?'}"

    @staticmethod
    def hash_key(session_key: str) -> str:
        return hashlib.sha256(session_key.encode()).hexdigest()

    @property
    def is_active(self) -> bool:
        return self.ended_at is None
