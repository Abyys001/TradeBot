"""The Phase 1/2 caps, as a value the pure package can hold.

``apps/pine/`` may not read ``django.conf.settings`` — that would make the
runtime's behaviour depend on a process's environment and quietly break the one
property Phase 4 rests on, that a backtest and a live run are the same object.
So the caps arrive as an argument. ``apps.bots.config.limits()`` builds one of
these from ``settings.BOT``; the defaults here are the same numbers, so the pure
package is usable and testable on its own.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Limits:
    #: Phase 1 — one pathological script must not be able to starve the loop.
    max_script_bytes: int = 65536
    max_ast_nodes: int = 20000
    max_ta_call_sites: int = 200
    #: Phase 1 rejects an unbounded loop; Phase 2 enforces this at runtime too,
    #: because "bounded" is a static judgement and the runtime is where it is
    #: actually true or not.
    max_loop_iterations: int = 10000
    #: Phase 2 — a bounded ring buffer, so a bot running a year on 1m bars does
    #: not grow without limit.
    series_depth: int = 5000
    #: Phase 2 — the runtime shares an event loop with a fan-out that has a
    #: per-leg deadline. A slow script is a latency incident for every account.
    bar_budget_ms: int = 250


DEFAULT_LIMITS = Limits()
