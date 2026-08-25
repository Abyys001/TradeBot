"""Pine Script v5 front end and runtime — **pure**, and deliberately so.

Nothing in this package may import ``django.*`` or ``apps.*``. Everything with
I/O — the bar feed, the backtest, the translator, the risk gate, the supervisor
— lives in ``apps.bots`` instead. That separation is the whole argument of
``docs/bot-mode.md`` Phase 4: the runtime is *the same object* in a backtest and
in a live run, so a divergence between them is a bug rather than a difference of
implementation. A ``settings`` read in here is the first crack in that.

The one exception is ``apps/pine/management/`` — a Django command is by
definition a Django import, and ``pine_check`` holds no logic of its own. The
purity test (``tests/test_pine_purity.py``) walks this package and skips that
subtree for exactly that reason.
"""
