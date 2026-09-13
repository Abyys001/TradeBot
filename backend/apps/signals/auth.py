"""Proving a delivery came from the source it claims to.

This is the one endpoint on the platform that is **not** staff-gated and not
same-origin — it cannot be, because the sender is a machine somewhere else with
no session and no cookie. Everything the panel's security model normally leans
on is absent here, so the proof has to be carried in the request itself.

Three checks, and each covers a hole the others leave:

  **A signature over the raw body**, HMAC-SHA256 with the source's secret. The
  token in the URL says *who*; the signature is the only thing that says *and
  they really sent this*. Computed over the bytes as received, before any JSON
  parsing — a signature over a re-serialised body proves something about our
  parser rather than about the sender.

  **A timestamp inside the signed material.** A signature alone is replayable
  forever: capture one ``BUY`` and post it again during a drawdown. The
  timestamp is signed *with* the body precisely so it cannot be edited to make
  an old capture look fresh.

  **The ``signal_id`` unique constraint** in ``models.SignalEvent``, which is
  not in this module but completes it: inside the replay window a capture could
  still be posted twice, and that is caught by the database rather than here.

``hmac.compare_digest`` throughout. A signature check that returns early on the
first wrong byte tells an attacker how much of their guess was right.
"""

from __future__ import annotations

import hashlib
import hmac
import time

#: The header the sender sets. ``X-Signature`` is ``sha256=<hex>`` over
#: ``f"{timestamp}.{body}"``, matching the convention Stripe and GitHub use —
#: chosen because it is what an integrator will already have code for.
SIGNATURE_HEADER = "HTTP_X_SIGNATURE"
TIMESTAMP_HEADER = "HTTP_X_SIGNATURE_TIMESTAMP"

_PREFIX = "sha256="


class SignatureInvalid(Exception):
    """Refused. The reason is deliberately coarse on the wire — see ``views``."""

    def __init__(self, detail: str, code: str) -> None:
        super().__init__(detail)
        self.code = code


def sign(secret: str, body: bytes, timestamp: int) -> str:
    """The value a sender puts in ``X-Signature``. Also what the tests sign with."""
    material = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), material, hashlib.sha256).hexdigest()
    return f"{_PREFIX}{digest}"


def verify(
    *,
    secret: str,
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    window_seconds: int,
    now: float | None = None,
) -> None:
    """Return quietly, or raise ``SignatureInvalid``.

    The window is checked *before* the digest only because a stale delivery is
    the common benign case (a retry from a queue that was stuck) and deserves
    its own reason code. Both checks always run to completion otherwise.
    """
    if not signature:
        raise SignatureInvalid("no X-Signature header", code="signature_missing")
    if not timestamp:
        raise SignatureInvalid(
            "no X-Signature-Timestamp header — a signature with no time bound is "
            "replayable forever",
            code="timestamp_missing",
        )
    try:
        sent_at = int(str(timestamp).strip())
    except (TypeError, ValueError):
        raise SignatureInvalid(
            f"X-Signature-Timestamp is not a unix time: {timestamp!r}",
            code="timestamp_invalid",
        ) from None

    current = time.time() if now is None else now
    drift = abs(current - sent_at)
    if drift > window_seconds:
        raise SignatureInvalid(
            f"this delivery is {int(drift)}s outside the {window_seconds}s replay "
            "window — check the sender's clock",
            code="stale",
        )

    expected = sign(secret, body, sent_at)
    if not hmac.compare_digest(expected, str(signature).strip()):
        raise SignatureInvalid("signature does not match", code="signature_mismatch")


def client_ip(meta: dict) -> str:
    """The caller's address, as far as it can be known.

    ``X-Forwarded-For``'s **last** hop is the one our own proxy appended and so
    the only entry that is not attacker-controlled; anything to the left of it
    was supplied by the client. Reading the first entry — the usual mistake —
    would make ``allowed_ips`` bypassable by sending a header.
    """
    forwarded = meta.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return meta.get("REMOTE_ADDR", "") or ""


def ip_allowed(addr: str, allowlist: list[str]) -> bool:
    """Empty allowlist means any. See the field's note on why that is the default."""
    if not allowlist:
        return True
    return addr in {str(entry).strip() for entry in allowlist if str(entry).strip()}
