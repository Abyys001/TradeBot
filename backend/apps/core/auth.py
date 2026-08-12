"""Authentication for the async order-routing views.

DRF's permission classes do not apply to plain Django async views, so the
routing endpoints need their own gate. Without it, anything that can reach the
API can move real money across every connected account.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable

from django.http import HttpRequest, JsonResponse


def admin_required(
    view: Callable[..., Awaitable[JsonResponse]],
) -> Callable[..., Awaitable[JsonResponse]]:
    """Require an authenticated staff user.

    Staff rather than merely authenticated: these endpoints place and close real
    orders on other people's capital, so being logged in is not enough.
    """

    @functools.wraps(view)
    async def wrapper(request: HttpRequest, *args, **kwargs) -> JsonResponse:
        user = await request.auser()
        if not user.is_authenticated:
            return JsonResponse({"detail": "authentication required"}, status=401)
        if not user.is_staff:
            return JsonResponse({"detail": "staff access required"}, status=403)
        return await view(request, *args, **kwargs)

    return wrapper
