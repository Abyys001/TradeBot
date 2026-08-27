"""Reading the security policy without paying for it.

``apps.trading.killswitch`` is the model: a singleton row, read through the
cache so the hot path costs a cache hit rather than a query. This module adds
one thing on top of that, and it is the reason the Security card can exist at
all — **a process-local memo**.

The kill switch is read once per routed order. These flags are read by a
middleware, which runs on *every* request including the routed order's. A Redis
GET there is small but it is not nothing, and it would be paid by deployments
that never turned a single switch on. So a snapshot is reused inside the worker
for ``POLICY_MEMO_SECONDS`` (default 1.0), which makes an off switch cost a dict
lookup and a float comparison — no I/O at all. The price is that a flip takes up
to that long to reach every worker, which for "ask for a code at sign-in" is not
a meaningful delay.

Two escapes are wired in here rather than anywhere else:

* ``SECURITY_FEATURES=false`` in the environment returns the all-off snapshot
  without touching the cache or the database. It is the mirror image of
  ``STOP_ALL``: that one cannot be *cleared* from a browser, this one cannot be
  *set* from one.
* a database error resolves every switch to **off**. The kill switch fails to
  *halted* because routing other people's capital on a guess is the wrong side
  to be on. Here the wrong side is locking the operator out of a live book, so
  it fails the other way.

Nothing in ``apps/engine/``, ``apps/trading/`` or ``apps/pine/`` may import this
module; ``tests/test_security_scope.py`` enforces that.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from types import MappingProxyType

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError

logger = logging.getLogger(__name__)

CACHE_KEY = "security:policy"
CACHE_TTL = 300

#: Every field the policy row exposes, with the value it has when nobody has
#: touched anything. Every boolean is False by construction — see the note on
#: ``SecurityPolicy``.
DEFAULTS: dict[str, object] = {
    "two_factor": False,
    "trusted_devices": False,
    "login_rate_limit": False,
    "new_device_notice": False,
    "idle_timeout": False,
    "single_session": False,
    "ip_allowlist": False,
    "step_up": False,
    "audit_log": False,
    "admin_write_rate_limit": False,
    "csp_mode": "off",
    "login_max_attempts": 5,
    "login_window_seconds": 300,
    "login_lockout_seconds": 900,
    "idle_timeout_minutes": 480,
    "session_max_hours": 336,
    "trusted_device_days": 30,
    "step_up_grace_seconds": 300,
    "admin_write_max_per_minute": 60,
    "allowed_ips": "",
}

#: The on/off rows. Order is the order the Settings card renders them in.
SWITCHES: tuple[str, ...] = (
    "two_factor",
    "trusted_devices",
    "login_rate_limit",
    "new_device_notice",
    "idle_timeout",
    "single_session",
    "ip_allowlist",
    "step_up",
    "audit_log",
    "admin_write_rate_limit",
)

#: The switches the request middleware has to look at. Everything else is read
#: on the sign-in path or on an admin write, where a cache hit is free relative
#: to what those endpoints already do.
_MIDDLEWARE_SWITCHES = ("ip_allowlist", "idle_timeout", "admin_write_rate_limit")

_FIELDS: tuple[str, ...] = tuple(DEFAULTS)


class PolicyError(ValueError):
    """A switch was asked for in a state that would strand its owner."""


def parse_networks(raw: str) -> tuple:
    """Addresses and CIDR blocks, one per line or comma-separated.

    An unparseable entry is dropped rather than raising: the allowlist is read
    on every request, and a typo saved last week must not be able to 500 the
    panel. ``set_flags`` validates on the way in, which is where a typo can
    still be reported to the person who made it.
    """
    networks = []
    for chunk in (raw or "").replace(",", "\n").split("\n"):
        candidate = chunk.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            logger.warning("security: ignoring unparseable allowlist entry")
    return tuple(networks)


def _derive(values: dict) -> dict:
    """Add the two computed keys every reader wants and nobody should recompute."""
    values["_allowed_networks"] = parse_networks(values.get("allowed_ips", ""))
    values["_middleware_active"] = any(bool(values[name]) for name in _MIDDLEWARE_SWITCHES)
    return values


_OFF = MappingProxyType(_derive(dict(DEFAULTS)))

_memo: dict | None = None
_memo_until: float = 0.0


def _row():
    from apps.security.models import SecurityPolicy

    row, _ = SecurityPolicy.objects.get_or_create(singleton=1)
    return row


def _load() -> dict:
    try:
        row = _row()
    except DatabaseError:
        # Off, not on. A panel that cannot read its own policy must stay
        # reachable; the alternative is an operator locked out of open trades
        # by a database blip.
        logger.exception("security: policy unreadable — every control treated as off")
        return dict(_OFF)
    values = {name: getattr(row, name) for name in _FIELDS}
    return _derive(values)


def enabled() -> bool:
    """False when the environment pins the whole layer off."""
    return bool(settings.SECURITY["FEATURES"])


def policy() -> dict:
    """The current policy. One dict lookup on the common path.

    The returned mapping is shared — treat it as read-only.
    """
    global _memo, _memo_until

    if not enabled():
        return _OFF

    now = time.monotonic()
    if _memo is not None and now < _memo_until:
        return _memo

    values = cache.get(CACHE_KEY)
    if values is None:
        values = _load()
        cache.set(CACHE_KEY, values, CACHE_TTL)

    _memo = values
    _memo_until = now + float(settings.SECURITY["POLICY_MEMO_SECONDS"])
    return values


def peek() -> dict | None:
    """The snapshot this process already holds, or ``None`` if it has lapsed.

    Exists for the ASGI middleware: it lets the common case answer from memory
    on the event loop, and pushes the refresh — which may touch Redis — into a
    thread only on the one request a second that needs it.
    """
    if not enabled():
        return _OFF
    if _memo is not None and time.monotonic() < _memo_until:
        return _memo
    return None


def is_on(name: str) -> bool:
    """One switch. Prefer holding the result of ``policy()`` when you need several."""
    return bool(policy()[name])


def invalidate() -> None:
    """Drop the shared and local snapshots. Called after a write, and by tests."""
    global _memo, _memo_until
    _memo = None
    _memo_until = 0.0
    cache.delete(CACHE_KEY)


def state() -> dict:
    """What the Settings card renders: the values, plus why they are what they are."""
    values = dict(_load()) if enabled() else dict(_OFF)
    values.pop("_allowed_networks", None)
    values.pop("_middleware_active", None)
    row_meta = {"updated_at": None, "updated_by": ""}
    if enabled():
        try:
            row = _row()
            row_meta = {"updated_at": row.updated_at, "updated_by": row.updated_by}
        except DatabaseError:
            pass
    return {
        **values,
        **row_meta,
        # False means the panel renders every row locked: the environment has
        # pinned the layer off and no API call will change that.
        "available": enabled(),
        "switches": list(SWITCHES),
    }


def _guard(name: str, value, pending: dict) -> None:
    """Refuse the two changes that can strand the person making them."""
    if name == "two_factor" and value:
        from apps.security.models import TotpDevice

        ready = TotpDevice.objects.filter(user__is_staff=True).filter(
            confirmed_at__isnull=False, recovery_acknowledged_at__isnull=False
        )
        if not ready.exists():
            raise PolicyError(
                "enrol an authenticator app and save the recovery codes before "
                "arming the second factor"
            )
    if name == "ip_allowlist" and value and not parse_networks(str(pending.get("allowed_ips", ""))):
        raise PolicyError("add at least one address before restricting sign-in")


def set_flags(changes: dict, *, actor: str = "") -> dict:
    """Write some subset of the policy. Returns the new ``state()``.

    Unknown keys are rejected rather than ignored — a typo in a flag name that
    silently does nothing is a security control the operator believes is on.
    """
    # The environment pin stops a control being *armed*, never disarmed:
    # ``manage.py security_off`` has to keep working whatever else is wrong,
    # and clearing a switch that is already inert costs nothing.
    arming = any(bool(value) and name in SWITCHES for name, value in changes.items())
    if arming and not enabled():
        raise PolicyError("the security layer is switched off by the environment")

    unknown = set(changes) - set(_FIELDS)
    if unknown:
        raise PolicyError(f"unknown setting: {', '.join(sorted(unknown))}")

    row = _row()
    before = {name: getattr(row, name) for name in changes}
    pending = {name: getattr(row, name) for name in _FIELDS} | changes

    for name, value in changes.items():
        _guard(name, value, pending)

    for name, value in changes.items():
        setattr(row, name, value)
    row.updated_by = actor[:150]
    row.full_clean()
    row.save(update_fields=[*changes, "updated_by", "updated_at"])
    invalidate()

    after = {name: getattr(row, name) for name in changes}
    changed = {name: [before[name], after[name]] for name in changes if before[name] != after[name]}
    if changed:
        # Always recorded, whether or not the audit log is on — see the note on
        # ``SecurityEvent``. This is a manual save on a settings page, so the
        # insert is provably not on any hot path.
        from apps.security.audit import record_policy_change

        record_policy_change(changed, actor=actor)
        logger.warning("security policy changed by %s: %s", actor or "?", sorted(changed))

    return state()
