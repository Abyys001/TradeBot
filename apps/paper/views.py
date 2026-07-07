"""Paper trading REST API."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.strategies.models import Strategy

from .models import PaperAccount, PaperTrade
from .tasks import start_paper_task, stop_paper_task


def _get_strategy_account(request, strategy_id: int) -> tuple[Strategy | None, PaperAccount | None]:
    strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
    if not strategy:
        return None, None
    account, _ = PaperAccount.objects.get_or_create(
        user=request.user,
        strategy=strategy,
        defaults={"balance": Decimal("10000"), "equity": Decimal("10000")},
    )
    return strategy, account


class PaperAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, strategy_id: int):
        strategy, account = _get_strategy_account(request, strategy_id)
        if not strategy or not account:
            return Response({"error": "not found"}, status=404)
        return Response(
            {
                "id": account.id,
                "balance": str(account.balance),
                "equity": str(account.equity),
                "is_active": account.is_active,
            }
        )

    def post(self, request, strategy_id: int):
        strategy, account = _get_strategy_account(request, strategy_id)
        if not strategy or not account:
            return Response({"error": "not found"}, status=404)
        start_paper_task.delay(account.id)
        return Response({"ok": True, "id": account.id, "status": "starting"})

    def patch(self, request, strategy_id: int):
        strategy, account = _get_strategy_account(request, strategy_id)
        if not strategy or not account:
            return Response({"error": "not found"}, status=404)
        if account.is_active:
            return Response({"error": "stop paper trading before changing balance"}, status=400)
        balance = request.data.get("balance")
        if balance is None:
            return Response({"error": "balance required"}, status=400)
        try:
            value = Decimal(str(balance))
        except (InvalidOperation, TypeError):
            return Response({"error": "invalid balance"}, status=400)
        account.balance = value
        account.equity = value
        account.save(update_fields=["balance", "equity", "updated_at"])
        return Response({"balance": str(account.balance), "equity": str(account.equity)})

    def delete(self, request, strategy_id: int):
        strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
        if not strategy:
            return Response({"error": "not found"}, status=404)
        account = PaperAccount.objects.filter(user=request.user, strategy=strategy).first()
        if account:
            stop_paper_task.delay(account.id)
        return Response({"ok": True})


class PaperTradesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, strategy_id: int):
        strategy, account = _get_strategy_account(request, strategy_id)
        if not strategy or not account:
            return Response({"error": "not found"}, status=404)
        trades = PaperTrade.objects.filter(account=account).order_by("-created_at")[:100]
        return Response(
            {
                "trades": [
                    {
                        "id": t.id,
                        "side": t.side,
                        "entry_price": str(t.entry_price),
                        "exit_price": str(t.exit_price) if t.exit_price is not None else None,
                        "size": str(t.size),
                        "pnl": str(t.pnl),
                        "entry_bar": t.entry_bar,
                        "exit_bar": t.exit_bar,
                        "created_at": t.created_at,
                    }
                    for t in trades
                ]
            }
        )


class PaperPositionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, strategy_id: int):
        strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).select_related("state").first()
        if not strategy:
            return Response({"error": "not found"}, status=404)
        pos = {}
        if hasattr(strategy, "state") and strategy.state:
            pos = strategy.state.position or {}
        if not pos:
            return Response({"positions": []})
        return Response(
            {
                "positions": [
                    {
                        "coin": strategy.symbol,
                        "side": pos.get("side", ""),
                        "size": str(pos.get("size", "0")),
                        "entry_px": str(pos.get("entry_price", "0")),
                        "unrealized_pnl": str(pos.get("unrealized_pnl", "0")),
                    }
                ]
            }
        )
