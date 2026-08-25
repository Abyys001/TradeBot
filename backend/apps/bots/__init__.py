"""Bot mode: everything with I/O around the pure Pine runtime.

``apps.pine`` is the language — lexer, parser, validator, ``ta``, runtime — and
it imports nothing from Django or from this codebase, which is what makes it the
*same object* in a backtest and in a live run. Everything that touches a socket,
the ORM, an exchange or a setting lives here instead: the bar feed, the
backtest, the intent translator, the risk gate, the supervisor, the models and
the views.

**A bot is a signal source, not a second execution path.** Every action a bot
takes goes through ``apps.trading.services.route_open`` / ``route_amend`` /
``route_close`` — the same calls the admin's own button makes — and inherits §5
sizing, the §4 fan-out and its deadline, account isolation, ``NEVER_SENT_CODES``
reconciliation, the §7 halt and §8 history by going through the front door. If a
diff in this package ever adds a second order path it is wrong regardless of
what it does.

Q27 puts two rules on this package and they need reading together. Bots fan out
to hidden accounts **identically** — nothing in the routing path may consult
``ConnectedAccount.hidden`` — and every bot **read** surface **must** filter,
with its own case in ``tests/test_account_access.py``.

So the prohibition is enforced where it means something: ``feed``, ``translate``,
``riskgate``, ``supervisor``, ``recovery``, ``backtest`` and everything in
``apps.pine`` may not import ``apps.accounts.visibility``, exactly as
``apps.engine`` may not. ``views`` and ``serializers`` are the read surface and
must — a rule that forbade them the import would make Q27's second sentence
unsatisfiable. ``tests/test_pine_purity.py`` pins that split module by module,
so the exception is one line in one file rather than a habit.
"""
