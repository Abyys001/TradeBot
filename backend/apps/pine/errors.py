"""The Pine error hierarchy.

House style is a subsystem-local base carrying a lowercase snake_case ``code``
— ``AdapterError`` (``apps/exchanges/base.py``), ``SizingRejection``
(``apps/trading/sizing.py``). ``PineError`` follows it and **adds ``span``**,
because this is the first subsystem here whose errors point at a place in a
document: the editor underlines a character range, and a chart marker in the
backtest report links back to the line that drew it. That is an extension of the
existing convention, not a second one.
"""

from __future__ import annotations

from apps.pine.tokens import Span


class PineError(Exception):
    """Base class. Every Pine failure surfaces as one of these."""

    #: Short, stable label used in messages and in the panel's error list.
    kind = "error"

    def __init__(self, message: str, *, code: str, span: Span | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.span = span

    def __str__(self) -> str:
        if self.span is None:
            return self.message
        return f"line {self.span.line}, col {self.span.col}: {self.message}"

    def as_dict(self) -> dict:
        """The wire shape the editor consumes. Spans are 1-based, as they read."""
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "span": self.span.as_dict() if self.span else None,
        }


class PineSyntaxError(PineError):
    """The text is not Pine: a bad token, a bad indent, a missing bracket."""

    kind = "syntax"


class PineNameError(PineError):
    """A name that is not defined, or is used before it is."""

    kind = "name"


class PineTypeError(PineError):
    """An argument shape the language allows but this platform cannot execute."""

    kind = "type"


class PineUnsupported(PineError):
    """Inside Pine, outside the v1 subset (Q24). Rejected by name, never ignored."""

    kind = "unsupported"


class PineRuntimeError(PineError):
    """Raised while a bar is being evaluated. Q25 stops the bot on the first one."""

    kind = "runtime"


class PineWarning:
    """Not an error: the script loads and runs, but something in it was *changed*.

    Q20 and Q24 both hinge on the same rule — a script that quietly does not do
    what it says is worse than one that will not load. Everything the platform
    ignores or reinterprets (a script's ``qty``, a ``varip`` under Q23's
    confirmed-bars-only rule) therefore leaves one of these, and the panel shows
    every one of them at upload time.
    """

    __slots__ = ("message", "code", "span")

    kind = "warning"

    def __init__(self, message: str, *, code: str, span: Span | None = None) -> None:
        self.message = message
        self.code = code
        self.span = span

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"PineWarning({self.code}, {self.message!r})"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "span": self.span.as_dict() if self.span else None,
        }
