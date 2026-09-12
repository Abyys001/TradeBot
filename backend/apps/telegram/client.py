"""The Bot API, as three calls.

The token is part of the URL path (``/bot<token>/sendMessage``), so anything
that prints a URL prints the credential. Three things keep it in:

* errors raised from here carry Telegram's own ``description`` or the transport
  error's class name, never the request, and are raised ``from None`` so no
  chained traceback carries it either;
* ``apps.logging.handlers._redact`` rewrites ``bot<id>:<secret>`` wherever it
  appears, on the database handler and — through ``RedactFilter`` — the console,
  which is where httpx logs every request URL at INFO;
* ``trust_env=False``, so a shell proxy nobody chose never sees the path.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from django.conf import settings

from apps.logging.handlers import _redact

logger = logging.getLogger(__name__)

API = "https://api.telegram.org"

#: Telegram's hard limit is 4096 characters per message; the margin leaves room
#: for the continuation mark.
MESSAGE_LIMIT = 4000


class TelegramError(Exception):
    def __init__(
        self, description: str, *, status: int | None = None, retry_after: float | None = None
    ) -> None:
        super().__init__(_redact(description))
        self.description = _redact(description)
        self.status = status
        self.retry_after = retry_after


def telegram_proxy() -> str | None:
    """``TELEGRAM_PROXY`` only — same rule as ``rest.exchange_proxy``, same reasons."""
    candidate = (settings.TELEGRAM.get("PROXY") or "").strip()
    if not candidate:
        return None
    if candidate.startswith("socks://"):
        candidate = "socks5://" + candidate[len("socks://") :]
    try:
        httpx.Proxy(candidate)
    except (ValueError, TypeError):
        logger.warning("TELEGRAM_PROXY is not a usable proxy URL; connecting directly")
        return None
    return candidate


def split(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Break on blank lines where possible, so one event is never cut in half."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
        while len(block) > limit:
            parts.append(block[:limit])
            block = block[limit:]
        current = block
    if current:
        parts.append(current)
    return parts


class TelegramClient:
    #: Tests replace this with an ``httpx.MockTransport``.
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self, token: str, *, timeout: float = 10.0) -> None:
        self._token = token
        self._timeout = timeout

    async def call(
        self, method: str, payload: dict[str, Any] | None = None, *, timeout: float | None = None
    ) -> Any:
        wait = timeout or self._timeout
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(wait, connect=min(wait, 5.0)),
                trust_env=False,
                proxy=None if self.transport else telegram_proxy(),
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{API}/bot{self._token}/{method}", json=payload or {}
                )
        except httpx.HTTPError as exc:
            raise TelegramError(f"network error ({type(exc).__name__})") from None
        try:
            body = response.json()
        except ValueError:
            status = response.status_code
            raise TelegramError(f"HTTP {status}", status=status) from None
        if body.get("ok"):
            return body.get("result")
        raise TelegramError(
            str(body.get("description") or f"HTTP {response.status_code}"),
            status=response.status_code,
            retry_after=(body.get("parameters") or {}).get("retry_after"),
        )

    async def get_me(self) -> dict[str, Any]:
        return await self.call("getMe")

    async def send_message(self, chat_id: int, text: str, *, html: bool = True) -> None:
        for part in split(text):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": part,
                "disable_web_page_preview": True,
            }
            if html:
                payload["parse_mode"] = "HTML"
            await self.call("sendMessage", payload)

    async def get_updates(self, offset: int, *, wait: int = 20) -> list[dict[str, Any]]:
        # The HTTP timeout has to outlast the long poll, or every quiet poll
        # would end as a network error.
        return await self.call(
            "getUpdates",
            {"offset": offset, "timeout": wait, "allowed_updates": ["message"]},
            timeout=wait + 10,
        )
