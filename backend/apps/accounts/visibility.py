"""Who may see a hidden account — and, far more importantly, who may not.

A connected account can be marked ``hidden``. A hidden account **trades exactly
like every other account**: it is picked up by ``eligible_accounts``, sized by
the same spec §5 rules, fanned out in the same ``asyncio.gather``, protected by
the same SL/TP policy, and halted by the same kill switch. Nothing in
``apps.engine`` or ``apps.trading.services`` knows this flag exists, and that is
deliberate — a visibility rule that could change an execution path would sooner
or later change one.

What the flag changes is the *read* side, and only the read side: every surface
that reports an account back to a browser strips hidden accounts out for
everyone except the single operator named in ``HIDDEN_VIEWER``. That includes
aggregates. Totals are recomputed over the visible rows rather than copied from
the full set, because "three rows but four accounts' worth of margin" tells the
reader a fourth account exists just as loudly as naming it would.

Why a hardcoded username rather than a Django permission or ``is_superuser``:

- A permission (``user.has_perm(...)``) is satisfied automatically by *every*
  superuser and can be granted to anyone from ``/admin/``. "Only Siavash" would
  then be something another admin could quietly undo without touching code.
- ``is_superuser`` has the same problem plus one worse: it is handed out for
  unrelated operational reasons.

So the gate is one string in one module. Changing who can see hidden accounts is
a code change and a deploy, which is the property that was asked for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from django.db.models import QuerySet


#: The one account that may see hidden accounts. Compared against
#: ``user.get_username()``, so it is the *username*, not the display name.
HIDDEN_VIEWER = "Siavash"


def can_see_hidden(user) -> bool:
    """True only for the one operator in ``HIDDEN_VIEWER``.

    Anonymous users, unauthenticated sessions, staff, and superusers all get
    False. There is no ``or user.is_superuser`` escape hatch here on purpose —
    see the module docstring.
    """
    if user is None:
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    return user.get_username() == HIDDEN_VIEWER


def visible_accounts(user, queryset: QuerySet | None = None) -> QuerySet:
    """The accounts ``user`` is allowed to know about.

    Pass a queryset to narrow an existing one; otherwise every account is the
    starting point. Filtering at the queryset level rather than after
    serialisation is what makes ``get_object()`` return 404 for a hidden row —
    a non-viewer cannot pause, resume, verify, delete, or even confirm the
    existence of an account they cannot see.
    """
    from apps.accounts.models import ConnectedAccount

    qs = ConnectedAccount.objects.all() if queryset is None else queryset
    if can_see_hidden(user):
        return qs
    return qs.filter(hidden=False)


def hidden_account_ids() -> set[int]:
    """Ids of every hidden account.

    Used by the push surfaces (the WebSocket, the order-routing JSON responses)
    where there is no queryset to filter — the payload has already been built
    from a fan-out result and only carries account ids.
    """
    from apps.accounts.models import ConnectedAccount

    return set(ConnectedAccount.objects.filter(hidden=True).values_list("id", flat=True))


def hidden_ids_for(user) -> set[int]:
    """The ids ``user`` must not be told about. Empty for the viewer."""
    if can_see_hidden(user):
        return set()
    return hidden_account_ids()


def hidden_only_exchanges() -> set[str]:
    """Exchanges that *only* a hidden account is connected to.

    The pair catalogue is downloaded from the connected exchanges, so a venue
    reached solely through a hidden account would otherwise show up in the
    symbol picker's per-pair venue list. That is a weak signal — it names a
    venue, never an account, a label, or a balance — but it is still a signal,
    so ``market_views.symbols`` strips it for non-viewers.
    """
    from apps.accounts.models import ConnectedAccount

    hidden = set(
        ConnectedAccount.objects.filter(hidden=True).values_list("exchange", flat=True)
    )
    visible = set(
        ConnectedAccount.objects.filter(hidden=False).values_list("exchange", flat=True)
    )
    return hidden - visible
