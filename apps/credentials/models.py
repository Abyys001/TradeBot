from django.conf import settings
from django.db import models

from .crypto import decrypt, encrypt


class Exchange(models.TextChoices):
    HYPERLIQUID = "hyperliquid", "Hyperliquid"
    TABDEAL = "tabdeal", "Tabdeal"


class Network(models.TextChoices):
    MAINNET = "mainnet", "Mainnet"
    TESTNET = "testnet", "Testnet"


class ExchangeCredential(models.Model):
    """Encrypted exchange trading credentials.

    Hyperliquid: stores only the Agent private key (never the master wallet
    key); `wallet_address` is the master account for PnL monitoring and signing.
    Tabdeal (Binance-style): stores an API key + HMAC secret (encrypted); the
    Hyperliquid-specific fields are left blank.
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
    # --- Hyperliquid fields (blank for other exchanges) ---
    wallet_address = models.CharField(
        max_length=42,
        blank=True,
        default="",
        help_text="Master wallet address (read-only monitoring; not stored encrypted). Hyperliquid only.",
    )
    agent_private_key_enc = models.BinaryField(
        blank=True, default=b"", help_text="Hyperliquid agent private key. Empty for other exchanges."
    )
    # --- Tabdeal / API-key fields (blank for Hyperliquid) ---
    api_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Public API key (Tabdeal and other Binance-style exchanges).",
    )
    api_key_enc = models.BinaryField(
        blank=True, default=b"", help_text="Encrypted REST API key (e.g. Tabdeal). Empty for Hyperliquid."
    )
    api_secret_enc = models.BinaryField(
        blank=True, default=b"", help_text="Encrypted REST API secret (e.g. Tabdeal). Empty for Hyperliquid."
    )
    # --- Independent watchdog key (§1.3). Blank -> the watchdog falls back to the
    # primary key. A separate, independently-revocable key is the spec-ideal. ---
    watchdog_api_key_enc = models.BinaryField(
        blank=True, default=b"", help_text="Encrypted watchdog REST API key. Blank -> reuse primary."
    )
    watchdog_api_secret_enc = models.BinaryField(
        blank=True, default=b"", help_text="Encrypted watchdog REST API secret. Blank -> reuse primary."
    )
    # --- Empirical probe results (§4), written by the diagnostics endpoint. ---
    probe_results = models.JSONField(
        default=dict,
        blank=True,
        help_text="Results of the last exchange-behaviour diagnostics run (§4).",
    )
    probed_at = models.DateTimeField(null=True, blank=True)
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

    def set_api_secret(self, secret: str) -> None:
        """Encrypt and store an HMAC API secret (Tabdeal). Does not save()."""
        self.api_secret_enc = encrypt(secret.strip())

    def set_api_credentials(self, api_key: str, api_secret: str) -> None:
        """Encrypt and store a REST API key/secret pair. Does not save()."""
        self.api_key = api_key.strip()
        self.api_key_enc = encrypt(api_key.strip())
        self.api_secret_enc = encrypt(api_secret.strip())

    def get_api_key(self) -> str:
        """Decrypt API key into memory. Never log or serialize the result."""
        return decrypt(bytes(self.api_key_enc))

    def get_api_secret(self) -> str:
        """Decrypt API secret into memory. Never log or serialize the result."""
        return decrypt(bytes(self.api_secret_enc))

    def set_watchdog_api_credentials(self, api_key: str, api_secret: str) -> None:
        """Encrypt and store the independent watchdog key pair. Does not save()."""
        self.watchdog_api_key_enc = encrypt(api_key.strip()) if api_key else b""
        self.watchdog_api_secret_enc = encrypt(api_secret.strip()) if api_secret else b""

    @property
    def has_watchdog_key(self) -> bool:
        return bool(self.watchdog_api_key_enc and self.watchdog_api_secret_enc)

    def get_watchdog_api_key(self) -> str:
        """Watchdog key, falling back to the primary key when none is set."""
        if self.watchdog_api_key_enc:
            return decrypt(bytes(self.watchdog_api_key_enc))
        return self.get_api_key()

    def get_watchdog_api_secret(self) -> str:
        """Watchdog secret, falling back to the primary secret when none is set."""
        if self.watchdog_api_secret_enc:
            return decrypt(bytes(self.watchdog_api_secret_enc))
        return self.get_api_secret()
