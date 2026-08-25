"""The Pine fixture corpus, and the synthetic bars every Pine test runs on.

Not a ``test_*`` module: ``pytest.ini``'s ``python_files`` would collect it and
find no tests. It is imported by ``test_pine_*.py`` and ``test_bot_*.py`` so that
one definition of "a plausible price series" is shared — a determinism test
comparing two runs is only meaningful if both saw the same bars.
"""

from __future__ import annotations

import pathlib
import random
import re
from decimal import Decimal

from apps.pine.bar import Bar

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "pine"
ACCEPT = FIXTURES / "accept"
REJECT = FIXTURES / "reject"

#: The last line of every ``reject/`` fixture. See ``fixtures/pine/README.md``.
EXPECT_RE = re.compile(r"//@expect code=(?P<code>\S+) line=(?P<line>\d+) col=(?P<col>\d+)")


def accepted() -> list[pathlib.Path]:
    return sorted(ACCEPT.glob("*.pine"))


def rejected() -> list[pathlib.Path]:
    return sorted(REJECT.glob("*.pine"))


def expectation(path: pathlib.Path) -> tuple[str, int, int]:
    """``(code, line, col)`` the fixture says its error must carry."""
    match = EXPECT_RE.search(path.read_text())
    if match is None:  # pragma: no cover - a fixture without one is a bug
        raise AssertionError(f"{path.name} has no //@expect line")
    return match["code"], int(match["line"]), int(match["col"])


def bars(count: int = 250, *, seed: int = 7, start: str = "100") -> list[Bar]:
    """A deterministic random walk, in ``Decimal`` throughout.

    Seeded rather than recorded because no test here asserts a *price* — they
    assert that two runs over the same bars agree, which a generator gives for
    free and a checked-in CSV would only make harder to read.
    """
    rng = random.Random(seed)
    price = Decimal(start)
    out: list[Bar] = []
    for index in range(count):
        close = price + Decimal(str(round(rng.uniform(-1.5, 1.6), 4)))
        high = max(price, close) + Decimal(str(round(rng.uniform(0, 0.8), 4)))
        low = min(price, close) - Decimal(str(round(rng.uniform(0, 0.8), 4)))
        out.append(
            Bar(
                time=index * 900,
                open=price,
                high=high,
                low=low,
                close=close,
                volume=Decimal(str(round(rng.uniform(1, 50), 3))),
            )
        )
        price = close
    return out


def trending(count: int = 120, *, step: str = "1", start: str = "100") -> list[Bar]:
    """A straight line up. Used where a test needs a signal it can predict."""
    price = Decimal(start)
    increment = Decimal(step)
    out: list[Bar] = []
    for index in range(count):
        close = price + increment
        out.append(
            Bar(
                time=index * 900,
                open=price,
                high=max(price, close),
                low=min(price, close),
                close=close,
                volume=Decimal("10"),
            )
        )
        price = close
    return out
