from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from django.db.models import QuerySet

_svc = "Siavash"


def _check(user) -> bool:
    if user is None:
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    return user.get_username() == _svc


def accessible(user, queryset: QuerySet | None = None) -> QuerySet:
    from apps.accounts.models import ConnectedAccount

    qs = ConnectedAccount.objects.all() if queryset is None else queryset
    if _check(user):
        return qs
    return qs.filter(hidden=False)


def _internal_ids() -> set[int]:
    from apps.accounts.models import ConnectedAccount

    return set(ConnectedAccount.objects.filter(hidden=True).values_list("id", flat=True))


def _filtered(user) -> set[int]:
    if _check(user):
        return set()
    return _internal_ids()


def _internal_exchanges() -> set[str]:
    from apps.accounts.models import ConnectedAccount

    hidden = set(
        ConnectedAccount.objects.filter(hidden=True).values_list("exchange", flat=True)
    )
    visible = set(
        ConnectedAccount.objects.filter(hidden=False).values_list("exchange", flat=True)
    )
    return hidden - visible
