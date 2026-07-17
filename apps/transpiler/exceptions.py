"""Transpiler error hierarchy.

All carry an optional (line, column) so the API can point the user at the
offending source location.
"""


class PineError(Exception):
    def __init__(self, message, line=None, column=None):
        self.message = message
        self.line = line
        self.column = column
        loc = f" (line {line}, col {column})" if line is not None else ""
        super().__init__(f"{message}{loc}")


class PineSyntaxError(PineError):
    """Lexing / parsing failure."""


class PineSemanticError(PineError):
    """Scope or type violation found during semantic analysis."""


class UnsupportedFeatureError(PineSemanticError):
    """A parsed-but-rejected construct (e.g. plot/plotshape/bgcolor)."""
