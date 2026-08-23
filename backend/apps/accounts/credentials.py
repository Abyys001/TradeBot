"""When a credential stops working, and how long the panel has to say so.

Most credentials fail loudly: the exchange refuses the request and the leg comes
back with an error the admin can read. Hyperliquid's do not. An agent approval
carries an expiry — `approveAgent`'s optional `valid_until`, capped by the
exchange at 180 days — and when it passes the agent wallet is **pruned**, not
rejected with a message. The account simply stops trading, and nothing in the
API says why.

There is no endpoint to ask. So the platform tracks the date it was given at
connect time (``ConnectedAccount.credential_expires_at``) and counts down to it,
which turns a silent disconnection into three weeks of warning.

This module only measures and reports. It never pauses an account, never
excludes one from a fan-out, and never touches an exchange — an expiring
credential is still a working credential, and the day it is not, the leg fails
through the path every other failure already takes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import AccountStatus, ConnectedAccount, Notification

#: No expiry recorded, or one too far out to be worth mentioning.
OK = ""
#: Inside the warning window. Still trading; needs a person to renew it.
EXPIRING = "expiring"
#: Past its date. On Hyperliquid the agent is already pruned.
EXPIRED = "expired"

NOTIFICATION_CODES = ("credential_expiring", "credential_expired")


def warn_days() -> int:
    return int(settings.CREDENTIALS["EXPIRY_WARN_DAYS"])


def max_agent_days() -> int:
    return int(settings.CREDENTIALS["MAX_AGENT_DAYS"])


def days_left(account: ConnectedAccount, now: datetime | None = None) -> int | None:
    """Whole days until the credential expires, or ``None`` if no date is set.

    Rounded **down**, so "1 day left" never means twenty minutes, and negative
    once the date has passed rather than clamped at zero — the panel says how
    long an account has been dead, which is the number that dates the outage.
    """
    if account.credential_expires_at is None:
        return None
    delta = account.credential_expires_at - (now or timezone.now())
    return delta.days if delta.total_seconds() >= 0 else -((-delta).days + 1)


def state(account: ConnectedAccount, now: datetime | None = None) -> str:
    remaining = days_left(account, now)
    if remaining is None:
        return OK
    if remaining < 0:
        return EXPIRED
    return EXPIRING if remaining <= warn_days() else OK


def ceiling(now: datetime | None = None) -> datetime:
    """The furthest expiry Hyperliquid will grant, from now.

    Used to sanity check a date typed at connect time. It is not used to invent
    one: an approval whose `valid_until` nobody recorded has an expiry this
    platform does not know, and guessing 180 days would put a confident wrong
    date on the screen where an honest blank belongs.
    """
    return (now or timezone.now()) + timedelta(days=max_agent_days())


@dataclass(frozen=True, slots=True)
class Expiry:
    """One account's credential clock, as the panel renders it."""

    account_id: int
    label: str
    exchange: str
    expires_at: datetime
    days_left: int
    state: str


def expiring(
    accounts: QuerySet[ConnectedAccount] | list[ConnectedAccount], now: datetime | None = None
) -> list[Expiry]:
    """Every account whose credential is inside the warning window or past it.

    Takes the caller's queryset rather than reaching for the manager, so the
    hidden-account filter the caller already applied is the one that holds
    (`accounts.visibility`).
    """
    now = now or timezone.now()
    out: list[Expiry] = []
    for account in accounts:
        status = state(account, now)
        if status == OK:
            continue
        out.append(
            Expiry(
                account_id=account.id,
                label=account.label,
                exchange=account.exchange,
                expires_at=account.credential_expires_at,
                days_left=days_left(account, now),
                state=status,
            )
        )
    out.sort(key=lambda e: e.days_left)
    return out


def sync_notifications(now: datetime | None = None) -> int:
    """Raise, escalate and clear the persistent notice for every account.

    Spec §4's notices do not expire on their own, which is right for a failed
    order and wrong for a countdown that the admin can end by renewing the key.
    So this owns both directions:

    * inside the window, one active notice per account per state — never a
      second one on the next poll, because the code and the account identify it;
    * crossing from expiring to expired replaces the notice rather than adding
      to it, so the top bar says the current thing;
    * a renewed date, a deleted account or a paused one dismisses whatever is
      standing. A notice nobody can act on any more is noise, and the admin
      dismissing it by hand would be dismissing the platform's own stale claim.

    Returns the number of notices created, so a caller can log a change without
    counting rows itself.
    """
    now = now or timezone.now()
    created = 0
    accounts = ConnectedAccount.objects.exclude(status=AccountStatus.PAUSED)
    wanted: dict[int, str] = {}
    for account in accounts:
        status = state(account, now)
        if status != OK:
            wanted[account.id] = status

    standing = Notification.objects.filter(code__in=NOTIFICATION_CODES, dismissed_at__isnull=True)
    active: set[tuple[int, str]] = set()
    for notice in standing:
        # An account that is gone, paused, renewed, or has crossed into the
        # other state no longer matches what is standing — clear it either way.
        wants = wanted.get(notice.account_id) if notice.account_id else None
        if wants is None or f"credential_{wants}" != notice.code:
            notice.dismissed_at = now
            notice.save(update_fields=["dismissed_at"])
        else:
            active.add((notice.account_id, notice.code))
    for account in accounts:
        status = wanted.get(account.id)
        if status is None:
            continue
        code = f"credential_{status}"
        if (account.id, code) in active:
            continue
        remaining = days_left(account, now)
        if status == EXPIRED:
            message = (
                f"{account.label}: the {account.get_exchange_display()} credential expired "
                f"{-remaining} day(s) ago. On Hyperliquid the agent wallet is pruned at "
                f"expiry, so this account is not trading and the exchange will not say so. "
                f"Approve a new agent and record the new date."
            )
        else:
            message = (
                f"{account.label}: the {account.get_exchange_display()} credential expires in "
                f"{remaining} day(s). Renewal needs the partner to approve a new agent, so "
                f"start now rather than on the day."
            )
        Notification.objects.create(account=account, code=code, message=message)
        created += 1
    return created
