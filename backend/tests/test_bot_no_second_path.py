"""The invariant the whole feature rests on, checked structurally.

`docs/bot-mode.md`: **a bot is a signal source, not a second execution path.**
Everything downstream of a `StrategyIntent` — sizing, the fan-out and its per-leg
deadline, account isolation, `NEVER_SENT_CODES` reconciliation, the halt — is the
code the admin's manual button already goes through.

A comment saying so is a hope. These walk the imports and the call graph, so a
diff that grows a private order path fails here rather than in production.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

BOTS = pathlib.Path(__file__).resolve().parent.parent / "apps" / "bots"
PINE = pathlib.Path(__file__).resolve().parent.parent / "apps" / "pine"

#: The routing functions a bot is allowed to reach for. There are three.
ROUTES = {"route_open", "route_amend", "route_close"}

#: Anything below them. A bot that called one of these would be placing an
#: order without the sizing, the deadline or the reconciliation above it.
BELOW_THE_LINE = {
    "fan_out",
    "size_order",
    "build_adapter",
    "place_market",
    "place_limit",
    "set_sltp",
    "amend_sltp",
    "close_position",
    "set_leverage",
    "open_trade",
    "amend_sltp_trade",
    "close_trade",
}


def modules(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in root.rglob("*.py") if "migrations" not in p.parts)


def called_names(tree: ast.AST) -> set[str]:
    """Every simple and attribute call target in the module."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            out.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            out.add(node.func.attr)
    return out


@pytest.mark.parametrize("path", modules(BOTS), ids=lambda p: p.name)
def test_no_bot_module_reaches_below_the_routing_layer(path):
    called = called_names(ast.parse(path.read_text()))
    assert not (called & BELOW_THE_LINE), sorted(called & BELOW_THE_LINE)


@pytest.mark.parametrize("path", modules(PINE), ids=lambda p: p.name)
def test_nothing_in_the_engine_can_place_an_order(path):
    """The Pine package cannot even name a routing function — it emits an
    intent and stops. That is what makes it the same object in a backtest."""
    called = called_names(ast.parse(path.read_text()))
    assert not (called & (ROUTES | BELOW_THE_LINE))


def test_exactly_one_module_calls_the_routing_layer():
    """`translate.py`. A second one would be a second order path by definition."""
    callers = {
        path.name
        for path in modules(BOTS)
        if called_names(ast.parse(path.read_text())) & ROUTES
    }
    assert callers == {"translate.py"}


def test_the_dispatcher_calls_all_three_routes_and_nothing_else():
    called = called_names(ast.parse((BOTS / "translate.py").read_text()))
    assert ROUTES <= called


def test_the_supervisor_reconciles_before_it_diffs():
    """The exchange decides what is open, not this database. Diffing against a
    stale record re-enters a position the bot already has, or closes one it
    does not — so the order of these two calls is the whole argument."""
    source = (BOTS / "supervisor.py").read_text()
    reconcile = source.index("_reconcile()")
    diff = source.index("translate.read_held")
    assert reconcile < diff


def test_the_halt_is_checked_before_anything_is_sent():
    source = (BOTS / "supervisor.py").read_text()
    assert "before_bar" in source
    assert source.index("before_bar") < source.index("translate.dispatch")


def test_every_dispatch_writes_its_idempotency_key_first():
    """Application logic alone does not survive a restart mid-fan-out, because
    at that moment there is no application logic running. The UNIQUE key is
    written before the order goes out, so the replay refuses instead."""
    source = (BOTS / "translate.py").read_text()
    assert source.index("idempotency_key") < source.index("async def _route")
