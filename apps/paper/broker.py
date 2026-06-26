"""Paper trading broker wrapping SimBroker for live-feed simulation."""
from __future__ import annotations

from decimal import Decimal

from apps.transpiler.runtime.sim_broker import SimBroker, Trade

from .models import PaperTrade


class PaperBroker(SimBroker):
    """SimBroker that persists trades to PaperTrade on finalize."""

    fill_at_next_open = False

    def __init__(self, account, **kwargs):
        super().__init__(**kwargs)
        self.account = account
        self.strategy = account.strategy

    def entry(self, oid, direction, price, bar_index, qty=None, **kwargs):
        super().entry(oid, direction, price, bar_index, qty, **kwargs)
        alert_message = kwargs.get("alert_message")
        if alert_message:
            from apps.integrations.tasks import signum_send_webhook_task

            signum_send_webhook_task.delay(self.account.user_id, alert_message)

    def sync_account(self, mark_price: float) -> None:
        eq = self.equity(mark_price)
        self.account.equity = eq
        self.account.balance = self.cash
        self.account.save(update_fields=["equity", "balance", "updated_at"])

    def _close_trade(self, t: Trade, fill: float, bar_index: int, reason: str = "") -> None:
        super()._close_trade(t, fill, bar_index, reason=reason)
        PaperTrade.objects.create(
            account=self.account,
            side=t.side,
            entry_price=Decimal(str(t.entry_price)),
            exit_price=Decimal(str(t.exit_price)) if t.exit_price is not None else None,
            size=Decimal(str(t.size)),
            pnl=Decimal(str(t.pnl)),
            entry_bar=t.entry_bar,
            exit_bar=t.exit_bar,
        )
