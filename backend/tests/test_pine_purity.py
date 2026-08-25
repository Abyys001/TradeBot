"""`docs/bot-plan.md` §2 — `apps/pine/` imports stdlib only.

The runtime must be the **same object** in a backtest and in the live loop. The
mechanism that guarantees it is that the package cannot reach a database, a
cache, a setting or a clock it does not own: there is no configuration for a
backtest to differ on. `test_pine_imports_no_django` is the plan's named test
for this, and it walks the imports rather than trusting a convention.
"""

from __future__ import annotations

import ast as py_ast
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "apps" / "pine"

#: The one carve-out, stated in `apps/pine/__init__.py`: a management command is
#: a Django entry point by definition, and it only wraps what the pure code did.
CARVE_OUT = "management"

FORBIDDEN_ROOTS = {"django", "rest_framework", "channels", "celery", "redis", "asgiref"}


def modules() -> list[pathlib.Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if CARVE_OUT not in p.parts)


def imported_roots(path: pathlib.Path) -> set[str]:
    tree = py_ast.parse(path.read_text())
    roots: set[str] = set()
    for node in py_ast.walk(tree):
        if isinstance(node, py_ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, py_ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_package_has_modules_to_check():
    """A rename that emptied the walk would otherwise pass silently."""
    assert len(modules()) >= 12


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_pine_imports_no_django(path):
    assert not (imported_roots(path) & FORBIDDEN_ROOTS)


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_pine_imports_nothing_from_the_rest_of_the_project(path):
    """Only `apps.pine` itself — an import of `apps.bots` would invert the layering."""
    tree = py_ast.parse(path.read_text())
    for node in py_ast.walk(tree):
        if isinstance(node, py_ast.ImportFrom) and node.module:
            if node.module.startswith("apps."):
                assert node.module.startswith("apps.pine"), node.module


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_reads_the_wall_clock_for_a_bar(path):
    """Bar time comes from the bar. `datetime.now()` would make a replay differ."""
    source = path.read_text()
    for forbidden in ("datetime.now(", "time.time(", "utcnow("):
        assert forbidden not in source, f"{path.name} calls {forbidden}"


#: The modules money actually passes through. A float literal in any of these is
#: a rounding bug waiting for a big enough number; elsewhere (`elapsed_ms`, a
#: literal comparison in the validator) a float is just a float.
MONEY_MODULES = {"ta.py", "series.py", "bar.py", "intent.py", "builtins.py"}


@pytest.mark.parametrize(
    "path", [p for p in modules() if p.name in MONEY_MODULES], ids=lambda p: p.name
)
def test_no_float_literal_where_money_passes(path):
    tree = py_ast.parse(path.read_text())
    for node in py_ast.walk(tree):
        if isinstance(node, py_ast.Constant) and isinstance(node.value, float):
            pytest.fail(f"{path.name}:{node.lineno} has the float literal {node.value!r}")


@pytest.mark.parametrize(
    "path",
    [p for p in modules() if p.name in MONEY_MODULES | {"runtime.py"}],
    ids=lambda p: p.name,
)
def test_no_module_converts_a_price_to_a_float(path):
    """`float(x)` on a Decimal is the one line that silently loses precision.

    `validate.py` is exempt and is the only exemption: its `_literal` reads a
    number out of the *source text* to compare against, and that value reaches
    the panel as an input default rather than an order size — `runtime._coerce_input`
    turns it back into a Decimal before anything arithmetic touches it.
    """
    tree = py_ast.parse(path.read_text())
    for node in py_ast.walk(tree):
        if isinstance(node, py_ast.Call) and isinstance(node.func, py_ast.Name):
            assert node.func.id != "float", f"{path.name}:{node.lineno}"


def test_the_package_imports_with_django_uninitialised():
    """The real proof: import every module in a subprocess with no settings set."""
    import subprocess
    import sys

    names = [f"apps.pine.{p.stem}" for p in modules() if p.stem != "__init__"]
    script = "import importlib\n" + "".join(f"importlib.import_module({n!r})\n" for n in names)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=PACKAGE.parent.parent,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert completed.returncode == 0, completed.stderr
