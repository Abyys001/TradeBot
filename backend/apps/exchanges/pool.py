"""Warm adapters, one per account (spec §2 isolation, spec §4 deadline).

An adapter is cheap to construct and ruinously expensive to *use* for the first
time. Every fresh instance means:

  - a cold TCP connection and a full TLS handshake to the venue — three round
    trips before the first byte of the first request;
  - on Hyperliquid, the SDK downloading its asset metadata on construction
    (``Info.__init__`` posts ``spotMeta`` and ``meta``), which used to happen
    *twice* because ``Exchange`` builds an ``Info`` of its own.

That is four-plus round trips of pure setup, paid inside the per-leg deadline,
on every single admin action. On a VPS ~150ms from the exchange it is most of a
second spent before the balance call has even started — which is exactly how a
healthy order came back as ``exceeded the 1s deadline``.

So adapters live between actions. **Still one per account**: the HTTP client,
the credentials and the rate limiter stay private to that account, which is the
structural half of the spec §2 isolation guarantee. Nothing is shared between
accounts — what is reused is only an account's own warm connection to its own
venue. A saturated or hung exchange therefore still costs that one account.

Keeping the rate limiter alive is a correctness gain too: a fresh ``TokenBucket``
per action handed every action a full burst, so the local limiter never actually
tracked the exchange's window across a rapid entry → amend → close.

**Invalidation is by credential fingerprint.** Every route re-reads its accounts
from the database, so a re-keyed, re-labelled-testnet or newly-disabled account
is noticed on the next action and its old adapter is closed. Deleting an account
evicts it through a ``post_delete`` signal.

Nothing here is a cache of *answers*. Balances, positions and fills are still
fetched every time; what is cached is the connection they travel over.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from apps.accounts.models import ConnectedAccount
from apps.exchanges.base import ExchangeAdapter
from apps.exchanges.registry import build_adapter

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _Entry:
    adapter: ExchangeAdapter
    #: What the adapter was built from. A change means rebuild, not reuse.
    fingerprint: str
    #: The event loop the adapter's client belongs to. httpx and the SDK bind
    #: their connection pools to a loop, so an adapter built on a loop that has
    #: since gone (Django's async-view bridge under WSGI opens one per request)
    #: must never be handed out again.
    loop: Any


_pool: dict[int, _Entry] = {}


def _fingerprint(account: ConnectedAccount) -> str:
    """Identity of the *connection* this account needs, as an opaque digest.

    Built from the **encrypted** columns, never the decrypted properties. Two
    reasons, and both matter:

    * spec §7 — credentials are decrypted in ``build_adapter`` and nowhere
      else. This module runs on every action and must not become a second place
      key material rests, not even for the length of a hash.
    * it is free. Reading ``account.api_key`` is a Fernet decrypt; the
      ciphertext is already in memory from the row that was just read.

    Fernet output is non-deterministic, so re-saving credentials changes this
    even when the key is the same. That is the safe direction to be wrong in: a
    re-key and a key rotation both rebuild, and neither can leave an adapter
    signing with something the admin has replaced.
    """
    parts = [
        account.exchange,
        account.api_key_encrypted or "",
        account.api_secret_encrypted or "",
        account.api_passphrase_encrypted or "",
        account.wallet_address or "",
        "testnet" if account.testnet else "live",
    ]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _running_loop() -> Any:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def get(account: ConnectedAccount) -> ExchangeAdapter:
    """The warm adapter for this account, building one if there is none.

    Deliberately synchronous and free of ``await``: on a single-threaded event
    loop that makes the lookup-or-build atomic, so two concurrent actions on one
    account cannot each build an adapter and race to warm it. Evicting an entry
    schedules its ``close()`` rather than awaiting it, for the same reason.
    """
    loop = _running_loop()
    fingerprint = _fingerprint(account)
    entry = _pool.get(account.id)

    if entry is not None:
        if entry.fingerprint == fingerprint and entry.loop is loop and loop is not None:
            return entry.adapter
        # Either the credentials changed or the loop it was built on is gone.
        # A stale-loop adapter cannot be closed from here — its client's pool
        # belongs to a loop nobody is running — so it is dropped and left to GC.
        _pool.pop(account.id, None)
        if entry.loop is loop:
            _schedule_close(entry.adapter)

    adapter = build_adapter(account)
    if loop is not None:
        _pool[account.id] = _Entry(adapter=adapter, fingerprint=fingerprint, loop=loop)
    return adapter


def evict(account_id: int) -> None:
    """Drop one account's adapter — a re-key, a disconnect, or a deletion."""
    entry = _pool.pop(account_id, None)
    if entry is not None and entry.loop is _running_loop():
        _schedule_close(entry.adapter)


def _schedule_close(adapter: ExchangeAdapter) -> None:
    """Close in the background: nothing waits on a dead adapter's sockets."""
    try:
        task = asyncio.ensure_future(adapter.close())
    except RuntimeError:  # no running loop — the sockets die with the process
        return
    task.add_done_callback(_swallow)


def _swallow(task: asyncio.Future) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.debug("closing a retired adapter failed", exc_info=task.exception())


async def aclose_all() -> None:
    """Close every pooled adapter. For shutdown and for test isolation."""
    entries = list(_pool.values())
    _pool.clear()
    loop = _running_loop()
    await asyncio.gather(
        *(entry.adapter.close() for entry in entries if entry.loop is loop),
        return_exceptions=True,
    )


def clear() -> None:
    """Forget every adapter without closing it. Only for tests with no loop."""
    _pool.clear()
