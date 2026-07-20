"""Run the live Tabdeal FAPI probe suite (Master Plan §7, P0 gate).

Read-only by default. Pass ``--live-orders`` to run the full open→SL→DELETE-close
lifecycle at minimum size — use a dedicated, withdrawal-disabled key with a tiny balance.

    python manage.py tabdeal_probe --credential-id 3
    python manage.py tabdeal_probe --credential-id 3 --live-orders --symbol BTC_USDT --quantity 0.001
"""
import os

from django.core.management.base import BaseCommand, CommandError

from apps.exchange.tabdeal_futures import TabdealFuturesClient
from apps.exchange.tabdeal_probe import run_probes


class _EnvCredential:
    """Minimal credential shim so the probe can run from env without a DB row."""

    def __init__(self, api_key: str, api_secret: str):
        self._k, self._s = api_key, api_secret

    def get_api_key(self):
        return self._k

    def get_api_secret(self):
        return self._s


class Command(BaseCommand):
    help = "Probe the live Tabdeal FAPI (8 load-bearing assumptions). Read-only unless --live-orders."

    def add_arguments(self, parser):
        parser.add_argument("--credential-id", type=int, default=None,
                            help="ExchangeCredential pk (exchange=tabdeal).")
        parser.add_argument("--symbol", default="BTC_USDT")
        parser.add_argument("--quantity", type=float, default=None,
                            help="Order size for --live-orders (defaults to symbol minQty).")
        parser.add_argument("--leverage", type=int, default=1)
        parser.add_argument("--live-orders", action="store_true",
                            help="Run the mutating open→SL→DELETE-close lifecycle. Sends REAL orders.")

    def _resolve_client(self, cred_id):
        if cred_id is not None:
            from apps.credentials.models import ExchangeCredential
            try:
                cred = ExchangeCredential.objects.get(pk=cred_id)
            except ExchangeCredential.DoesNotExist as exc:
                raise CommandError(f"credential {cred_id} not found") from exc
            return TabdealFuturesClient(cred)
        key, secret = os.environ.get("TABDEAL_PROBE_API_KEY"), os.environ.get("TABDEAL_PROBE_API_SECRET")
        if not key or not secret:
            raise CommandError(
                "provide --credential-id or set TABDEAL_PROBE_API_KEY/TABDEAL_PROBE_API_SECRET")
        return TabdealFuturesClient(_EnvCredential(key, secret))

    def handle(self, *args, **opts):
        client = self._resolve_client(opts["credential_id"])
        if opts["live_orders"]:
            self.stdout.write(self.style.WARNING(
                "LIVE ORDERS enabled — sending real market orders at minimum size."))
        results = run_probes(
            client, symbol=opts["symbol"], quantity=opts["quantity"],
            leverage=opts["leverage"], live_orders=opts["live_orders"],
        )
        failed = 0
        for r in results:
            style = self.style.SUCCESS if r.ok else self.style.ERROR
            self.stdout.write(style(r.line()))
            failed += 0 if r.ok else 1
        self.stdout.write("")
        summary = f"{len(results) - failed}/{len(results)} probes passed"
        self.stdout.write((self.style.SUCCESS if not failed else self.style.ERROR)(summary))
        if failed:
            raise CommandError(f"{failed} probe(s) failed — do not proceed past P0")
