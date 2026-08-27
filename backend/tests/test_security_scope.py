"""`docs/security-plan.md` §1 — the security layer stays off the money path.

The promise the whole design rests on is that switching every control on cannot
change what happens between "the admin clicks" and "the exchange answers". A
promise like that decays into a code-review habit unless something checks it,
so this file checks it the way `test_pine_purity.py` checks the Pine engine's
stdlib-only rule: by walking the imports.

`apps/bots/views.py` is the single carve-out, and a narrow one — it asks for a
step-up grant before promoting a bot to **live**, which is a deliberate,
rare, human action and not a leg of a fan-out.
"""

from __future__ import annotations

import ast as py_ast
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent

#: Everything between the click and the exchange. None of it may import the
#: security layer, because an import is the only way a switch could reach it.
ROUTING_PACKAGES = ("engine", "exchanges", "pine", "trading")

#: `apps.bots` is guarded per file: the supervisor and the translator are the
#: money path, the HTTP view is not.
BOT_CARVE_OUT = ("views.py",)


def routing_modules() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for package in ROUTING_PACKAGES:
        found.extend((BACKEND / "apps" / package).rglob("*.py"))
    found.extend(
        path
        for path in (BACKEND / "apps" / "bots").rglob("*.py")
        if path.name not in BOT_CARVE_OUT
    )
    return sorted(found)


def imported_modules(path: pathlib.Path) -> set[str]:
    tree = py_ast.parse(path.read_text())
    names: set[str] = set()
    for node in py_ast.walk(tree):
        if isinstance(node, py_ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, py_ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_the_walk_finds_the_modules_it_is_meant_to_guard():
    """A rename that emptied the sweep would otherwise pass in silence."""
    found = routing_modules()
    assert len(found) >= 40
    assert any(path.name == "fanout.py" for path in found)
    assert any(path.name == "executor.py" for path in found)
    assert any(path.name == "sizing.py" for path in found)
    assert any(path.name == "supervisor.py" for path in found)


@pytest.mark.parametrize("path", routing_modules(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_the_money_path_does_not_import_the_security_layer(path):
    offending = {name for name in imported_modules(path) if name.startswith("apps.security")}
    assert not offending, f"{path.relative_to(BACKEND)} imports {sorted(offending)}"


@pytest.mark.parametrize("path", routing_modules(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_the_money_path_does_not_read_the_policy_row(path):
    """Not even by name: `SecurityPolicy.objects` would be the same coupling."""
    source = path.read_text()
    for forbidden in ("SecurityPolicy", "security:policy", "securityflags"):
        assert forbidden not in source, f"{path.relative_to(BACKEND)} mentions {forbidden}"


def test_the_one_carve_out_is_the_one_documented():
    """`apps/bots/views.py` may ask for step-up — and only for going live."""
    source = (BACKEND / "apps" / "bots" / "views.py").read_text()
    assert "from apps.security import stepup" in source
    assert "step_up_required" in source
    tree = py_ast.parse(source)
    imported = {
        node.module
        for node in py_ast.walk(tree)
        if isinstance(node, py_ast.ImportFrom) and node.module
    }
    assert {name for name in imported if name.startswith("apps.security")} == {"apps.security"}


def test_the_security_layer_does_not_import_the_money_path():
    """The other direction, which would make the layer un-switchable-off.

    `apps.accounts` is allowed — `client_ip`, `describe_agent` and the session
    rows are where "who is asking" already lives, and reusing them is what
    keeps this layer from growing a second answer to that question.
    """
    for path in sorted((BACKEND / "apps" / "security").rglob("*.py")):
        forbidden = {
            name
            for name in imported_modules(path)
            if any(name.startswith(f"apps.{package}") for package in ROUTING_PACKAGES)
            or name.startswith("apps.bots")
        }
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}"
