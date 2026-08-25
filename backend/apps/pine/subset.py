"""The v1 subset (Q24), as data.

One table for what is accepted and one for what is rejected, so that a rejection
cannot ship without the message its error must produce —
``tests/test_pine_validate.py`` parametrizes over ``REJECTIONS`` and asserts each
one's construct name, line and column come back.

Q24's rule is the one Q13 took for prices: **a script that loads and quietly
does not do what it says is worse than a script that will not load.** So nothing
outside this file is silently ignored. Two things are *accepted and reported*
rather than rejected — a script's ``qty`` (Q20) and a ``varip`` declaration
(Q23) — and both raise a warning the panel shows at upload time.

Two deliberate narrowings of "reject everything else" are recorded here rather
than left implicit:

  **Decorative constants inside visual calls.** ``plot``/``plotshape`` and
  friends are recorded, never executed (§1.3), so their arguments have no
  execution effect at all. ``color.*``, ``shape.*``, ``location.*``, ``size.*``
  and ``plot.style_*`` are therefore accepted *only* inside those calls' argument
  lists and rejected by name anywhere else. Without this, nearly every real
  script fails on its first ``color=color.green`` — over a value that cannot
  reach an order.

  **``strategy.exit`` takes percent through ``loss_pct``/``profit_pct``.**
  Q21 says a percent exit wins and a tick/point exit is rejected, but Pine's own
  ``loss=``/``profit=`` are *in ticks*. Accepting those as percent would silently
  give a TradingView script a different meaning here — exactly what Q24 forbids
  — so they are rejected **by name** and a distinct percent spelling is provided.
  Recorded as Q30 in ``questions.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- accepted ---------------------------------------------------------------

#: Built-in series. Every one of these advances per bar and supports ``[n]``.
BUILTIN_SERIES = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "hl2",
        "hlc3",
        "ohlc4",
        "hlcc4",
        "time",
        "bar_index",
    }
)

#: Scalars and namespaces that are values rather than calls.
BUILTIN_VALUES = frozenset({"na", "last_bar_index"})

NAMESPACE_FUNCTIONS: dict[str, frozenset[str]] = {
    "ta": frozenset(
        {
            "sma",
            "ema",
            "rma",
            "wma",
            "vwma",
            "hma",
            "stdev",
            "variance",
            "rsi",
            "atr",
            "tr",
            "macd",
            "bb",
            "bbw",
            "stoch",
            "cci",
            "mom",
            "roc",
            "crossover",
            "crossunder",
            "cross",
            "change",
            "highest",
            "lowest",
            "highestbars",
            "lowestbars",
            "barssince",
            "valuewhen",
            "cum",
            "sum",
            "percentile_linear_interpolation",
            "linreg",
            "rising",
            "falling",
            "pivothigh",
            "pivotlow",
        }
    ),
    "math": frozenset(
        {
            "abs",
            "max",
            "min",
            "pow",
            "sqrt",
            "log",
            "log10",
            "exp",
            "round",
            "floor",
            "ceil",
            "sign",
            "avg",
            "sum",
            "random",
        }
    ),
    "str": frozenset({"tostring", "tonumber", "format", "length", "contains"}),
    "input": frozenset({"int", "float", "bool", "string", "source", "timeframe"}),
    "strategy": frozenset({"entry", "close", "close_all", "exit"}),
}

#: Namespace members that are values, not calls.
NAMESPACE_VALUES: dict[str, frozenset[str]] = {
    "ta": frozenset({"tr"}),
    "strategy": frozenset(
        {
            "position_size",
            "position_avg_price",
            "opentrades",
            "equity",
            "netprofit",
            "long",
            "short",
        }
    ),
    "barstate": frozenset(
        {"isfirst", "islast", "isconfirmed", "isnew", "ishistory", "isrealtime"}
    ),
    "math": frozenset({"pi", "e"}),
}

#: Callable without a namespace.
BARE_FUNCTIONS = frozenset(
    {
        "nz",
        "na",
        "fixnan",
        "input",
        "timestamp",
        "dayofweek",
        "hour",
        "minute",
        "second",
        "year",
        "month",
        "dayofmonth",
        "strategy",
        "max",
        "min",
        "abs",
    }
)

#: Recorded as annotations and never executed (§1.3). Their arguments cannot
#: reach an order, which is what licenses DECORATIVE_NAMESPACES below.
VISUAL_FUNCTIONS = frozenset(
    {"plot", "plotshape", "plotchar", "hline", "fill", "bgcolor", "alert", "alertcondition"}
)

#: Accepted only inside a VISUAL_FUNCTIONS argument list. See the module docstring.
DECORATIVE_NAMESPACES = frozenset({"color", "shape", "location", "size", "plot", "display"})

#: ``strategy.exit`` percent arguments (Q21, and see the module docstring).
EXIT_PERCENT_ARGS = frozenset({"loss_pct", "profit_pct"})

#: ``strategy()`` arguments that are parsed, ignored, and **reported** (Q20).
STRATEGY_IGNORED_ARGS = frozenset(
    {"default_qty_type", "default_qty_value", "initial_capital", "currency", "commission_value",
     "commission_type", "margin_long", "margin_short", "slippage"}
)

#: ``strategy()`` arguments that carry no risk and are simply accepted.
STRATEGY_ACCEPTED_ARGS = frozenset(
    {"title", "shorttitle", "overlay", "format", "precision", "max_bars_back", "scale"}
)


# --- rejected ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rejection:
    """One construct outside the subset, and the message its error must carry."""

    code: str
    #: What the validator matches on: a dotted prefix, a bare name, a keyword,
    #: or a ``strategy()`` / ``strategy.exit`` argument name.
    kind: str
    pattern: str
    message: str


REJECTIONS: tuple[Rejection, ...] = (
    Rejection(
        code="unsupported_security",
        kind="namespace",
        pattern="request",
        message=(
            "multi-timeframe is not supported yet — request.security() and its lookahead "
            "semantics are the single largest source of backtest/live divergence"
        ),
    ),
    Rejection(
        code="unsupported_collections",
        kind="namespace",
        pattern="array",
        message="collections are not supported yet — array.* needs a runtime value model",
    ),
    Rejection(
        code="unsupported_collections",
        kind="namespace",
        pattern="matrix",
        message="collections are not supported yet — matrix.* needs a runtime value model",
    ),
    Rejection(
        code="unsupported_collections",
        kind="namespace",
        pattern="map",
        message="collections are not supported yet — map.* needs a runtime value model",
    ),
    Rejection(
        code="unsupported_drawing",
        kind="namespace",
        pattern="line",
        message="drawing objects are not supported — line.* has no execution effect here",
    ),
    Rejection(
        code="unsupported_drawing",
        kind="namespace",
        pattern="label",
        message="drawing objects are not supported — label.* has no execution effect here",
    ),
    Rejection(
        code="unsupported_drawing",
        kind="namespace",
        pattern="box",
        message="drawing objects are not supported — box.* has no execution effect here",
    ),
    Rejection(
        code="unsupported_drawing",
        kind="namespace",
        pattern="table",
        message="drawing objects are not supported — table.* has no execution effect here",
    ),
    Rejection(
        code="unsupported_drawing",
        kind="namespace",
        pattern="polyline",
        message="drawing objects are not supported — polyline.* has no execution effect here",
    ),
    Rejection(
        code="unsupported_strategy_risk",
        kind="namespace",
        pattern="strategy.risk",
        message=(
            "configure risk limits on the bot, not in the script — strategy.risk.* would "
            "overlap the bot's own auto-stop triggers (Q25) with no way to tell which won"
        ),
    ),
    Rejection(
        code="unsupported_raw_order",
        kind="name",
        pattern="strategy.order",
        message=(
            "use strategy.entry / strategy.close — raw order primitives do not map to §5 "
            "sizing"
        ),
    ),
    Rejection(
        code="unsupported_raw_order",
        kind="name",
        pattern="strategy.cancel",
        message=(
            "use strategy.entry / strategy.close — raw order primitives do not map to §5 "
            "sizing"
        ),
    ),
    Rejection(
        code="unsupported_raw_order",
        kind="name",
        pattern="strategy.cancel_all",
        message=(
            "use strategy.entry / strategy.close — raw order primitives do not map to §5 "
            "sizing"
        ),
    ),
    Rejection(
        code="unsupported_pyramiding",
        kind="strategy_arg",
        pattern="pyramiding",
        message=(
            "pyramiding is not supported — the platform commits 99% of the account on the "
            "first entry, so there is nothing left for a second"
        ),
    ),
    Rejection(
        code="unsupported_intrabar",
        kind="strategy_arg",
        pattern="calc_on_every_tick",
        message=(
            "this platform evaluates on bar close only (Q23) — calc_on_every_tick has no "
            "setting"
        ),
    ),
    Rejection(
        code="unsupported_fill_model",
        kind="strategy_arg",
        pattern="calc_on_order_fills",
        message="calc_on_order_fills describes a fill model that does not exist here",
    ),
    Rejection(
        code="unsupported_fill_model",
        kind="strategy_arg",
        pattern="process_orders_on_close",
        message="process_orders_on_close describes a fill model that does not exist here",
    ),
    Rejection(
        code="unsupported_user_type",
        kind="keyword",
        pattern="type",
        message="user-defined types are not supported yet",
    ),
    Rejection(
        code="unsupported_user_type",
        kind="keyword",
        pattern="method",
        message="user-defined types are not supported yet — method needs a type system",
    ),
    Rejection(
        code="unsupported_user_type",
        kind="keyword",
        pattern="enum",
        message="user-defined types are not supported yet — enum needs a type system",
    ),
    Rejection(
        code="unsupported_import",
        kind="keyword",
        pattern="import",
        message=(
            "libraries are not supported — resolution, versioning and trust are all unsolved "
            "here"
        ),
    ),
    Rejection(
        code="unsupported_import",
        kind="keyword",
        pattern="export",
        message=(
            "libraries are not supported — resolution, versioning and trust are all unsolved "
            "here"
        ),
    ),
    Rejection(
        code="unsupported_exit_ticks",
        kind="exit_arg",
        pattern="loss",
        message=(
            "strategy.exit in ticks or points is rejected (Q21) — converting one needs the "
            "symbol's tick size, which the script cannot see. Use loss_pct= for percent"
        ),
    ),
    Rejection(
        code="unsupported_exit_ticks",
        kind="exit_arg",
        pattern="profit",
        message=(
            "strategy.exit in ticks or points is rejected (Q21) — converting one needs the "
            "symbol's tick size, which the script cannot see. Use profit_pct= for percent"
        ),
    ),
    Rejection(
        code="unsupported_exit_price",
        kind="exit_arg",
        pattern="stop",
        message=(
            "strategy.exit stop= is an absolute price and this platform's SL/TP is a "
            "percentage identical across accounts (§5). Use loss_pct="
        ),
    ),
    Rejection(
        code="unsupported_exit_price",
        kind="exit_arg",
        pattern="limit",
        message=(
            "strategy.exit limit= is an absolute price and this platform's SL/TP is a "
            "percentage identical across accounts (§5). Use profit_pct="
        ),
    ),
    Rejection(
        code="unsupported_exit_trail",
        kind="exit_arg",
        pattern="trail_points",
        message="trailing stops are not supported yet — trail_points is in ticks (Q21)",
    ),
    Rejection(
        code="unsupported_exit_trail",
        kind="exit_arg",
        pattern="trail_offset",
        message="trailing stops are not supported yet — trail_offset is in ticks (Q21)",
    ),
    Rejection(
        code="unsupported_exit_trail",
        kind="exit_arg",
        pattern="trail_price",
        message="trailing stops are not supported yet — trail_price is an absolute price (Q21)",
    ),
)

REJECTED_NAMESPACES = {r.pattern: r for r in REJECTIONS if r.kind == "namespace"}
REJECTED_NAMES = {r.pattern: r for r in REJECTIONS if r.kind == "name"}
REJECTED_STRATEGY_ARGS = {r.pattern: r for r in REJECTIONS if r.kind == "strategy_arg"}
REJECTED_KEYWORDS = {r.pattern: r for r in REJECTIONS if r.kind == "keyword"}
REJECTED_EXIT_ARGS = {r.pattern: r for r in REJECTIONS if r.kind == "exit_arg"}
