from django.conf import settings
from django.db import models

from .crypto import decrypt, encrypt


class Exchange(models.TextChoices):
    HYPERLIQUID = "hyperliquid", "Hyperliquid"


class Network(models.TextChoices):
    MAINNET = "mainnet", "Mainnet"
    TESTNET = "testnet", "Testnet"


class ExchangeCredential(models.Model):
    """Encrypted Hyperliquid agent credentials.

    Stores only the Agent private key (never the master wallet key).
    The master `wallet_address` is used for PnL monitoring and as
    `account_address` when signing trades on behalf of the account.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credentials",
    )
    exchange = models.CharField(
        max_length=16,
        choices=Exchange.choices,
        default=Exchange.HYPERLIQUID,
    )
    label = models.CharField(max_length=64, help_text="Human-friendly name.")
    wallet_address = models.CharField(
        max_length=42,
        help_text="Master wallet address (read-only monitoring; not stored encrypted).",
    )
    agent_private_key_enc = models.BinaryField()
    agent_address = models.CharField(
        max_length=42,
        blank=True,
        default="",
        help_text="Derived agent wallet address (set on verify).",
    )
    network = models.CharField(
        max_length=16,
        choices=Network.choices,
        default=Network.TESTNET,
    )
    permissions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Agent metadata reported on verify.",
    )
    is_active = models.BooleanField(default=False)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "exchange", "label"],
                name="uniq_user_exchange_label",
            )
        ]

    def __str__(self):
        return f"{self.user} · {self.exchange} · {self.label}"

    def set_agent_key(self, private_key_hex: str) -> None:
        """Encrypt and store agent private key. Does not save()."""
        key = private_key_hex.strip()
        if key.startswith("0x"):
            key = key[2:]
        self.agent_private_key_enc = encrypt(key)

    def get_agent_key(self) -> str:
        """Decrypt agent key into memory. Never log or serialize the result."""
        key = decrypt(self.agent_private_key_enc)
        if not key.startswith("0x"):
            key = "0x" + key
        return key
