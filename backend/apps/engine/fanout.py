"""The fan-out engine (spec §4).

One admin action becomes N independent per-account tasks, run concurrently with
a hard per-task deadline. The contract this module exists to guarantee:

  - one account's failure never blocks, delays, or aborts another
  - every leg is dispatched within FANOUT_TIMEOUT_SECONDS (default 10.0, Q19)
  - a leg that overruns is abandoned, not awaited — and then re-read from the
    exchange (executor.py _reconcile*) to learn whether it actually landed, so
    an order that executed after the deadline is reported as filled, not failed
  - the same re-read covers *every* failure that could have left an order on
    the exchange, not just the deadline. See ``NEVER_SENT_CODES``.

That is why this is plain asyncio and not Celery: a broker round-trip plus
worker prefetch does not fit inside a per-leg deadline.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from django.conf import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


#: Failure codes that **prove** no order reached the exchange. Everything else
#: is *unconfirmed*: the request may have executed even though the leg failed.
#:
#: The asymmetry is deliberate and the direction matters. A leg is only listed
#: here when the platform can name the moment it stopped — sizing skipped the
#: account (spec §5), the SL/TP resolver refused, the local rate limiter never
#: sent the request, the exchange rejected the credentials outright, or a
#: re-read has since confirmed the account holds nothing. Every other failure —
#: the fan-out deadline, an HTTP read timeout, a 5xx, a reset connection, an
#: unrecognised adapter error — happens with a request already in flight, and
#: cancelling a coroutine cannot unsend it.
#:
#: Treating those as plain failures is what let the panel report "exceeded the
#: deadline" for a position the exchange had already opened.
NEVER_SENT_CODES = frozenset(
    {
        # sizing / policy: the account sat the entry out before place_order
        "non_usdt_balance",
        "no_price",
        "bad_leverage",
        "below_min_qty",
        "below_min_notional",
        "leverage_capped",
        "sl_beyond_liquidation",
        "no_entry",
        # the request was never put on the wire, or the exchange refused it
        # before it could act on it
        "rate_limit_local",
        "auth",
        # the exchange itself answered "there is nothing here"
        "no_position",
        "not_filled",
    }
)


@dataclass(slots=True)
class LegResult(Generic[T]):
    """Outcome of one account's leg. Never raises — failure is data, not control flow."""

    account_id: Any
    ok: bool
    value: T | None = None
    error: str = ""
    error_code: str = ""
    duration_ms: float = 0.0

    @property
    def timed_out(self) -> bool:
        return self.error_code == "timeout"

    @property
    def unconfirmed(self) -> bool:
        """Failed, but the exchange may still have acted on the request.

        The question this answers is not "did it work" but "is it safe to say
        it did not". Only a code in ``NEVER_SENT_CODES`` earns that.
        """
        return not self.ok and self.error_code not in NEVER_SENT_CODES


@dataclass(slots=True)
class FanOutResult(Generic[T]):
    legs: list[LegResult[T]] = field(default_factory=list)
    total_ms: float = 0.0

    @property
    def succeeded(self) -> list[LegResult[T]]:
        return [leg for leg in self.legs if leg.ok]

    @property
    def failed(self) -> list[LegResult[T]]:
        return [leg for leg in self.legs if not leg.ok]

    @property
    def all_ok(self) -> bool:
        return not self.failed

    def within_budget(self, seconds: float | None = None) -> bool:
        budget = seconds if seconds is not None else settings.TRADING["FANOUT_TIMEOUT_SECONDS"]
        return self.total_ms <= budget * 1000


class StopAllActive(Exception):
    """The platform-wide kill switch is on (spec §7)."""


def stop_all_active() -> bool:
    return bool(settings.TRADING["STOP_ALL"])


async def _run_leg(
    account_id: Any,
    op: Callable[[], Awaitable[T]],
    timeout: float,
) -> LegResult[T]:
    started = time.perf_counter()
    try:
        value = await asyncio.wait_for(op(), timeout=timeout)
    except TimeoutError:
        elapsed = (time.perf_counter() - started) * 1000
        logger.warning("fanout leg timed out account=%s after %.0fms", account_id, elapsed, extra={"account_id": account_id, "error_code": "timeout"})
        return LegResult(
            account_id=account_id,
            ok=False,
            error=f"exceeded the {timeout:g}s deadline",
            error_code="timeout",
            duration_ms=elapsed,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - isolation is the whole point
        elapsed = (time.perf_counter() - started) * 1000
        logger.warning("fanout leg failed account=%s: %s", account_id, exc, extra={"account_id": account_id, "error_code": getattr(exc, "code", None) or type(exc).__name__})
        return LegResult(
            account_id=account_id,
            ok=False,
            error=str(exc),
            error_code=getattr(exc, "code", None) or type(exc).__name__,
            duration_ms=elapsed,
        )
    return LegResult(
        account_id=account_id,
        ok=True,
        value=value,
        duration_ms=(time.perf_counter() - started) * 1000,
    )


async def fan_out(
    operations: Sequence[tuple[Any, Callable[[], Awaitable[T]]]],
    *,
    timeout: float | None = None,
    respect_stop_all: bool = True,
) -> FanOutResult[T]:
    """Run every operation concurrently and collect all outcomes.

    ``operations`` is a sequence of ``(account_id, zero-arg coroutine factory)``.
    A factory rather than a coroutine so nothing starts before the gather —
    otherwise the first accounts get a head start and the spread widens.
    """
    if respect_stop_all and stop_all_active():
        raise StopAllActive("STOP_ALL is on — no orders are being routed")

    budget = timeout if timeout is not None else settings.TRADING["FANOUT_TIMEOUT_SECONDS"]
    started = time.perf_counter()

    # return_exceptions=True is belt-and-braces: _run_leg already swallows
    # everything, but a bug in it must still not cancel the sibling legs.
    legs = await asyncio.gather(
        *(_run_leg(account_id, op, budget) for account_id, op in operations),
        return_exceptions=True,
    )

    collected: list[LegResult[T]] = []
    for (account_id, _), leg in zip(operations, legs, strict=True):
        if isinstance(leg, BaseException):
            logger.exception("fanout leg raised out of _run_leg account=%s", account_id)
            collected.append(
                LegResult(
                    account_id=account_id,
                    ok=False,
                    error=str(leg),
                    error_code="engine_error",
                )
            )
        else:
            collected.append(leg)

    return FanOutResult(legs=collected, total_ms=(time.perf_counter() - started) * 1000)
