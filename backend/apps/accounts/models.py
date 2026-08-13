"""Connected accounts (spec §6).

One row per partner account. Credentials are ciphertext at rest (spec §7) and
are only ever decrypted inside an adapter at signing time.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.core import crypto


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

    # Spec §6: a newly connected account joins from the *next* trade, never an
    # open one. Set when connected/resumed; the engine filters on it.
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
        ``withdrawal_check_passed``. Only Bybit, OKX and Binance publish key
        permissions at all; requiring a *passed* check would make the other
        five exchanges unusable, which is not what §7 asks. What §7 asks is
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
