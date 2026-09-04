"""Source text → tokens, with indentation turned into INDENT/DEDENT.

Pine is whitespace-significant inside ``if``/``for``/``while`` bodies and
function bodies, exactly the way Python is — so the column stack is the same
mechanism Python's own tokenizer uses. Two things suspend it:

  **Brackets.** Inside ``(``/``[``/``{`` a newline is not a statement
  terminator and indentation carries no meaning, which is what lets a long
  ``ta.macd(...)`` argument list wrap.

  **A line indented by a number of spaces that is not a multiple of four.**
  This is TradingView's own line-wrapping rule (``style_guide.md``, "Line
  wrapping"): four spaces open a block, so *any other* indentation continues the
  line above. It is invisible in a diff and hard to put in an error message,
  which is why this lexer used to accept only the explicit form below — but
  every real published strategy wraps its ternary chains and its ``strategy()``
  call this way, and a subset that cannot read them is a subset of nothing.
  Bracket wrapping (above) already worked, and is where v6 lifted the
  indentation restriction entirely (``release_notes.md``, December 2025); this
  is the unparenthesised half, where the restriction still stands in v6 too.

  **A trailing backslash.** ``bot-mode.md`` §1.1 asks for it explicitly. Kept
  alongside the indentation rule rather than replaced by it: it is the spelling
  that survives an editor which reindents on save.

Every token carries a full ``(line, col, end_line, end_col)`` span. That is not
decoration: Phase 4 links a chart marker back to the line that drew it, and the
Phase 8 editor underlines a character range. A span added later would mean
touching every node in ``ast_nodes.py``.
"""

from __future__ import annotations

import re

from apps.pine.errors import PineSyntaxError
from apps.pine.tokens import KEYWORDS, OPERATORS, Span, Token, TokenKind

#: A tab advances to the next multiple of this. Pine's own editor inserts four
#: spaces; a file mixing the two still lines up under this rule.
TAB_WIDTH = 4

_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER_RE = re.compile(r"(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?")
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?")
_VERSION_RE = re.compile(r"^\s*//\s*@version\s*=\s*(\d+)\s*$", re.MULTILINE)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "0": "\0"}


def declared_version(source: str) -> int | None:
    """The ``//@version=N`` annotation, or ``None`` when the script has none.

    Read from the raw text rather than from a token, because it *is* a comment
    and the lexer discards comments. The validator turns a missing or wrong
    version into a located error.
    """
    match = _VERSION_RE.search(source)
    return int(match.group(1)) if match else None


class Lexer:
    def __init__(self, source: str) -> None:
        # Normalise line endings first so a CRLF file does not report every
        # column one to the right of where the editor draws the caret.
        self.source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.pos = 0
        self.line = 1
        self.col = 1
        self.depth = 0
        self.indents: list[int] = [0]
        self.tokens: list[Token] = []
        self.at_line_start = True

    # --- helpers ------------------------------------------------------------

    def _here(self) -> tuple[int, int]:
        return self.line, self.col

    def _span(self, start: tuple[int, int]) -> Span:
        return Span(start[0], start[1], self.line, self.col)

    def _advance(self, count: int) -> str:
        text = self.source[self.pos : self.pos + count]
        for char in text:
            if char == "\n":
                self.line += 1
                self.col = 1
            elif char == "\t":
                self.col += TAB_WIDTH - ((self.col - 1) % TAB_WIDTH)
            else:
                self.col += 1
        self.pos += count
        return text

    def _emit(self, kind: TokenKind, value: str, start: tuple[int, int]) -> None:
        self.tokens.append(Token(kind, value, self._span(start)))

    def _error(self, message: str, start: tuple[int, int], code: str) -> PineSyntaxError:
        return PineSyntaxError(message, code=code, span=self._span(start))

    # --- the pass -----------------------------------------------------------

    def run(self) -> list[Token]:
        while self.pos < len(self.source):
            if self.at_line_start and self.depth == 0:
                self._line_start()
                continue
            char = self.source[self.pos]
            if char == "\n":
                self._newline()
            elif char in " \t":
                self._advance(1)
            elif char == "\\" and self._rest_of_line_blank(self.pos + 1):
                # Explicit continuation: swallow the backslash, the newline, and
                # the next line's leading whitespace, so the logical line runs on.
                self._advance(1)
                while self.pos < len(self.source) and self.source[self.pos] != "\n":
                    self._advance(1)
                if self.pos < len(self.source):
                    self._advance(1)
                while self.pos < len(self.source) and self.source[self.pos] in " \t":
                    self._advance(1)
            elif char == "/" and self.source.startswith("//", self.pos):
                while self.pos < len(self.source) and self.source[self.pos] != "\n":
                    self._advance(1)
            else:
                self._token()

        # A file that does not end in a newline still ends a statement.
        if self.tokens and self.tokens[-1].kind not in (TokenKind.NEWLINE, TokenKind.DEDENT):
            self._emit(TokenKind.NEWLINE, "\n", self._here())
        while len(self.indents) > 1:
            self.indents.pop()
            self._emit(TokenKind.DEDENT, "", self._here())
        self._emit(TokenKind.EOF, "", self._here())
        return self.tokens

    def _rest_of_line_blank(self, index: int) -> bool:
        while index < len(self.source) and self.source[index] in " \t":
            index += 1
        return index >= len(self.source) or self.source[index] == "\n"

    def _newline(self) -> None:
        start = self._here()
        self._advance(1)
        if self.depth:
            # Inside brackets a line break is whitespace, not a statement
            # terminator — a `plot()` call wrapped over four lines is one
            # statement. `run()` already suspends indentation the same way.
            return
        if self.tokens and self.tokens[-1].kind not in (
            TokenKind.NEWLINE,
            TokenKind.INDENT,
            TokenKind.DEDENT,
        ):
            self._emit(TokenKind.NEWLINE, "\n", start)
        self.at_line_start = True

    def _line_start(self) -> None:
        """Measure this line's indentation and emit INDENT/DEDENT for the change.

        A blank line and a comment-only line carry no indentation information —
        they are not statements — so both are skipped without touching the stack.
        """
        start = self._here()
        width = 0
        scan = self.pos
        while scan < len(self.source) and self.source[scan] in " \t":
            if self.source[scan] == "\t":
                width += TAB_WIDTH - (width % TAB_WIDTH)
            else:
                width += 1
            scan += 1
        if scan >= len(self.source) or self.source[scan] == "\n":
            self._advance(scan - self.pos)
            if self.pos < len(self.source):
                self._advance(1)
            return
        if self.source.startswith("//", scan):
            self._advance(scan - self.pos)
            while self.pos < len(self.source) and self.source[self.pos] != "\n":
                self._advance(1)
            if self.pos < len(self.source):
                self._advance(1)
            return

        if width % TAB_WIDTH and self._wraps_previous_line():
            # Line wrapping. Four spaces open a block, so an indentation that is
            # not a multiple of four continues the logical line above — the
            # NEWLINE just emitted did not, in fact, end a statement.
            self._advance(scan - self.pos)
            self.at_line_start = False
            self.tokens.pop()
            return

        self._advance(scan - self.pos)
        self.at_line_start = False
        if width > self.indents[-1]:
            self.indents.append(width)
            self._emit(TokenKind.INDENT, " " * width, start)
            return
        while width < self.indents[-1]:
            self.indents.pop()
            self._emit(TokenKind.DEDENT, "", start)
        if width != self.indents[-1]:
            raise self._error(
                "this line's indentation does not line up with any block above it",
                start,
                "bad_dedent",
            )

    def _wraps_previous_line(self) -> bool:
        """Whether there is a statement above for this line to be a wrap *of*.

        A file whose very first line is indented has nothing to continue, and
        neither has a line following a block boundary — reporting those as bad
        indentation is more useful than silently gluing them to nothing.
        """
        return bool(self.tokens) and self.tokens[-1].kind == TokenKind.NEWLINE

    def _token(self) -> None:
        start = self._here()
        rest = self.source[self.pos :]

        match = _COLOR_RE.match(rest)
        if match:
            self._advance(match.end())
            self._emit(TokenKind.COLOR, match.group(0), start)
            return

        match = _NAME_RE.match(rest)
        if match:
            self._advance(match.end())
            word = match.group(0)
            kind = TokenKind.KEYWORD if word in KEYWORDS else TokenKind.NAME
            self._emit(kind, word, start)
            return

        char = rest[0]
        if char.isdigit() or (char == "." and len(rest) > 1 and rest[1].isdigit()):
            match = _NUMBER_RE.match(rest)
            assert match is not None  # the leading-digit test above guarantees it
            self._advance(match.end())
            self._emit(TokenKind.NUMBER, match.group(0), start)
            return

        if char in "'\"":
            self._string(start)
            return

        for op in OPERATORS:
            if rest.startswith(op):
                self._advance(len(op))
                if op in "([{":
                    self.depth += 1
                elif op in ")]}":
                    if self.depth == 0:
                        raise self._error(f"unmatched '{op}'", start, "unmatched_bracket")
                    self.depth -= 1
                self._emit(TokenKind.OP, op, start)
                return

        raise self._error(f"unexpected character {char!r}", start, "bad_character")

    def _string(self, start: tuple[int, int]) -> None:
        quote = self.source[self.pos]
        self._advance(1)
        out: list[str] = []
        while True:
            if self.pos >= len(self.source) or self.source[self.pos] == "\n":
                raise self._error("unterminated string", start, "unterminated_string")
            char = self.source[self.pos]
            if char == "\\":
                self._advance(1)
                if self.pos >= len(self.source):
                    raise self._error("unterminated string", start, "unterminated_string")
                escape = self.source[self.pos]
                out.append(_ESCAPES.get(escape, escape))
                self._advance(1)
                continue
            if char == quote:
                self._advance(1)
                break
            out.append(char)
            self._advance(1)
        self._emit(TokenKind.STRING, "".join(out), start)


def tokenize(source: str) -> list[Token]:
    """Lex ``source``, raising ``PineSyntaxError`` with a span on the first fault."""
    return Lexer(source).run()
