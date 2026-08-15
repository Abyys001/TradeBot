"""The fan-out engine (spec §4).

One admin action becomes N independent per-account tasks, run concurrently with
a hard per-task deadline. The contract this module exists to guarantee:

  - one account's failure never blocks, delays, or aborts another
  - every leg is dispatched within FANOUT_TIMEOUT_SECONDS (default 4.0, Q19)
  - a leg that overruns is abandoned, not awaited

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
        logger.warning("fanout leg timed out account=%s after %.0fms", account_id, elapsed)
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
        logger.warning("fanout leg failed account=%s: %s", account_id, exc)
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
