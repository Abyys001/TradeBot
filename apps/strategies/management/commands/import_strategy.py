"""Import a Pine strategy from a ``.pine`` file, validating it on creation.

Example:
    python manage.py import_strategy --pine strat.pine --name "Test" \
        --symbol BTC --timeframe 1h
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.strategies.models import Strategy
from apps.transpiler.engine import compile
from apps.transpiler.exceptions import PineError


class Command(BaseCommand):
    help = "Import and validate a Pine strategy from a file."

    def add_arguments(self, parser):
        parser.add_argument("--pine", required=True, help="Path to a .pine source file")
        parser.add_argument("--name", required=True)
        parser.add_argument("--symbol", required=True)
        parser.add_argument("--timeframe", default="1h")
        parser.add_argument("--user", default=None, help="username (default: first user)")
        parser.add_argument("--credential-id", type=int, default=None)

    def handle(self, *args, **opts):
        from apps.accounts.models import User
        from apps.credentials.models import ExchangeCredential

        path = Path(opts["pine"])
        if not path.exists():
            raise CommandError(f"file not found: {path}")
        source = path.read_text()

        if opts["user"]:
            try:
                user = User.objects.get(username=opts["user"])
            except User.DoesNotExist as exc:
                raise CommandError(f"no user {opts['user']!r}") from exc
        else:
            user = User.objects.order_by("id").first()
            if user is None:
                raise CommandError("no users exist; create one first")

        cred_qs = ExchangeCredential.objects.filter(user=user)
        if opts["credential_id"]:
            credential = cred_qs.filter(pk=opts["credential_id"]).first()
        else:
            credential = cred_qs.order_by("id").first()
        if credential is None:
            raise CommandError(f"user {user} has no exchange credential; create one first")

        try:
            compile(source)
        except PineError as exc:
            raise CommandError(f"Pine validation failed: {exc}") from exc

        strategy = Strategy.objects.create(
            user=user,
            credential=credential,
            name=opts["name"],
            type="pine",
            symbol=opts["symbol"],
            timeframe=opts["timeframe"],
            source=source,
            validation_status="ok",
        )
        self.stdout.write(
            self.style.SUCCESS(f"created Strategy<{strategy.id}> {strategy.name} (validation_status=ok)")
        )
