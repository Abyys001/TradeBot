"""The second factor, and the browser that is allowed to skip it.

Two halves that only make sense together. A code demanded at every sign-in gets
switched off within a week, so ``trusted_devices`` is not a convenience bolted
on afterwards — it is what makes ``two_factor`` survive contact with daily use.
``docs/security-plan.md`` phase 4 says the two ship together for that reason.

Enrolment is deliberately three steps, not one:

1. ``begin`` writes an **unconfirmed** secret and hands back the QR;
2. ``confirm`` proves the app is holding it, and only then mints recovery codes;
3. ``acknowledge_recovery`` records that they were saved.

Only after all three will ``flags.set_flags`` let the switch be armed. A secret
written but never proved would arm a prompt nobody can answer, which is the
lock-out this layer exists to avoid.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import timedelta

import pyotp
import qrcode
import qrcode.image.svg
from django.utils import timezone

from apps.core.crypto import decrypt, encrypt
from apps.security.models import TotpDevice, TrustedDevice

#: 30-second steps, and one step of tolerance either side for clock drift.
STEP_SECONDS = 30
DRIFT_STEPS = 1
RECOVERY_CODES = 10
TRUST_COOKIE = "panel_trust"
ISSUER = "TradeBot"


# --- recovery codes ---------------------------------------------------------
#
# Hashed with a bare SHA-256 rather than Django's password hasher, and for the
# same reason ``PanelSession`` hashes its session key that way: these are 80
# bits of ``secrets`` output, not something a person chose. A slow hash defends
# against guessing a low-entropy secret, and buys nothing here — while costing
# a PBKDF2 round per stored code on every sign-in that falls back to one.


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").upper().encode()).hexdigest()


def _new_codes() -> list[str]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1
    codes = []
    for _ in range(RECOVERY_CODES):
        raw = "".join(secrets.choice(alphabet) for _ in range(16))
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:]}")
    return codes


# --- enrolment --------------------------------------------------------------


def begin(user) -> dict:
    """Start (or restart) enrolment. Returns the secret, the URI and a QR.

    Restarting is allowed and throws the previous secret away: an operator who
    lost the phone mid-enrolment should not have to be unpicked by hand.
    """
    secret = pyotp.random_base32()
    device, _ = TotpDevice.objects.update_or_create(
        user=user,
        defaults={
            "secret": encrypt(secret),
            "confirmed_at": None,
            "recovery_codes": [],
            "recovery_acknowledged_at": None,
            "last_step": 0,
        },
    )
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.get_username(), issuer_name=ISSUER)
    return {"secret": secret, "uri": uri, "qr_svg": qr_svg(uri), "device": device}


def qr_svg(uri: str) -> str:
    """The provisioning URI as an inline SVG.

    SVG rather than PNG because it needs no imaging library in the container,
    and inline because the panel's Content-Security-Policy — which this same
    settings card can switch on — would block it as an external image.
    """
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    return image.to_string(encoding="unicode")


def confirm(user, code: str) -> list[str]:
    """Prove the app holds the secret, then mint the recovery codes.

    Returns the plaintext codes. They are shown once and are not recoverable
    afterwards — only their hashes are kept.
    """
    device = TotpDevice.objects.filter(user=user).first()
    if device is None:
        raise ValueError("no enrolment in progress")
    if not _check_totp(device, code):
        raise ValueError("that code is not right — check the time on the phone")

    codes = _new_codes()
    device.confirmed_at = timezone.now()
    device.recovery_codes = [{"hash": _hash_code(one), "used_at": None} for one in codes]
    device.recovery_acknowledged_at = None
    device.save(update_fields=["confirmed_at", "recovery_codes", "recovery_acknowledged_at"])
    return codes


def acknowledge_recovery(user) -> None:
    """The operator says the codes are stored. The last gate before arming."""
    TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).update(
        recovery_acknowledged_at=timezone.now()
    )


def disable(user) -> None:
    TotpDevice.objects.filter(user=user).delete()
    TrustedDevice.objects.filter(user=user).delete()


def device_state(user) -> dict:
    device = TotpDevice.objects.filter(user=user).first()
    trusted = TrustedDevice.objects.filter(user=user, expires_at__gt=timezone.now()).count()
    if device is None:
        return {"enrolled": False, "confirmed": False, "ready": False,
                "recovery_remaining": 0, "trusted_devices": trusted}
    return {
        "enrolled": True,
        "confirmed": bool(device.confirmed_at),
        "ready": device.is_ready,
        "recovery_remaining": device.recovery_remaining,
        "trusted_devices": trusted,
    }


# --- verification -----------------------------------------------------------


def _check_totp(device: TotpDevice, code: str) -> bool:
    """A code, checked across the drift window, and never twice.

    ``pyotp.verify`` would do the window on its own but will not say *which*
    step matched, and without that the replay guard cannot exist: a code is
    valid for a whole 30-second step, so one shoulder-surfed digit string works
    twice inside a minute.
    """
    candidate = (code or "").strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != 6:
        return False

    totp = pyotp.TOTP(decrypt(device.secret))
    current = int(time.time()) // STEP_SECONDS
    for offset in range(-DRIFT_STEPS, DRIFT_STEPS + 1):
        step = current + offset
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), candidate):
            if step <= device.last_step:
                return False
            device.last_step = step
            device.save(update_fields=["last_step"])
            return True
    return False


def _check_recovery(device: TotpDevice, code: str) -> bool:
    digest = _hash_code(code or "")
    for entry in device.recovery_codes:
        if entry.get("used_at") or not hmac.compare_digest(entry.get("hash", ""), digest):
            continue
        entry["used_at"] = timezone.now().isoformat()
        device.save(update_fields=["recovery_codes"])
        return True
    return False


def verify(user, code: str) -> str | None:
    """``"totp"``, ``"recovery"``, or ``None``. The caller decides what to log."""
    device = TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).first()
    if device is None:
        return None
    if _check_totp(device, code):
        return "totp"
    if _check_recovery(device, code):
        return "recovery"
    return None


def required_for(user) -> bool:
    """Whether this user has a usable second factor. Called only when armed."""
    return TotpDevice.objects.filter(
        user=user, confirmed_at__isnull=False, recovery_acknowledged_at__isnull=False
    ).exists()


# --- trusted browsers -------------------------------------------------------


def trust_token(request) -> str:
    return request.COOKIES.get(TRUST_COOKIE, "")


def is_trusted(user, request) -> bool:
    token = trust_token(request)
    if not token:
        return False
    device = TrustedDevice.objects.filter(
        user=user, token_hash=TrustedDevice.hash_token(token), expires_at__gt=timezone.now()
    ).first()
    if device is None:
        return False
    device.last_used_at = timezone.now()
    device.save(update_fields=["last_used_at"])
    return True


def remember(user, request, response, *, days: int, label: str = "") -> None:
    """Issue the cookie that lets this browser skip the code next time."""
    from django.conf import settings

    token = secrets.token_urlsafe(32)
    expires = timezone.now() + timedelta(days=days)
    TrustedDevice.objects.create(
        user=user,
        token_hash=TrustedDevice.hash_token(token),
        label=label[:120],
        ip_address=_ip(request),
        expires_at=expires,
    )
    response.set_cookie(
        TRUST_COOKIE,
        token,
        max_age=days * 86400,
        # HttpOnly for the reason the session cookie is: a token readable by
        # injected script is a second factor an XSS can carry off.
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="Lax",
        path="/",
    )


def forget(user, request, response) -> None:
    token = trust_token(request)
    if token:
        TrustedDevice.objects.filter(
            user=user, token_hash=TrustedDevice.hash_token(token)
        ).delete()
    response.delete_cookie(TRUST_COOKIE, path="/")


def forget_all(user) -> int:
    deleted, _ = TrustedDevice.objects.filter(user=user).delete()
    return deleted


def _ip(request):
    from apps.accounts.sessions import client_ip

    return client_ip(request)
