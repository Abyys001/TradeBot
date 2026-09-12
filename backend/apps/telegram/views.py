"""The Settings card's Telegram endpoints.

Staff-only, off the routing path. Every write goes through step-up (a no-op
while that switch is off) because muting the notifier is exactly what someone
holding a stolen session would do first — and for the same reason, switching
it off, unlinking, or replacing the token sends one last message to the chat
that is about to stop hearing, so the silence has a visible cause.
"""

from __future__ import annotations

import re
import secrets
from datetime import timedelta

from asgiref.sync import async_to_sync
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.logging.utils import system_log
from apps.security import stepup
from apps.telegram.client import TelegramClient, TelegramError
from apps.telegram.commands import hash_code
from apps.telegram.events import GROUPS
from apps.telegram.messages import LANGUAGES, t
from apps.telegram.models import TelegramBot

#: The service writes a heartbeat every couple of seconds; past this the card
#: says the notifier is not running rather than letting silence read as calm.
HEARTBEAT_FRESH = timedelta(seconds=30)
LINK_TTL = timedelta(minutes=15)
SETTINGS_FIELDS = ("enabled", "recipient_username", "language", "groups")

_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_TOKEN = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


def _now():
    from django.utils import timezone

    return timezone.now()


def state(row: TelegramBot) -> dict:
    now = _now()
    heartbeat = row.last_heartbeat_at
    return {
        "enabled": row.enabled,
        "configured": row.configured,
        "bot_username": row.bot_username,
        "token_fingerprint": row.token_fingerprint,
        "recipient_username": row.recipient_username,
        "linked": row.linked,
        "link_pending": bool(
            row.link_code_hash and row.link_code_expires_at and row.link_code_expires_at > now
        ),
        "language": row.language,
        "groups": [g for g in GROUPS if g in (row.groups or ())],
        "all_groups": list(GROUPS),
        "health": {
            "notifier_running": bool(heartbeat and now - heartbeat < HEARTBEAT_FRESH),
            "last_heartbeat_at": heartbeat,
            "last_sent_at": row.last_sent_at,
            "last_error": row.last_error,
        },
        "updated_at": row.updated_at,
        "updated_by": row.updated_by,
    }


def _refuse(detail: str, code: str = "telegram_refused") -> Response:
    return Response({"detail": detail, "code": code}, status=400)


def _save(row: TelegramBot, request, fields: list[str], changed: list[str]) -> None:
    actor = request.user.get_username()
    row.updated_by = actor
    row.save(update_fields=[*dict.fromkeys(fields), "updated_at", "updated_by"])
    system_log(
        "INFO",
        "ADMIN",
        f"Telegram settings changed: {', '.join(changed)}",
        source="apps.telegram",
        error_code="telegram_changed",
        context={"actor": actor, "changed": changed},
    )


def _farewell(row: TelegramBot, actor: str) -> None:
    """Best effort: the chat hears that it is about to stop hearing."""
    if not (row.configured and row.linked):
        return
    text = _off_text(row, actor)
    try:
        async_to_sync(TelegramClient(row.token).send_message)(row.chat_id, text)
    except TelegramError:
        pass


def _off_text(row: TelegramBot, actor: str) -> str:
    from html import escape

    if row.language == "fa":
        return f"🟠 اعلان‌های این گفتگو توسط <b>{escape(actor)}</b> قطع شد."
    return f"🟠 Notifications to this chat were turned off by <b>{escape(actor)}</b>."


def _unlink(row: TelegramBot) -> list[str]:
    row.chat_id = None
    row.enabled = False
    row.link_code_hash = ""
    row.link_code_expires_at = None
    return ["chat_id", "enabled", "link_code_hash", "link_code_expires_at"]


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def settings_view(request):
    row = TelegramBot.load()
    if request.method == "GET":
        return Response(state(row))

    changes = dict(request.data or {})
    unknown = sorted(set(changes) - set(SETTINGS_FIELDS))
    if not changes or unknown:
        return _refuse(f"unknown or empty change: {', '.join(unknown)}")
    stepup.enforce(request, action="telegram")

    fields: list[str] = []
    changed: list[str] = []

    if "recipient_username" in changes:
        name = str(changes["recipient_username"] or "").strip().lstrip("@")
        if name and not _USERNAME.match(name):
            return _refuse("a Telegram username is 5–32 letters, digits or underscores")
        if name.lower() != row.recipient_username.lower():
            _farewell(row, request.user.get_username())
            row.recipient_username = name
            fields += ["recipient_username", *_unlink(row)]
            changed.append("recipient_username")

    if "language" in changes:
        if changes["language"] not in LANGUAGES:
            return _refuse("language must be en or fa")
        row.language = changes["language"]
        fields.append("language")
        changed.append("language")

    if "groups" in changes:
        groups = changes["groups"]
        if not isinstance(groups, list) or not set(groups) <= set(GROUPS):
            return _refuse(f"groups must be a list drawn from {', '.join(GROUPS)}")
        row.groups = [g for g in GROUPS if g in groups]
        fields.append("groups")
        changed.append("groups")

    if "enabled" in changes:
        on = changes["enabled"]
        if not isinstance(on, bool):
            return _refuse("enabled must be true or false")
        if on and not (row.configured and row.linked):
            return _refuse("save a bot token and link your chat before switching this on")
        if on != row.enabled:
            if on:
                # Begin at the head: what happened while it was off stays in /logs.
                row.log_cursor = None
                fields.append("log_cursor")
            else:
                _farewell(row, request.user.get_username())
            row.enabled = on
            fields.append("enabled")
            changed.append("enabled")

    if fields:
        _save(row, request, fields, changed)
    return Response(state(row))


@api_view(["POST"])
@permission_classes([IsAdminUser])
def token_view(request):
    """Validate with ``getMe`` before storing; an empty token removes it."""
    token = str((request.data or {}).get("token") or "").strip()
    stepup.enforce(request, action="telegram")
    row = TelegramBot.load()
    actor = request.user.get_username()

    if not token:
        _farewell(row, actor)
        row.token_encrypted = row.token_fingerprint = row.bot_username = ""
        row.update_offset = 0
        cleared = ["token_encrypted", "token_fingerprint", "bot_username", "update_offset"]
        _save(row, request, [*cleared, *_unlink(row)], ["token"])
        return Response(state(row))

    if not _TOKEN.match(token):
        return _refuse("that does not look like a BotFather token", "token_invalid")
    try:
        me = async_to_sync(TelegramClient(token).get_me)()
    except TelegramError as exc:
        return _refuse(f"Telegram refused the token: {exc.description}", "token_invalid")

    fields = ["bot_username"]
    row.bot_username = str(me.get("username") or "")
    if row.configured and row.token != token:
        _farewell(row, actor)
    if not row.configured or row.token != token:
        # A different bot cannot write to the chat the old one was linked to.
        row.set_token(token)
        row.update_offset = 0
        fields += ["token_encrypted", "token_fingerprint", "update_offset", *_unlink(row)]
    _save(row, request, fields, ["token"])
    return Response(state(row))


@api_view(["POST"])
@permission_classes([IsAdminUser])
def link_view(request):
    stepup.enforce(request, action="telegram")
    row = TelegramBot.load()
    if not row.configured or not row.bot_username:
        return _refuse("save a bot token first")
    if not row.recipient_username:
        return _refuse("enter the Telegram username that should receive the messages")
    code = secrets.token_urlsafe(18)
    row.link_code_hash = hash_code(code)
    row.link_code_expires_at = _now() + LINK_TTL
    _save(row, request, ["link_code_hash", "link_code_expires_at"], ["link_code"])
    return Response(
        {
            **state(row),
            "link_url": f"https://t.me/{row.bot_username}?start={code}",
            "link_expires_at": row.link_code_expires_at,
        }
    )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def unlink_view(request):
    stepup.enforce(request, action="telegram")
    row = TelegramBot.load()
    _farewell(row, request.user.get_username())
    _save(row, request, _unlink(row), ["chat"])
    return Response(state(row))


@api_view(["POST"])
@permission_classes([IsAdminUser])
def test_view(request):
    row = TelegramBot.load()
    if not (row.configured and row.linked):
        return _refuse("link a chat first", "send_failed")
    try:
        async_to_sync(TelegramClient(row.token).send_message)(row.chat_id, t("test", row.language))
    except TelegramError as exc:
        return _refuse(exc.description, "send_failed")
    return Response({"ok": True})
