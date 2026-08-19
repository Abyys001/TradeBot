"""Connected accounts (spec §6).

One row per partner account. Credentials are ciphertext at rest (spec §7) and
are only ever decrypted inside an adapter at signing time.
"""

from __future__ import annotations

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


class FundMovement(models.Model):
    """One recorded deposit or withdrawal against an account.

    Cash flows are entered by hand — the platform's keys are trade-only (spec
    §7), so no exchange API can tell us who moved money in or out. The account's
    ``last_balance`` stays the exchange's live number; this table is the history
    that turns that number into invested capital and PnL (``apps.accounts.ledger``).
    """

    account = models.ForeignKey(
        ConnectedAccount, on_delete=models.CASCADE, related_name="fund_movements"
    )
    kind = models.CharField(max_length=12, choices=FundMovementType.choices)
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
