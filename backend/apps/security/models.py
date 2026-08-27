"""The optional security layer, as rows.

Everything here is **off until somebody turns it on**. The platform's job is to
route one click to N exchanges inside a deadline, and a security control that
runs whether or not it was asked for is a cost taken without a decision. So the
shape is: one singleton row of switches, and one table per control that needs
storage — none of which is read by anything on the order-routing path.

See ``docs/security-plan.md`` for why each control exists and what it costs
when it is on.
"""

from __future__ import annotations

import hashlib

from django.db import models
from django.utils import timezone


class CspMode(models.TextChoices):
    OFF = "off", "Off"
    REPORT = "report", "Report only"
    ENFORCE = "enforce", "Enforced"


class SecurityPolicy(models.Model):
    """Every switch on the Settings page's Security card, in one row.

    A singleton for the same reason ``KillSwitch`` is one: it is read far more
    often than it is written, and a table with exactly one row can be cached as
    a single value rather than queried. ``apps.security.flags`` owns every read.

    Booleans default to ``False`` without exception. A control that arrived
    switched on would be a change to how the app works, which is the one thing
    this layer promised not to be.
    """

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1)

    # --- A. Sign-in ---------------------------------------------------------
    two_factor = models.BooleanField(default=False)
    trusted_devices = models.BooleanField(default=False)
    login_rate_limit = models.BooleanField(default=False)
    new_device_notice = models.BooleanField(default=False)
    idle_timeout = models.BooleanField(default=False)
    single_session = models.BooleanField(default=False)
    ip_allowlist = models.BooleanField(default=False)

    # --- B. Hardening -------------------------------------------------------
    step_up = models.BooleanField(default=False)
    audit_log = models.BooleanField(default=False)
    admin_write_rate_limit = models.BooleanField(default=False)
    csp_mode = models.CharField(max_length=8, choices=CspMode.choices, default=CspMode.OFF)

    # --- Tunables. Each belongs to the switch above it and is inert without it.
    login_max_attempts = models.PositiveSmallIntegerField(default=5)
    login_window_seconds = models.PositiveIntegerField(default=300)
    login_lockout_seconds = models.PositiveIntegerField(default=900)
    idle_timeout_minutes = models.PositiveIntegerField(default=480)
    session_max_hours = models.PositiveIntegerField(default=336)
    trusted_device_days = models.PositiveSmallIntegerField(default=30)
    step_up_grace_seconds = models.PositiveIntegerField(default=300)
    admin_write_max_per_minute = models.PositiveSmallIntegerField(default=60)
    #: Newline- or comma-separated addresses and CIDR blocks. Empty means the
    #: allowlist cannot be armed — an empty list is "nobody", never "everybody".
    allowed_ips = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    #: Username, not a FK — this row outlives the account that wrote it.
    updated_by = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name_plural = "security policy"

    def __str__(self) -> str:
        return "security policy"


class SecurityEventKind(models.TextChoices):
    LOGIN_OK = "login_ok", "Signed in"
    LOGIN_FAILED = "login_failed", "Sign-in refused"
    LOGIN_LOCKED = "login_locked", "Sign-in rate limited"
    LOGOUT = "logout", "Signed out"
    MFA_OK = "mfa_ok", "Second factor accepted"
    MFA_FAILED = "mfa_failed", "Second factor refused"
    MFA_ENROLLED = "mfa_enrolled", "Second factor enrolled"
    MFA_DISABLED = "mfa_disabled", "Second factor removed"
    RECOVERY_USED = "recovery_used", "Recovery code used"
    TRUST_ISSUED = "trust_issued", "Browser remembered"
    NEW_DEVICE = "new_device", "Sign-in from a new device"
    SESSION_REVOKED = "session_revoked", "Session ended remotely"
    SESSION_EXPIRED = "session_expired", "Session timed out"
    IP_BLOCKED = "ip_blocked", "Address not on the allowlist"
    RATE_LIMITED = "rate_limited", "Write rate limited"
    STEP_UP_OK = "step_up_ok", "Password re-entered"
    STEP_UP_FAILED = "step_up_failed", "Password re-entry refused"
    STEP_UP_REQUIRED = "step_up_required", "Password re-entry demanded"
    POLICY_CHANGED = "policy_changed", "Security setting changed"


class SecurityEvent(models.Model):
    """Append-only access history — ``LedgerEvent``'s shape, for access.

    ``apps.accounts.bookkeeping`` records every change to money with the actor
    and the before/after. This is the same idea one layer out: who reached the
    panel, from where, and what they changed about how it is reached.

    Written only while ``SecurityPolicy.audit_log`` is on, with one deliberate
    exception — ``POLICY_CHANGED`` is always written, because a log you can
    switch off without trace is not one. That write happens when an operator
    saves the Settings page and nowhere else.
    """

    kind = models.CharField(max_length=24, choices=SecurityEventKind.choices, db_index=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    username = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    #: Free-form context — never a credential, a session key, or a TOTP secret.
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self) -> str:
        return f"{self.kind} {self.username or '?'} @ {self.at:%Y-%m-%d %H:%M}"


class TotpDevice(models.Model):
    """One authenticator app per user.

    The secret is encrypted with the same ``MultiFernet`` that holds the
    exchange credentials: it is a bearer secret, and a database dump that hands
    over the second factor has not cost the attacker a second factor.

    ``confirmed_at`` is what makes enrolment two steps. A secret written but
    never proved — the admin scanned the code and closed the tab — must not arm
    anything, or the next sign-in asks for a code nobody can produce.
    """

    user = models.OneToOneField(
        "auth.User", on_delete=models.CASCADE, related_name="totp_device"
    )
    #: Fernet ciphertext of the base32 secret. Never returned by any endpoint
    #: after enrolment, and never logged.
    secret = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    #: Hashes of the ten single-use recovery codes. The plaintext is shown once
    #: at enrolment and is not recoverable afterwards, here or anywhere.
    recovery_codes = models.JSONField(default=list, blank=True)
    recovery_acknowledged_at = models.DateTimeField(null=True, blank=True)
    #: The last TOTP counter this device accepted. A code is valid for its whole
    #: 30-second step, so without this one shoulder-surfed code works twice.
    last_step = models.BigIntegerField(default=0)

    def __str__(self) -> str:
        return f"totp for {self.user_id}"

    @property
    def is_ready(self) -> bool:
        """Enrolled, proved, and the recovery codes acknowledged.

        All three, because arming the second factor on anything less is the
        lock-out this whole layer is designed around.
        """
        return bool(self.confirmed_at and self.recovery_acknowledged_at)

    @property
    def recovery_remaining(self) -> int:
        return sum(1 for entry in self.recovery_codes if not entry.get("used_at"))


class TrustedDevice(models.Model):
    """A browser that may skip the second factor for a while.

    Stored as a hash for the same reason ``PanelSession`` stores one: the token
    is a cookie, and a table of live cookies is a table of ready-made logins.
    """

    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="trusted_devices"
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    label = models.CharField(max_length=120, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-last_used_at"]

    def __str__(self) -> str:
        return self.label or f"trusted device {self.pk}"

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @property
    def is_live(self) -> bool:
        return self.expires_at > timezone.now()
