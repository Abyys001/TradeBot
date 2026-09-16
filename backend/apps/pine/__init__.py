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

The contract this engine is held to
-----------------------------------

**The operator's script is the source of truth, and TradingView is the
reference implementation.** Not "signals that look broadly similar" — the same
fill, on the same bar, at the same price, for the same reason. What that means
in practice, and where each half of it lives:

- **The strategy is executed, never re-interpreted.** The source is lexed,
  parsed and evaluated here, bar by bar. Nothing in the platform special-cases
  a known strategy, recognises a pattern, or substitutes a hand-written
  equivalent of what a script computes. ``explain.py`` reads what a strategy
  does back off its own AST and slices the text out by span, because even a
  *paraphrase* of the logic would be a second opinion about it.

- **TradingView's execution model, not a generic backtester's.** Series
  semantics and history references, ``process_orders_on_close``, and the
  Properties tab honoured as data rather than assumed (``properties.py``:
  initial capital, order size and its unit, pyramiding, commission, and
  slippage counted in the *chart's* mintick, which is not the tick an exchange
  listing reports). Every ``ta.*`` is incremental rather than recomputed per
  bar, the way Pine evaluates it — the difference shows in the fourth decimal
  and, at 100% of equity, compounds forward.

- **Every input the author declared, and only those.** ``inputs.py``
  transcribes each ``input.*`` call site with its type and default; the
  defaults are pinned against the script's own source
  (``tests/test_pine_inputs.py::test_every_default_in_the_published_strategy``
  ``_survives_the_parser``), a submitted value comes through ``validate_values``
  alone, and what the operator set is stored with the bot, so the run that
  trades is the run that was configured. An input that is parsed but never
  reaches the logic is a bug, not a simplification.

- **The historical export is a test set, never a training set.** The admin's
  365-day Strategy Tester run lives in
  ``tests/fixtures/pine/tradingview/mcg_t3_flow_perp/`` and is *replayed*: no
  trade, date, price or count from it appears anywhere in engine code. A
  divergence is traced to the mechanism that caused it and fixed there — that
  is how the chart-mintick slippage and the derived chart timezone were found —
  and where it cannot be fixed it is written down (that directory's README,
  "Discrepancies") rather than smoothed over. Sixty of its eighty-six trades
  predate any bar Hyperliquid will still serve, and are therefore
  **unverified, not assumed correct**.

- **One engine, and nothing forked below it.** The ``StrategyIntent`` this
  runtime emits carries no size and no account. ``apps.bots.translate`` turns
  it into the same ``route_*`` calls a manual order takes, so every account
  with the bot enabled receives it through the one order path — sized by spec
  §5, bounded by ``apps/trading/protection.py``, gated by the same two
  switches. A second path would be a second set of rules about partner capital.
"""
