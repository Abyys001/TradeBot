"""``python manage.py pine_check <file>`` — parse and validate one strategy.

The Phase 8 editor in miniature, and deliberately so: it renders exactly what
the ``validate`` endpoint returns, so if the command says a script is fine and
the panel says it is not, one of them is wrong rather than both being right
about different things.

A Django command is by definition a Django import, which is why this file sits
under ``apps/pine/management/`` — the subtree the purity test skips. It holds no
logic: everything it prints comes from ``apps.pine.validate``.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.pine import ast_nodes as ast
from apps.pine.validate import validate


class Command(BaseCommand):
    help = "Parse and validate a Pine v5 strategy against the v1 subset (Q24)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("path", help="path to a .pine file")
        parser.add_argument(
            "--ast", action="store_true", help="print the parsed tree instead of a summary"
        )

    def handle(self, *args, **options) -> None:
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"no such file: {path}")
        source = path.read_text(encoding="utf-8")

        from apps.bots.config import limits

        result = validate(source, limits=limits())

        for warning in result.warnings:
            where = f"{warning.span.line}:{warning.span.col}" if warning.span else "-"
            self.stderr.write(
                self.style.WARNING(f"warning {where} [{warning.code}] {warning.message}")
            )
        for error in result.errors:
            where = f"{error.span.line}:{error.span.col}" if error.span else "-"
            self.stderr.write(self.style.ERROR(f"error {where} [{error.code}] {error.message}"))

        if not result.ok:
            raise CommandError(f"{path.name}: {len(result.errors)} error(s)")

        if options["ast"] and result.program is not None:
            self.stdout.write(_render(result.program))
            return

        self.stdout.write(f"nodes: {result.node_count}")
        self.stdout.write(f"ta call sites: {result.ta_call_sites}")
        for spec in result.inputs:
            self.stdout.write(f"input {spec.name} ({spec.kind}) = {spec.default!r}  {spec.title}")
        self.stdout.write(self.style.SUCCESS(f"{path.name}: valid Pine v5 for this platform"))


def _render(node: ast.Node, depth: int = 0) -> str:
    label = type(node).__name__
    detail = ""
    for field in ("name", "attr", "op", "value", "target", "targets", "params", "var"):
        if hasattr(node, field):
            detail = f" {getattr(node, field)!r}"
            break
    lines = [f"{'  ' * depth}{label}{detail}  @{node.span.line}:{node.span.col}"]
    lines.extend(_render(child, depth + 1) for child in ast.children(node))
    return "\n".join(lines)
