"""Who may send signals, and what every one of them did.

Two tables, and the split is the same one ``apps.bots.models`` makes: the
**source** is configuration and the **event** is the audit trail. The event log
is the part that matters after something goes wrong, so it records the rejected
signals too — an endpoint that only logs what it acted on cannot tell you that
somebody has been posting to it for a week with a bad signature.

``SignalSource.secret`` is a credential and is treated as one: Fernet at rest
like an exchange key and the Telegram token, never returned by the API, never
logged, and shown exactly once at creation because nobody can re-read it
afterwards. The fingerprint is what the panel displays instead.
"""

from __future__ import annotations

import secrets

from django.db import models

from apps.core import crypto


class Verdict(models.TextChoices):
    """What happened to one delivery. Every arrival gets exactly one."""

    ACCEPTED = "accepted", "Routed"
    #: The same ``signal_id`` arrived twice. Not an error — alert systems
    #: retry, and a retry that re-entered a position would be the worst bug
    #: this endpoint could have.
    DUPLICATE = "duplicate", "Duplicate — already handled"
    #: Understood and deliberately not acted on: an EXIT_BUY with no long
    #: open, a BUY while already long. The position is already what the signal
    #: asked for, which is success, not failure.
    NOOP = "noop", "Already in that state"
    REJECTED = "rejected", "Refused"


class SignalSource(models.Model):
    """One external strategy allowed to move this platform's positions.

    Bound to exactly one bot. That binding is what makes the webhook safe to
    have at all: the bot carries the symbol, the market, the leverage, the exit
    policy, the risk gate, the journal, the one-open-trade rule and the stop
    button. A source cannot name any of them, so the worst a compromised secret
    can do is trade the pair the admin already chose, at the size §5 already
    fixed — and the §7 halt in the top bar stops it like anything else.
    """

    name = models.CharField(max_length=120, unique=True)
    bot = models.OneToOneField(
        "bots.Bot", on_delete=models.CASCADE, related_name="signal_source_config"
    )

    #: The public half — it appears in the URL the sender posts to. Not a
    #: secret and not treated as one; it identifies which source is speaking so
    #: the right secret can be used to check that it really is them.
    token = models.CharField(max_length=43, unique=True, db_index=True)
    #: The shared secret the HMAC is computed with. Write-only, everywhere.
    secret_encrypted = models.TextField(blank=True)
    secret_fingerprint = models.CharField(max_length=16, blank=True)

    #: Off by default. A source that exists is not a source that may trade —
    #: creating one and enabling it are two deliberate acts.
    enabled = models.BooleanField(default=False)
    #: Whether a signature is required. Settable, never settable to off from
    #: the API while the bot is live — see ``serializers``. An unsigned webhook
    #: that routes real orders is a URL anyone who has ever seen it can trade.
    require_signature = models.BooleanField(default=True)
    #: Optional source addresses. Empty means "any" — the signature is the real
    #: control, and an allowlist that silently became the only one would fail
    #: open the day a provider changed egress ranges.
    allowed_ips = models.JSONField(default=list, blank=True)
    #: How old a signed delivery may be. A signature with no time bound is a
    #: replayable one: capture a ``BUY`` today, post it again in a drawdown.
    replay_window_seconds = models.PositiveIntegerField(default=300)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=150, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} → {self.bot_id}"

    # --- the secret ---------------------------------------------------------

    @staticmethod
    def new_token() -> str:
        return secrets.token_urlsafe(32)[:43]

    @staticmethod
    def new_secret() -> str:
        return secrets.token_urlsafe(48)

    @property
    def secret(self) -> str:
        return crypto.decrypt(self.secret_encrypted)

    @property
    def has_secret(self) -> bool:
        return bool(self.secret_encrypted)

    def set_secret(self, plaintext: str) -> None:
        self.secret_encrypted = crypto.encrypt(plaintext)
        self.secret_fingerprint = crypto.fingerprint(plaintext)

    @property
    def endpoint(self) -> str:
        """The path a sender posts to. Relative — the host is the panel's own."""
        return f"/api/signals/hooks/{self.token}/"


class SignalEvent(models.Model):
    """One delivery, kept forever — the same reason ``BotAction`` is (Q26).

    It is what answers "the position flipped at 03:12, who said so", and it
    answers it for refusals too. Small, and the volume is bounded by how often
    a strategy actually signals rather than by the bar rate.
    """

    source = models.ForeignKey(
        SignalSource, on_delete=models.CASCADE, related_name="events"
    )
    received_at = models.DateTimeField(auto_now_add=True)
    remote_addr = models.CharField(max_length=64, blank=True)

    #: The sender's own id, or a digest of the body when it sent none. Unique
    #: per source: this is the deduplication, and it is a database constraint
    #: rather than a check for the reason ``BotAction``'s is — the case it
    #: defends against is two deliveries in flight at once, and at that moment
    #: no amount of application logic is holding a lock.
    signal_id = models.CharField(max_length=140)

    verb = models.CharField(max_length=12, blank=True)
    verdict = models.CharField(max_length=12, choices=Verdict.choices)
    code = models.CharField(max_length=40, blank=True)
    detail = models.TextField(blank=True)

    #: The body as it arrived. No credential is ever in here: the signature
    #: travels in a header and the secret never travels at all.
    payload = models.JSONField(default=dict, blank=True)
    #: What ``translate.plan`` decided, and what came back per leg.
    actions = models.JSONField(default=list, blank=True)

    run = models.ForeignKey(
        "bots.BotRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signal_events",
    )

    class Meta:
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "signal_id"], name="signals_event_unique_per_source"
            )
        ]
        indexes = [models.Index(fields=["source", "-received_at"])]

    def __str__(self) -> str:
        return f"{self.verb or '?'} {self.verdict} ({self.source_id})"
