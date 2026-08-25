"""Recursive-descent parser for the Pine v5 subset.

Precedence, lowest binding to highest, exactly as ``bot-mode.md`` §1.2 lists it
and as TradingView's own table has it::

    ?:  →  or  →  and  →  ==  !=  →  <  >  <=  >=  →  +  -  →  *  /  %
        →  unary + - not  →  history []  →  call / member access

Two shapes carry more weight than they look like they do:

  ``=`` and ``:=`` produce **different nodes**. See ``ast_nodes.Assign``.

  ``if`` and ``switch`` are parsed as **expressions** that may also stand as
  statements, because Pine allows ``x = if cond`` with an indented body. Parsing
  them as statements only would make that line a syntax error in a language
  where it is idiomatic.
"""

from __future__ import annotations

from apps.pine.ast_nodes import (
    Argument,
    Assign,
    Binary,
    Block,
    BoolLit,
    Break,
    Call,
    ColorLit,
    Continue,
    ExprStmt,
    For,
    ForIn,
    FuncDef,
    If,
    Index,
    Member,
    Name,
    Node,
    NumberLit,
    Program,
    Reassign,
    StringLit,
    Switch,
    SwitchCase,
    Ternary,
    TupleExpr,
    Unary,
    While,
)
from apps.pine.errors import PineSyntaxError
from apps.pine.lexer import declared_version, tokenize
from apps.pine.tokens import Span, Token, TokenKind

#: Pine lets a declaration carry an explicit type — ``var int streak = 0``,
#: ``float x = na`` — optionally behind a ``series``/``simple``/``const``
#: qualifier. All three are *documentation* here: this runtime infers types from
#: the values themselves, so the annotation is parsed and dropped rather than
#: refused, which would reject idiomatic scripts for no benefit.
TYPE_NAMES = frozenset({"int", "float", "bool", "string", "color"})
FORM_QUALIFIERS = frozenset({"series", "simple", "const"})

#: ``a += b`` and friends. Desugared to ``a := a <op> b`` — see ``compound_reassignment``.
COMPOUND_ASSIGN = frozenset({"+=", "-=", "*=", "/=", "%="})

_COMPARISON = {"<", ">", "<=", ">="}
_EQUALITY = {"==", "!="}
_ADDITIVE = {"+", "-"}
_MULTIPLICATIVE = {"*", "/", "%"}


class Parser:
    def __init__(self, tokens: list[Token], *, version: int | None = None) -> None:
        self.tokens = tokens
        self.index = 0
        self.version = version

    # --- token plumbing -----------------------------------------------------

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def peek(self, ahead: int = 0) -> Token:
        return self.tokens[min(self.index + ahead, len(self.tokens) - 1)]

    def at(self, kind: TokenKind, value: str | None = None) -> bool:
        token = self.current
        return token.kind == kind and (value is None or token.value == value)

    def accept(self, kind: TokenKind, value: str | None = None) -> Token | None:
        if self.at(kind, value):
            token = self.current
            self.index += 1
            return token
        return None

    def expect(self, kind: TokenKind, value: str | None = None) -> Token:
        token = self.accept(kind, value)
        if token is None:
            wanted = value or kind.value
            got = self.current.value or self.current.kind.value
            raise PineSyntaxError(
                f"expected {wanted!r} but found {got!r}",
                code="unexpected_token",
                span=self.current.span,
            )
        return token

    def skip_newlines(self) -> None:
        while self.at(TokenKind.NEWLINE):
            self.index += 1

    # --- program ------------------------------------------------------------

    def parse(self) -> Program:
        body: list[Node] = []
        functions: list[FuncDef] = []
        self.skip_newlines()
        while not self.at(TokenKind.EOF):
            statement = self.statement()
            if isinstance(statement, FuncDef):
                functions.append(statement)
            body.append(statement)
            self.skip_newlines()
        span = (
            body[0].span.to(body[-1].span)
            if body
            else Span(1, 1, 1, 1)
        )
        return Program(
            span=span, body=tuple(body), version=self.version, functions=tuple(functions)
        )

    # --- statements ---------------------------------------------------------

    def statement(self) -> Node:
        token = self.current

        if token.kind == TokenKind.KEYWORD:
            if token.value in ("var", "varip"):
                return self.declaration(qualifier=token.value)
            if token.value == "if":
                return ExprStmt(span=token.span, value=self.if_expr())
            if token.value == "switch":
                return ExprStmt(span=token.span, value=self.switch_expr())
            if token.value == "for":
                return self.for_stmt()
            if token.value == "while":
                return self.while_stmt()
            if token.value == "break":
                self.index += 1
                self.end_statement()
                return Break(span=token.span)
            if token.value == "continue":
                self.index += 1
                self.end_statement()
                return Continue(span=token.span)

        if token.kind == TokenKind.OP and token.value == "[":
            return self.tuple_declaration()

        if token.kind == TokenKind.NAME:
            if self._starts_typed_declaration():
                return self.declaration(qualifier="")
            if self._looks_like_funcdef():
                return self.func_def()
            following = self.peek(1)
            if following.kind == TokenKind.OP and following.value == "=":
                return self.declaration(qualifier="")
            if following.kind == TokenKind.OP and following.value == ":=":
                return self.reassignment()
            if following.kind == TokenKind.OP and following.value in COMPOUND_ASSIGN:
                return self.compound_reassignment()

        value = self.expression()
        self.end_statement()
        return ExprStmt(span=value.span, value=value)

    def _starts_typed_declaration(self) -> bool:
        """``int x = 0`` / ``series float y = na`` — a type annotation, not a call."""
        offset = 0
        if self.peek(offset).value in FORM_QUALIFIERS:
            offset += 1
        if self.peek(offset).value not in TYPE_NAMES:
            return False
        return self.peek(offset + 1).kind == TokenKind.NAME

    def end_statement(self) -> None:
        """Consume the statement terminator. EOF and DEDENT both end one."""
        if self.at(TokenKind.NEWLINE):
            self.index += 1
            return
        if self.at(TokenKind.EOF) or self.at(TokenKind.DEDENT):
            return
        # `x = if cond` / `x = switch` end with their block's DEDENT and carry no
        # NEWLINE of their own — the newline was consumed inside the block.
        if self.index and self.tokens[self.index - 1].kind == TokenKind.DEDENT:
            return
        raise PineSyntaxError(
            f"unexpected {self.current.value!r} after the end of a statement",
            code="trailing_token",
            span=self.current.span,
        )

    def _looks_like_funcdef(self) -> bool:
        """``f(a, b) =>`` — scan past the matching ``)`` and look for the arrow."""
        following = self.peek(1)
        if not (following.kind == TokenKind.OP and following.value == "("):
            return False
        depth = 0
        offset = 1
        while True:
            token = self.peek(offset)
            if token.kind == TokenKind.EOF:
                return False
            if token.kind == TokenKind.OP and token.value in "([{":
                depth += 1
            elif token.kind == TokenKind.OP and token.value in ")]}":
                depth -= 1
                if depth == 0:
                    arrow = self.peek(offset + 1)
                    return arrow.kind == TokenKind.OP and arrow.value == "=>"
            offset += 1

    def func_def(self) -> FuncDef:
        name_token = self.expect(TokenKind.NAME)
        self.expect(TokenKind.OP, "(")
        params: list[str] = []
        if not self.at(TokenKind.OP, ")"):
            while True:
                params.append(self.expect(TokenKind.NAME).value)
                if not self.accept(TokenKind.OP, ","):
                    break
        self.expect(TokenKind.OP, ")")
        self.expect(TokenKind.OP, "=>")
        body = self.body_or_expression()
        return FuncDef(
            span=name_token.span.to(body.span),
            name=name_token.value,
            params=tuple(params),
            body=body,
        )

    def declaration(self, *, qualifier: str) -> Assign:
        start = self.current.span
        if qualifier:
            self.index += 1
        # The optional type annotation, dropped after parsing — see TYPE_NAMES.
        if self.current.value in FORM_QUALIFIERS and self.peek(1).kind == TokenKind.NAME:
            self.index += 1
        if self.current.value in TYPE_NAMES and self.peek(1).kind == TokenKind.NAME:
            self.index += 1
        name_token = self.expect(TokenKind.NAME)
        self.expect(TokenKind.OP, "=")
        value = self.expression()
        self.end_statement()
        return Assign(
            span=start.to(value.span),
            targets=(name_token.value,),
            value=value,
            qualifier=qualifier,
        )

    def tuple_declaration(self) -> Assign:
        start = self.expect(TokenKind.OP, "[").span
        targets: list[str] = []
        while True:
            targets.append(self.expect(TokenKind.NAME).value)
            if not self.accept(TokenKind.OP, ","):
                break
        self.expect(TokenKind.OP, "]")
        self.expect(TokenKind.OP, "=")
        value = self.expression()
        self.end_statement()
        return Assign(span=start.to(value.span), targets=tuple(targets), value=value)

    def reassignment(self) -> Reassign:
        name_token = self.expect(TokenKind.NAME)
        self.expect(TokenKind.OP, ":=")
        value = self.expression()
        self.end_statement()
        return Reassign(span=name_token.span.to(value.span), target=name_token.value, value=value)

    def compound_reassignment(self) -> Reassign:
        """``a += b`` — the same node ``a := a + b`` produces.

        Desugaring at the parser keeps the runtime with one reassignment path,
        which is what stops a compound form from acquiring its own scoping or
        ``na`` behaviour by accident.
        """
        name_token = self.expect(TokenKind.NAME)
        op_token = self.peek()
        self.index += 1
        value = self.expression()
        self.end_statement()
        span = name_token.span.to(value.span)
        combined = Binary(
            span=span,
            op=op_token.value[0],
            left=Name(span=name_token.span, name=name_token.value),
            right=value,
        )
        return Reassign(span=span, target=name_token.value, value=combined)

    def for_stmt(self) -> Node:
        start = self.expect(TokenKind.KEYWORD, "for").span

        if self.at(TokenKind.OP, "["):
            self.index += 1
            names: list[str] = []
            while True:
                names.append(self.expect(TokenKind.NAME).value)
                if not self.accept(TokenKind.OP, ","):
                    break
            self.expect(TokenKind.OP, "]")
            self.expect(TokenKind.KEYWORD, "in")
            iterable = self.expression()
            body = self.indented_block()
            return ForIn(
                span=start.to(body.span), vars=tuple(names), iterable=iterable, body=body
            )

        var = self.expect(TokenKind.NAME).value
        if self.accept(TokenKind.KEYWORD, "in"):
            iterable = self.expression()
            body = self.indented_block()
            return ForIn(span=start.to(body.span), vars=(var,), iterable=iterable, body=body)

        self.expect(TokenKind.OP, "=")
        first = self.expression()
        self.expect(TokenKind.KEYWORD, "to")
        last = self.expression()
        step = self.expression() if self.accept(TokenKind.KEYWORD, "by") else None
        body = self.indented_block()
        return For(span=start.to(body.span), var=var, start=first, end=last, step=step, body=body)

    def while_stmt(self) -> While:
        start = self.expect(TokenKind.KEYWORD, "while").span
        cond = self.expression()
        body = self.indented_block()
        return While(span=start.to(body.span), cond=cond, body=body)

    # --- blocks -------------------------------------------------------------

    def indented_block(self) -> Block:
        self.expect(TokenKind.NEWLINE)
        self.skip_newlines()
        start = self.current.span
        self.expect(TokenKind.INDENT)
        body: list[Node] = []
        self.skip_newlines()
        while not self.at(TokenKind.DEDENT) and not self.at(TokenKind.EOF):
            body.append(self.statement())
            self.skip_newlines()
        self.accept(TokenKind.DEDENT)
        if not body:
            raise PineSyntaxError("this block is empty", code="empty_block", span=start)
        return Block(span=start.to(body[-1].span), body=tuple(body))

    def body_or_expression(self) -> Block:
        """A function or ``=>`` arm: either an indented block or one expression."""
        if self.at(TokenKind.NEWLINE):
            return self.indented_block()
        value = self.expression()
        statement = ExprStmt(span=value.span, value=value)
        return Block(span=value.span, body=(statement,))

    # --- expressions --------------------------------------------------------

    def expression(self) -> Node:
        return self.ternary()

    def ternary(self) -> Node:
        cond = self.logical_or()
        if self.accept(TokenKind.OP, "?"):
            then = self.ternary()
            self.expect(TokenKind.OP, ":")
            # Right-associative: `a ? b : c ? d : e` is `a ? b : (c ? d : e)`.
            otherwise = self.ternary()
            return Ternary(
                span=cond.span.to(otherwise.span), cond=cond, then=then, otherwise=otherwise
            )
        return cond

    def logical_or(self) -> Node:
        left = self.logical_and()
        while self.at(TokenKind.KEYWORD, "or"):
            self.index += 1
            right = self.logical_and()
            left = Binary(span=left.span.to(right.span), op="or", left=left, right=right)
        return left

    def logical_and(self) -> Node:
        left = self.equality()
        while self.at(TokenKind.KEYWORD, "and"):
            self.index += 1
            right = self.equality()
            left = Binary(span=left.span.to(right.span), op="and", left=left, right=right)
        return left

    def equality(self) -> Node:
        left = self.comparison()
        while self.current.kind == TokenKind.OP and self.current.value in _EQUALITY:
            op = self.current.value
            self.index += 1
            right = self.comparison()
            left = Binary(span=left.span.to(right.span), op=op, left=left, right=right)
        return left

    def comparison(self) -> Node:
        left = self.additive()
        while self.current.kind == TokenKind.OP and self.current.value in _COMPARISON:
            op = self.current.value
            self.index += 1
            right = self.additive()
            left = Binary(span=left.span.to(right.span), op=op, left=left, right=right)
        return left

    def additive(self) -> Node:
        left = self.multiplicative()
        while self.current.kind == TokenKind.OP and self.current.value in _ADDITIVE:
            op = self.current.value
            self.index += 1
            right = self.multiplicative()
            left = Binary(span=left.span.to(right.span), op=op, left=left, right=right)
        return left

    def multiplicative(self) -> Node:
        left = self.unary()
        while self.current.kind == TokenKind.OP and self.current.value in _MULTIPLICATIVE:
            op = self.current.value
            self.index += 1
            right = self.unary()
            left = Binary(span=left.span.to(right.span), op=op, left=left, right=right)
        return left

    def unary(self) -> Node:
        token = self.current
        if token.kind == TokenKind.OP and token.value in ("+", "-"):
            self.index += 1
            operand = self.unary()
            return Unary(span=token.span.to(operand.span), op=token.value, operand=operand)
        if token.kind == TokenKind.KEYWORD and token.value == "not":
            self.index += 1
            operand = self.unary()
            return Unary(span=token.span.to(operand.span), op="not", operand=operand)
        return self.postfix()

    def postfix(self) -> Node:
        node = self.primary()
        while True:
            if self.at(TokenKind.OP, "["):
                self.index += 1
                offset = self.expression()
                close = self.expect(TokenKind.OP, "]")
                node = Index(span=node.span.to(close.span), obj=node, offset=offset)
                continue
            if self.at(TokenKind.OP, "."):
                self.index += 1
                attr = self.expect(TokenKind.NAME)
                node = Member(span=node.span.to(attr.span), obj=node, attr=attr.value)
                continue
            if self.at(TokenKind.OP, "("):
                node = self.call(node)
                continue
            return node

    def call(self, func: Node) -> Call:
        self.expect(TokenKind.OP, "(")
        args: list[Argument] = []
        if not self.at(TokenKind.OP, ")"):
            while True:
                args.append(self.argument())
                if not self.accept(TokenKind.OP, ","):
                    break
        close = self.expect(TokenKind.OP, ")")
        return Call(span=func.span.to(close.span), func=func, args=tuple(args))

    def argument(self) -> Argument:
        # `length=20` is a named argument; `length == 20` is an expression that
        # happens to start with a name, so only a single `=` names an argument.
        if self.current.kind == TokenKind.NAME:
            following = self.peek(1)
            if following.kind == TokenKind.OP and following.value == "=":
                name_token = self.current
                self.index += 2
                value = self.expression()
                return Argument(
                    span=name_token.span.to(value.span), name=name_token.value, value=value
                )
        value = self.expression()
        return Argument(span=value.span, name="", value=value)

    def primary(self) -> Node:
        token = self.current

        if token.kind == TokenKind.NUMBER:
            self.index += 1
            return NumberLit(span=token.span, value=token.value)
        if token.kind == TokenKind.STRING:
            self.index += 1
            return StringLit(span=token.span, value=token.value)
        if token.kind == TokenKind.COLOR:
            self.index += 1
            return ColorLit(span=token.span, value=token.value)
        if token.kind == TokenKind.NAME:
            self.index += 1
            return Name(span=token.span, name=token.value)
        if token.kind == TokenKind.KEYWORD:
            if token.value in ("true", "false"):
                self.index += 1
                return BoolLit(span=token.span, value=token.value == "true")
            if token.value == "if":
                return self.if_expr()
            if token.value == "switch":
                return self.switch_expr()
        if token.kind == TokenKind.OP and token.value == "(":
            self.index += 1
            inner = self.expression()
            self.expect(TokenKind.OP, ")")
            return inner
        if token.kind == TokenKind.OP and token.value == "[":
            self.index += 1
            items: list[Node] = []
            if not self.at(TokenKind.OP, "]"):
                while True:
                    items.append(self.expression())
                    if not self.accept(TokenKind.OP, ","):
                        break
            close = self.expect(TokenKind.OP, "]")
            return TupleExpr(span=token.span.to(close.span), items=tuple(items))

        raise PineSyntaxError(
            f"unexpected {token.value or token.kind.value!r} here",
            code="unexpected_token",
            span=token.span,
        )

    def if_expr(self) -> If:
        start = self.expect(TokenKind.KEYWORD, "if").span
        cond = self.expression()
        then = self.indented_block()
        otherwise: Node | None = None
        self.skip_newlines()
        if self.at(TokenKind.KEYWORD, "else"):
            self.index += 1
            if self.at(TokenKind.KEYWORD, "if"):
                otherwise = self.if_expr()
            else:
                otherwise = self.indented_block()
        span = start.to(otherwise.span if otherwise is not None else then.span)
        return If(span=span, cond=cond, then=then, otherwise=otherwise)

    def switch_expr(self) -> Switch:
        start = self.expect(TokenKind.KEYWORD, "switch").span
        subject = None if self.at(TokenKind.NEWLINE) else self.expression()
        self.expect(TokenKind.NEWLINE)
        self.skip_newlines()
        self.expect(TokenKind.INDENT)
        cases: list[SwitchCase] = []
        self.skip_newlines()
        while not self.at(TokenKind.DEDENT) and not self.at(TokenKind.EOF):
            case_start = self.current.span
            match = None if self.at(TokenKind.OP, "=>") else self.expression()
            self.expect(TokenKind.OP, "=>")
            body = self.body_or_expression()
            cases.append(SwitchCase(span=case_start.to(body.span), match=match, body=body))
            self.skip_newlines()
        self.accept(TokenKind.DEDENT)
        if not cases:
            raise PineSyntaxError("this switch has no arms", code="empty_switch", span=start)
        return Switch(span=start.to(cases[-1].span), subject=subject, cases=tuple(cases))


def parse(source: str) -> Program:
    """Source text → ``Program``, or ``PineSyntaxError`` with a span."""
    return Parser(tokenize(source), version=declared_version(source)).parse()
