"""The inbound endpoint, and the staff-only surface that configures it.

Two audiences and two security models in one file, which is worth stating
plainly because the split is the whole design:

``receive`` is the **only** unauthenticated write endpoint on this platform.
It has no session, no CSRF token and no same-origin check, because the caller
is a machine elsewhere. What stands in their place is the token in the path
(who), the HMAC over the raw body (and it really was them), the timestamp
inside the signed material (and not a replay), and the unique constraint on
``SignalEvent.signal_id`` (and not a duplicate). It is exempt from CSRF by
necessity, and exempt from nothing else.

Everything else here is ordinary ``IsAdminUser`` DRF, and the secret is
write-only across all of it: shown once at creation, never again, fingerprint
only thereafter — the same contract exchange credentials and the Telegram token
already have.

**What a refusal is allowed to say.** A bad signature gets a flat
``invalid signature`` with no hint about which of the four checks failed, and an
unknown token gets the same 404 as a disabled one. A caller who cannot
authenticate learns nothing about whether the token exists, whether the source
is on, or which bot is behind it. The operator gets the real reason — in
``SignalEvent`` and in the panel, where it is useful and not a probe.
"""

from __future__ import annotations

import hashlib
import json
import logging

from asgiref.sync import sync_to_async
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.logging.utils import system_log
from apps.signals import auth, service
from apps.signals.models import SignalEvent, SignalSource, Verdict
from apps.signals.payload import SignalRejected, parse

logger = logging.getLogger(__name__)

#: A body larger than this is not a trade signal. Read before parsing so a
#: multi-megabyte POST cannot be turned into JSON just to be rejected.
MAX_BODY_BYTES = 16 * 1024


def _not_found() -> JsonResponse:
    """One answer for unknown, disabled, and secretless. See the module note."""
    return JsonResponse({"detail": "unknown signal endpoint"}, status=404)


@sync_to_async
def _source(token: str) -> SignalSource | None:
    source = (
        SignalSource.objects.select_related("bot")
        .filter(token=token, enabled=True)
        .first()
    )
    if source is None or not source.has_secret:
        return None
    return source


@sync_to_async
def _record(
    source: SignalSource,
    *,
    signal_id: str,
    verb: str,
    verdict: str,
    code: str,
    detail: str,
    payload: dict,
    addr: str,
) -> SignalEvent | None:
    """Write the delivery down. ``None`` means this one is a duplicate.

    The insert *is* the duplicate check — the unique constraint on
    ``(source, signal_id)`` decides it, not a preceding ``exists()`` query,
    because two deliveries racing each other would both pass that query.
    """
    source.last_seen_at = timezone.now()
    source.save(update_fields=["last_seen_at"])
    try:
        return SignalEvent.objects.create(
            source=source,
            signal_id=signal_id,
            verb=verb,
            verdict=verdict,
            code=code,
            detail=detail[:4000],
            payload=payload,
            remote_addr=addr,
        )
    except IntegrityError:
        return None


@sync_to_async
def _settle(event: SignalEvent, outcome: service.Outcome) -> None:
    event.verdict = outcome.verdict
    event.code = outcome.code
    event.detail = outcome.detail[:4000]
    event.actions = outcome.actions or []
    event.run_id = outcome.run_id
    event.save(update_fields=["verdict", "code", "detail", "actions", "run"])
    if outcome.accepted:
        SignalSource.objects.filter(id=event.source_id).update(
            last_accepted_at=timezone.now()
        )


@csrf_exempt
@require_POST
async def receive(request: HttpRequest, token: str) -> JsonResponse:
    """One delivery from an external strategy.

    Ordered so that nothing expensive runs for an unauthenticated caller: the
    source lookup and the signature check come before JSON parsing, and JSON
    parsing comes before anything that touches the bot or an exchange.
    """
    source = await _source(token)
    if source is None:
        return _not_found()

    body = request.body
    if len(body) > MAX_BODY_BYTES:
        return JsonResponse({"detail": "payload too large"}, status=413)

    addr = auth.client_ip(request.META)
    if not auth.ip_allowed(addr, source.allowed_ips or []):
        await _reject_unauthenticated(source, addr, "ip_not_allowed", f"from {addr}")
        return _not_found()

    if source.require_signature:
        try:
            await sync_to_async(_verify)(source, body, request.META)
        except auth.SignatureInvalid as exc:
            await _reject_unauthenticated(source, addr, exc.code, str(exc))
            # Deliberately uninformative — the operator gets exc.code, the
            # caller gets the fact and nothing more.
            return JsonResponse({"detail": "invalid signature"}, status=401)

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        return JsonResponse({"detail": "body is not valid JSON"}, status=400)

    # Past this line the caller is authenticated, so every outcome is recorded
    # against a real SignalEvent and every refusal says what was actually wrong.
    signal_id = _signal_id(payload, body)
    try:
        signal = parse(payload, expected_symbol=source.bot.symbol)
    except SignalRejected as exc:
        await _record(
            source,
            signal_id=signal_id,
            verb="",
            verdict=Verdict.REJECTED,
            code=exc.code,
            detail=str(exc),
            payload=payload if isinstance(payload, dict) else {},
            addr=addr,
        )
        return JsonResponse({"detail": str(exc), "code": exc.code}, status=400)

    event = await _record(
        source,
        signal_id=signal_id,
        verb=signal.verb.value,
        verdict=Verdict.DUPLICATE,
        code="",
        detail="",
        payload=payload,
        addr=addr,
    )
    if event is None:
        # The constraint fired: this exact signal has already been handled.
        # 200, not 409 — a retrying alert system that sees an error retries,
        # and what it would be retrying is the retry.
        return JsonResponse(
            {
                "status": Verdict.DUPLICATE,
                "detail": f"signal {signal_id} was already handled",
            },
            status=200,
        )

    outcome = await service.apply(source=source, signal=signal, event=event)
    await _settle(event, outcome)

    system_log(
        "INFO" if outcome.verdict != Verdict.REJECTED else "WARNING",
        "BOT",
        f"signal {signal.verb.value} on {signal.symbol} from “{source.name}”: "
        f"{outcome.verdict}{f' ({outcome.code})' if outcome.code else ''}",
        source="apps.signals.views",
        error_code=f"signal_{outcome.verdict}",
        context={
            "source": source.name,
            "bot_id": source.bot_id,
            "symbol": signal.symbol,
            "verb": signal.verb.value,
            "verdict": outcome.verdict,
            "code": outcome.code,
            "detail": outcome.detail,
            # Named ``legs`` because that is the only key apps.telegram.sink
            # looks in when it filters hidden accounts out of a notification.
            "legs": _legs(outcome),
        },
    )

    return JsonResponse(
        {
            "status": outcome.verdict,
            "code": outcome.code,
            "detail": outcome.detail,
            "actions": outcome.actions or [],
        },
        status=outcome.http_status,
    )


def _legs(outcome: service.Outcome) -> list[dict]:
    legs: list[dict] = []
    for action in outcome.actions or []:
        legs.extend(action.get("legs", []) or [])
    return legs


def _verify(source: SignalSource, body: bytes, meta: dict) -> None:
    auth.verify(
        secret=source.secret,
        body=body,
        signature=meta.get(auth.SIGNATURE_HEADER),
        timestamp=meta.get(auth.TIMESTAMP_HEADER),
        window_seconds=source.replay_window_seconds,
    )


def _signal_id(payload: object, body: bytes) -> str:
    """The sender's own id, or a digest of what it sent.

    The digest fallback means a sender with no id still cannot replay the same
    body twice — but two genuinely separate signals with identical bodies would
    collide, so the field is documented as the way to avoid that rather than
    guessed at here.
    """
    if isinstance(payload, dict):
        given = str(payload.get("id") or payload.get("signal_id") or "").strip()
        if given:
            return given[:140]
    return "sha256:" + hashlib.sha256(body).hexdigest()[:56]


async def _reject_unauthenticated(
    source: SignalSource, addr: str, code: str, detail: str
) -> None:
    """Record a delivery that failed at the door.

    It gets an event row like any other — an endpoint that only logs what it
    accepted cannot tell the operator that somebody has been posting to it for
    a week. The ``signal_id`` is synthesised from the clock so these never
    collide with each other or with a real one, since an unauthenticated body
    is not something to derive a stable key from.
    """
    stamp = timezone.now().timestamp()
    await _record(
        source,
        signal_id=f"unauth:{code}:{stamp:.6f}",
        verb="",
        verdict=Verdict.REJECTED,
        code=code,
        detail=detail,
        payload={},
        addr=addr,
    )
    logger.warning(
        "signal source %s: delivery refused at the door (%s)",
        source.name,
        code,
        extra={"category": "BOT"},
    )
