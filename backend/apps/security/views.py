"""The Settings card's endpoints.

Everything here is staff-only and none of it is on the routing path, so these
views can be as ordinary as they look. The one exception is ``csp_view``, which
is unauthenticated by design — see ``urls.py``.
"""

from __future__ import annotations

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from apps.security import csp, flags, ratelimit, stepup, totp
from apps.security.audit import EVENT_LIMIT, recent, record
from apps.security.models import SecurityEventKind
from apps.security.serializers import SecurityEventSerializer

#: Re-entering a password is a password prompt like any other, so it gets the
#: same treatment as the sign-in form when the limiter is on.
STEP_UP_BUCKET = "stepup"


def _state(request) -> dict:
    return {
        **flags.state(),
        "totp": totp.device_state(request.user),
        "step_up_seconds_left": stepup.remaining(request),
    }


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def policy_view(request):
    """Read the switches, or change some of them.

    A POST carries only what changed. Turning on the address allowlist adds the
    caller's own address first — the guard that stops the operator locking
    themselves out with the switch they are in the middle of using.
    """
    if request.method == "GET":
        return Response(_state(request))

    changes = dict(request.data or {})
    if not changes:
        return Response({"detail": "nothing to change"}, status=400)

    stepup.enforce(request, action="security_policy")

    if changes.get("ip_allowlist"):
        changes["allowed_ips"] = _with_caller(request, changes.get("allowed_ips"))

    try:
        flags.set_flags(changes, actor=request.user.get_username())
    except flags.PolicyError as exc:
        return Response({"detail": str(exc), "code": "policy_refused"}, status=400)
    except ValidationError as exc:
        return Response({"detail": "; ".join(exc.messages)}, status=400)

    return Response(_state(request))


def _with_caller(request, raw) -> str:
    """The submitted list, plus whoever is submitting it."""
    import ipaddress

    from apps.accounts.sessions import client_ip

    current = flags.policy()["allowed_ips"] if raw is None else str(raw)
    ip = client_ip(request)
    if not ip:
        return current
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        # Nothing useful to add, and adding it would make the list unparseable.
        return current
    if any(address in network for network in flags.parse_networks(current)):
        return current
    return "\n".join(filter(None, [current.strip(), ip]))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def events_view(request):
    try:
        limit = min(int(request.query_params.get("limit", EVENT_LIMIT)), 500)
    except ValueError:
        limit = EVENT_LIMIT
    return Response({"events": SecurityEventSerializer(recent(limit), many=True).data})


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def step_up_view(request):
    """Confirm the password, and hold the grant for a few minutes."""
    if request.method == "GET":
        return Response(
            {"required": flags.is_on("step_up"), "seconds_left": stepup.remaining(request)}
        )

    values = flags.policy()
    bucket = f"{STEP_UP_BUCKET}:{request.user.get_username()}"
    if values["login_rate_limit"]:
        waiting = ratelimit.locked_for(bucket)
        if waiting:
            return Response(
                {"detail": "too many attempts — wait a moment", "code": "rate_limited",
                 "retry_after": waiting},
                status=429,
            )

    user = authenticate(
        request,
        username=request.user.get_username(),
        password=request.data.get("password", ""),
    )
    if user is None:
        if values["login_rate_limit"]:
            ratelimit.register_failure(
                bucket,
                limit=int(values["login_max_attempts"]),
                window=int(values["login_window_seconds"]),
                lockout=int(values["login_lockout_seconds"]),
            )
        record(SecurityEventKind.STEP_UP_FAILED, request)
        return Response({"detail": "that password is not right"}, status=401)

    ratelimit.clear(bucket)
    stepup.grant(request)
    record(SecurityEventKind.STEP_UP_OK, request)
    return Response({"required": True, "seconds_left": stepup.remaining(request)})


@api_view(["GET"])
@permission_classes([IsAdminUser])
def totp_view(request):
    return Response(totp.device_state(request.user))


@api_view(["POST"])
@permission_classes([IsAdminUser])
def totp_begin(request):
    """Hand back a fresh secret and its QR. Nothing is armed by this."""
    result = totp.begin(request.user)
    return Response(
        {"secret": result["secret"], "uri": result["uri"], "qr_svg": result["qr_svg"]}
    )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def totp_confirm(request):
    """Prove the app holds the secret. Returns the recovery codes, once."""
    try:
        codes = totp.confirm(request.user, str(request.data.get("code", "")))
    except ValueError as exc:
        record(SecurityEventKind.MFA_FAILED, request, detail={"stage": "enrolment"})
        return Response({"detail": str(exc)}, status=400)
    record(SecurityEventKind.MFA_ENROLLED, request)
    return Response({"recovery_codes": codes, **totp.device_state(request.user)})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def totp_acknowledge(request):
    """The operator says the recovery codes are stored. The last gate."""
    totp.acknowledge_recovery(request.user)
    return Response(totp.device_state(request.user))


@api_view(["POST"])
@permission_classes([IsAdminUser])
def totp_disable(request):
    """Remove the second factor. Needs the password, and disarms the switch.

    Disarming rather than refusing: leaving ``two_factor`` on with no enrolled
    device would demand a code at the next sign-in that nobody can produce,
    which is the lock-out this layer is built to avoid.
    """
    user = authenticate(
        request,
        username=request.user.get_username(),
        password=request.data.get("password", ""),
    )
    if user is None:
        return Response({"detail": "that password is not right"}, status=401)

    totp.disable(request.user)
    if flags.is_on("two_factor"):
        flags.set_flags({"two_factor": False}, actor=request.user.get_username())
    record(SecurityEventKind.MFA_DISABLED, request)
    return Response(_state(request))


@api_view(["POST"])
@permission_classes([IsAdminUser])
def trusted_forget(request):
    """Forget every remembered browser — the next sign-in asks for a code again."""
    count = totp.forget_all(request.user)
    response = Response({"forgotten": count, **totp.device_state(request.user)})
    totp.forget(request.user, request, response)
    return response


@api_view(["GET"])
@permission_classes([AllowAny])
def csp_view(request):
    """Which Content-Security-Policy header the panel should be sending.

    Read by the Nuxt server, which is what actually renders the HTML — a policy
    on a JSON API response protects nothing, because there is no document there
    for a browser to apply it to.
    """
    mode = str(flags.policy()["csp_mode"])
    header = csp.header_for(mode)
    return Response(
        {
            "mode": mode,
            "header": header[0] if header else "",
            "value": header[1] if header else "",
        }
    )
