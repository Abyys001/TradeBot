"""The id that ties every log row of one request together.

``LogEntry.request_id`` existed and was always null: the column was written only
if a caller passed ``request_id`` in ``extra``, and no caller ever did. So the
log could show that an order failed and that a request had returned 500 without
any way to say they were the same event.

A ``ContextVar`` rather than thread-local storage, because the ASGI process runs
sync views in a thread pool *and* async code on the loop — a contextvar is the
one carrier that survives both, and ``asgiref``'s ``sync_to_async`` copies the
context into the worker thread for us.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("log_request_id", default=None)


def new_request_id() -> str:
    """A short id. 12 hex chars is unambiguous within a log page and stays
    readable in a table cell, which a full UUID does not."""
    return uuid.uuid4().hex[:12]


def set_request_id(value: str | None) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def get_request_id() -> str | None:
    return _request_id.get()
