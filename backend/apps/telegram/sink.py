"""From ``LogEntry`` rows to Telegram messages.

The log table is the outbox. Every process writes to it already, so tailing it
from a stored cursor sees the backend's, ``possync``'s and the bot runner's
events alike, survives a restart of the notifier by resuming where it stopped,
and adds nothing to the order-routing path.

Two rules that are easy to get wrong:

* **Only settled rows are read.** ``LogEntry.id`` is allocated at insert, and two
  processes can commit ids 100 and 101 in the wrong order. A cursor that jumped
  to 101 before 100 was visible would skip 100 for good, so rows younger than
  ``SETTLE_SECONDS`` wait for the next pass.
* **Hidden accounts never leave.** Telegram is a read surface with no Django
  user behind it, so it gets what any non-``_svc`` reader gets: a row about a
  hidden account is dropped, a fan-out loses its hidden legs *before* anything
  is counted, and a fan-out of nothing but hidden legs is not an event at all.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Max, Q
from django.utils import timezone

from apps.accounts.visibility import _internal_ids
from apps.logging.models import Level, LogEntry
from apps.telegram import messages
from apps.telegram.client import MESSAGE_LIMIT, TelegramClient, TelegramError
from apps.telegram.events import EVENTS, GENERIC, QUIET, Group
from apps.telegram.models import TelegramBot

SETTLE_SECONDS = 3
BATCH = 200
#: Rows scanned to write one backlog summary. Past it the cursor jumps to the
#: head: a notifier that was down for a week is told so, not replayed.
SCAN_CAP = 5000
REPEAT_WINDOW = 600
SERIOUS = (Level.ERROR, Level.CRITICAL)
GENERIC_MESSAGE_CHARS = 600

_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class Outgoing:
    text: str
    #: The cursor once this message is delivered.
    last_id: int


@dataclass(frozen=True, slots=True)
class Batch:
    messages: list[Outgoing]
    #: The cursor once every message is delivered; None when nothing was read.
    scanned_to: int | None


class Repeats:
    """Collapses the same error arriving over and over into one message.

    Registered events are never collapsed — ten trades are ten messages. Only
    the generic "system error" is, because an exchange that is down logs the
    same failure on every poll.
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], tuple[float, int]] = {}

    def admit(self, key: tuple[str, str], now: float) -> int | None:
        """None to suppress; otherwise how many were suppressed before this one."""
        first, suppressed = self._seen.get(key, (0.0, 0))
        if first and now - first < REPEAT_WINDOW:
            self._seen[key] = (first, suppressed + 1)
            return None
        self._seen[key] = (now, 0)
        if len(self._seen) > 500:
            self._seen = {k: v for k, v in self._seen.items() if now - v[0] < REPEAT_WINDOW}
        return suppressed


@dataclass(frozen=True, slots=True)
class _Audience:
    """What the chat may see, read once per pass."""

    hidden_ids: set[int]
    hidden_labels: tuple[str, ...]
    #: Visible account id -> (label, exchange). Most emitters carry only the
    #: id, and a message that says "an account" is one the operator cannot act on.
    names: dict[int, tuple[str, str]]
    groups: frozenset[str]
    language: str


def _audience(row: TelegramBot) -> _Audience:
    from apps.accounts.models import ConnectedAccount

    hidden = _internal_ids()
    labels: list[str] = []
    names: dict[int, tuple[str, str]] = {}
    for pk, label, exchange in ConnectedAccount.objects.values_list("id", "label", "exchange"):
        if pk in hidden:
            if label:
                labels.append(label)
        else:
            names[pk] = (label, exchange)
    return _Audience(hidden, tuple(labels), names, frozenset(row.groups or ()), row.language)


def _name(context: dict[str, Any], account_id: int | None, audience: _Audience) -> None:
    known = audience.names.get(account_id) if account_id is not None else None
    if known is None:
        return
    if not context.get("account"):
        context["account"] = known[0]
    if not context.get("exchange"):
        context["exchange"] = known[1]


def _code(entry: LogEntry) -> str | None:
    """The event this row is, or None when it is not one."""
    code = entry.error_code or ""
    if code in EVENTS:
        return code
    if entry.level in SERIOUS and code not in QUIET:
        return GENERIC
    return None


def _group(code: str) -> str:
    return Group.SYSTEM if code == GENERIC else EVENTS[code].group


def _context(entry: LogEntry, code: str, audience: _Audience) -> dict[str, Any] | None:
    """The row's context with everything hidden removed — or None to drop the row."""
    if entry.account_id is not None and entry.account_id in audience.hidden_ids:
        return None
    raw = entry.context if isinstance(entry.context, dict) else {}
    if code == GENERIC:
        text = entry.message or ""
        # A free-text line is only as safe as its words: a label in it names
        # the account whether or not the row carried the id.
        if any(label in text for label in audience.hidden_labels):
            return None
        context: dict[str, Any] = {
            "account": raw.get("account"),
            "exchange": entry.exchange,
            "category": entry.category,
            "source": entry.source,
            "message": text[:GENERIC_MESSAGE_CHARS],
        }
        _name(context, entry.account_id, audience)
        return context

    context = dict(raw)
    legs = context.get("legs")
    if isinstance(legs, list):
        kept = [
            leg
            for leg in legs
            if isinstance(leg, dict) and leg.get("account_id") not in audience.hidden_ids
        ]
        if legs and not kept:
            return None
        context["legs"] = kept
        for leg in kept:
            _name(leg, leg.get("account_id"), audience)
    if entry.exchange and not context.get("exchange") and not context.get("legs"):
        context["exchange"] = entry.exchange
    _name(context, entry.account_id, audience)
    return context


def _wanted(entry: LogEntry, audience: _Audience) -> tuple[str, dict[str, Any]] | None:
    code = _code(entry)
    if code is None or _group(code) not in audience.groups:
        return None
    context = _context(entry, code, audience)
    if context is None:
        return None
    return code, context


def _pending(cursor: int, now: datetime):
    settled = now - timedelta(seconds=SETTLE_SECONDS)
    return (
        LogEntry.objects.filter(id__gt=cursor, timestamp__lte=settled)
        .filter(Q(error_code__in=list(EVENTS)) | Q(level__in=SERIOUS))
        .order_by("id")
    )


def _head() -> int:
    return LogEntry.objects.aggregate(top=Max("id"))["top"] or 0


def collect(row: TelegramBot, now: datetime, repeats: Repeats) -> Batch:
    """What to send next. Reads only; the cursor moves in ``advance``."""
    if row.log_cursor is None:
        # Just switched on: begin at the head rather than replay history.
        TelegramBot.objects.filter(pk=row.pk, log_cursor__isnull=True).update(log_cursor=_head())
        return Batch([], None)

    pending = _pending(row.log_cursor, now)
    entries = list(pending[:BATCH])
    if not entries:
        return Batch([], None)
    audience = _audience(row)

    if len(entries) > settings.TELEGRAM["BACKLOG_MAX"]:
        return _backlog(pending, audience)

    texts: list[tuple[str, int]] = []
    clock = time.monotonic()
    for entry in entries:
        wanted = _wanted(entry, audience)
        if wanted is None:
            continue
        code, context = wanted
        repeats_before = 0
        if code == GENERIC:
            admitted = repeats.admit((entry.source, entry.error_code or entry.message[:80]), clock)
            if admitted is None:
                continue
            repeats_before = admitted
        texts.append(
            (
                messages.render(
                    code=code,
                    level=entry.level,
                    timestamp=entry.timestamp,
                    context=context,
                    language=audience.language,
                    trade_id=entry.trade_id,
                    repeats=repeats_before,
                ),
                entry.id,
            )
        )
    return Batch(_pack(texts), entries[-1].id)


def _backlog(pending, audience: _Audience) -> Batch:
    """One message counting what was missed, instead of a flood of them."""
    scanned = list(pending[:SCAN_CAP])
    counts: Counter[str] = Counter()
    for entry in scanned:
        wanted = _wanted(entry, audience)
        if wanted is not None:
            counts[wanted[0]] += 1
    last = scanned[-1].id if len(scanned) < SCAN_CAP else pending.aggregate(top=Max("id"))["top"]
    if not counts:
        return Batch([], last)
    language = audience.language
    lines = [f"🟠 {messages.t('backlog', language, n=sum(counts.values()))}"]
    lines += [
        f"• {n}× {messages.escape(messages.title(code, language))}"
        for code, n in counts.most_common()
    ]
    return Batch([Outgoing("\n".join(lines), last)], last)


def _pack(texts: list[tuple[str, int]]) -> list[Outgoing]:
    """Several events per message, so a burst does not run into the rate limit."""
    out: list[Outgoing] = []
    current, last = "", 0
    for text, entry_id in texts:
        joined = f"{current}\n\n{text}" if current else text
        if current and len(joined) > MESSAGE_LIMIT:
            out.append(Outgoing(current, last))
            joined = text
        current, last = joined, entry_id
    if current:
        out.append(Outgoing(current, last))
    return out


def advance(cursor: int, *, sent: bool) -> None:
    values: dict[str, Any] = {"log_cursor": cursor}
    if sent:
        values.update(last_sent_at=timezone.now(), last_error="")
    # ``log_cursor__isnull=False``: if the operator switched the notifier off
    # and on while this pass was sending, the reset to the head wins.
    TelegramBot.objects.filter(pk=1, log_cursor__isnull=False).update(**values)


def record_error(description: str) -> None:
    TelegramBot.objects.filter(pk=1).update(last_error=description[:500])


async def send(client: TelegramClient, chat_id: int, text: str) -> None:
    """Deliver one message, riding out a rate limit and a markup rejection."""
    try:
        await client.send_message(chat_id, text)
    except TelegramError as exc:
        if exc.status == 429 and exc.retry_after:
            await _sleep(float(exc.retry_after))
            await client.send_message(chat_id, text)
        elif exc.status == 400 and "parse" in exc.description.lower():
            # A message Telegram will not parse would otherwise block the cursor
            # forever; the same words without markup still get through.
            await client.send_message(chat_id, messages.unescape(_TAG.sub("", text)), html=False)
        else:
            raise


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(min(seconds, 60.0))


async def drain(client: TelegramClient, row: TelegramBot, repeats: Repeats) -> int:
    """Send everything pending. Returns how many messages went out."""
    batch = await sync_to_async(collect)(row, timezone.now(), repeats)
    for outgoing in batch.messages:
        await send(client, row.chat_id, outgoing.text)
        await sync_to_async(advance)(outgoing.last_id, sent=True)
    if batch.scanned_to is not None:
        await sync_to_async(advance)(batch.scanned_to, sent=False)
    return len(batch.messages)
