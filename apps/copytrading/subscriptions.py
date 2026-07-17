"""Signal <-> investor subscription management for copy-trading fan-out.

Auto-follow model: activating a strategy attaches every active investor's active
Tabdeal credential to that strategy's CopySignal. New investors added later are
picked up by re-running ``sync_subscriptions`` (on activate / on a reconcile).
"""
from __future__ import annotations

import secrets

from .models import CopySignal, CopySubscription


def ensure_signal(strategy) -> CopySignal:
    """Get or create the CopySignal bound to this strategy."""
    signal = getattr(strategy, "copy_signal", None)
    if signal is None:
        signal = CopySignal.objects.create(
            owner=strategy.user,
            strategy=strategy,
            name=(strategy.name or f"signal-{strategy.pk}")[:64],
            secret_token=secrets.token_urlsafe(24),
        )
    return signal


def sync_subscriptions(strategy) -> dict:
    """Subscribe every active investor's active Tabdeal credential to the signal."""
    from apps.accounts.models import User
    from apps.credentials.models import Exchange, ExchangeCredential

    signal = ensure_signal(strategy)
    creds = ExchangeCredential.objects.filter(
        exchange=Exchange.TABDEAL,
        is_active=True,
        user__is_active=True,
        user__role=User.Role.INVESTOR,
    ).select_related("user")

    created = 0
    for cred in creds:
        _, was_created = CopySubscription.objects.get_or_create(
            signal=signal, credential=cred, defaults={"is_active": True}
        )
        created += int(was_created)
    total = CopySubscription.objects.filter(signal=signal, is_active=True).count()
    return {"signal_id": signal.pk, "new": created, "active_total": total}


def ensure_owner_subscription(strategy) -> CopySubscription | None:
    """Attach the strategy owner's own active Tabdeal credential to their signal.

    sync_subscriptions() intentionally excludes admin-role users via its
    User.Role.INVESTOR filter -- that filter must stay untouched (relied on
    elsewhere). This is a separate, role-independent path so the strategy
    owner (e.g. an admin running their own bot script) also receives real
    fills on their own Tabdeal account, exactly like an auto-followed
    investor.
    """
    from apps.credentials.models import Exchange

    signal = ensure_signal(strategy)
    cred = strategy.credential
    if cred is None or cred.exchange != Exchange.TABDEAL or not cred.is_active:
        return None
    if cred.user_id != strategy.user_id:
        return None
    sub, created = CopySubscription.objects.get_or_create(
        signal=signal, credential=cred, defaults={"is_active": True}
    )
    if not created and not sub.is_active:
        sub.is_active = True
        sub.save(update_fields=["is_active"])
    return sub
