"""Asking for the password again, before the few writes that deserve it.

The list is short on purpose. Step-up guards **credentials, money records and
promoting a bot to live** — writes that are rare, deliberate, and expensive to
undo. It does not guard opening, amending or closing a position, and it does
not guard the emergency halt.

That exclusion is the point rather than an oversight. A password prompt in
front of "close this position" is a control whose cost lands during the one
minute it matters most, and the attacker it would stop is one who already holds
a staff session — who can simply wait for the grant the operator is about to
create anyway.

The grant lives in the session, so it is per-browser and dies with the sign-in.
"""

from __future__ import annotations

import time

from rest_framework.exceptions import APIException

from apps.security.audit import record
from apps.security.flags import policy
from apps.security.models import SecurityEventKind

SESSION_KEY = "_stepup_at"


class StepUpRequired(APIException):
    """403 with a code the panel recognises and answers with a prompt."""

    status_code = 403
    default_detail = "confirm your password to continue"
    default_code = "step_up_required"


def grant(request) -> None:
    request.session[SESSION_KEY] = time.time()


def revoke(request) -> None:
    request.session.pop(SESSION_KEY, None)


def satisfied(request) -> bool:
    values = policy()
    if not values["step_up"]:
        return True
    granted = request.session.get(SESSION_KEY)
    if not granted:
        return False
    return (time.time() - float(granted)) < float(values["step_up_grace_seconds"])


def remaining(request) -> int:
    """Seconds left on the grant — what the panel shows next to the switch."""
    values = policy()
    if not values["step_up"]:
        return 0
    granted = request.session.get(SESSION_KEY)
    if not granted:
        return 0
    left = float(values["step_up_grace_seconds"]) - (time.time() - float(granted))
    return max(0, int(left))


def enforce(request, *, action: str = "") -> None:
    """Raise unless the caller has confirmed their password recently enough."""
    if satisfied(request):
        return
    record(
        SecurityEventKind.STEP_UP_REQUIRED,
        request,
        detail={"action": action} if action else {},
    )
    raise StepUpRequired(
        {
            "detail": StepUpRequired.default_detail,
            # In the body, not only in DRF's exception code: the panel
            # branches on it to open the prompt and retry the same call.
            "code": StepUpRequired.default_code,
            "action": action or None,
        }
    )
