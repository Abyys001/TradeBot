"""Dashboard REST API views."""
from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.credentials.models import ExchangeCredential
from apps.exchange.candles import BAR_MAP, CandleFetchError, fetch_candles
from apps.execution.models import ExecutionLog, OrderRecord
from apps.strategies.models import Strategy
from apps.transpiler.models import BacktestTrade

from .health import get_celery_status, get_market_feed_status
from .overview import build_overview_payload
from .tasks import emergency_stop_all_task


def build_health_payload(*, user) -> dict:
    credentials = []
    active_strategies = 0
    is_trading_enabled = False
    if user is not None and user.is_authenticated:
        credentials = [
            {
                "id": c.pk,
                "label": c.label,
                "is_active": c.is_active,
                "network": c.network,
                "wallet_address": c.wallet_address,
                "last_verified_at": c.last_verified_at,
            }
            for c in ExchangeCredential.objects.filter(user=user)
        ]
        active_strategies = Strategy.objects.filter(
            user=user, status=Strategy.Status.ACTIVE
        ).count()
        is_trading_enabled = bool(user.is_trading_enabled)

    return {
        "hl_market_feed": get_market_feed_status(),
        "celery": get_celery_status(),
        "credentials": credentials,
        "active_strategies": active_strategies,
        "is_trading_enabled": is_trading_enabled,
    }


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.pk,
                "username": user.username,
                "email": user.email,
                "is_trading_enabled": user.is_trading_enabled,
            }
        )


class KillSwitchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        enabled = request.data.get("enabled", False)
        close_positions = request.data.get("close_positions", False)

        if not enabled and close_positions:
            emergency_stop_all_task.delay(request.user.pk)
            return Response({"status": "emergency_stop_queued"}, status=status.HTTP_202_ACCEPTED)

        request.user.is_trading_enabled = bool(enabled)
        request.user.save(update_fields=["is_trading_enabled"])
        return Response({"is_trading_enabled": request.user.is_trading_enabled})


class HealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_health_payload(user=request.user))


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_overview_payload(request.user))


class CandlesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        symbol = request.query_params.get("symbol", "BTC")
        bar = request.query_params.get("bar", "1m")
        try:
            limit = min(int(request.query_params.get("limit", 500)), 1000)
        except (TypeError, ValueError):
            return Response({"error": "invalid limit"}, status=status.HTTP_400_BAD_REQUEST)

        if bar not in BAR_MAP:
            return Response({"error": f"unsupported bar: {bar}"}, status=status.HTTP_400_BAD_REQUEST)

        network = request.query_params.get("network", "testnet")
        try:
            df = fetch_candles(symbol, bar, limit, network=network)
        except (CandleFetchError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        candles = [
            {
                "time": int(row.ts // 1000),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
            for row in df.itertuples()
        ]
        return Response({"symbol": symbol, "bar": bar, "candles": candles})


class MarkersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        strategy_id = request.query_params.get("strategy_id")
        source = request.query_params.get("source", "live")
        if not strategy_id:
            return Response({"error": "strategy_id required"}, status=status.HTTP_400_BAD_REQUEST)

        strategy = get_object_or_404(Strategy, pk=strategy_id, user=request.user)
        markers = []

        if source == "backtest":
            from apps.exchange.candle_store import load_candles
            from apps.transpiler.models import Backtest

            backtest_id = request.query_params.get("backtest_id")
            if not backtest_id:
                return Response({"error": "backtest_id required for backtest source"}, status=status.HTTP_400_BAD_REQUEST)
            bt = get_object_or_404(Backtest, pk=backtest_id, strategy=strategy)
            trades = BacktestTrade.objects.filter(backtest=bt)

            start_ms = int(bt.range_start.timestamp() * 1000) if bt.range_start else None
            end_ms = int(bt.range_end.timestamp() * 1000) if bt.range_end else None
            df = load_candles(
                bt.symbol, bt.timeframe, start_ms, end_ms, network=bt.network or "mainnet"
            )
            ts_list = [int(t // 1000) for t in df["ts"].tolist()] if not df.empty else []

            def bar_time(bar_index: int | None) -> int | None:
                if bar_index is None or bar_index < 0 or bar_index >= len(ts_list):
                    return None
                return ts_list[bar_index]

            # Exit-reason → marker styling (stop-loss vs take-profit vs liquidation).
            exit_styles = {
                "stop": ("#ef4444", "SL"),
                "take_profit": ("#3b82f6", "TP"),
                "liquidation": ("#f59e0b", "Liq"),
            }
            levels = []
            for trade in trades:
                entry_time = bar_time(trade.entry_bar)
                if entry_time is not None:
                    is_long = trade.side == "long"
                    markers.append(
                        {
                            "time": entry_time,
                            "position": "belowBar" if is_long else "aboveBar",
                            "color": "#22c55e" if is_long else "#ef4444",
                            "shape": "arrowUp" if is_long else "arrowDown",
                            "text": "Buy" if is_long else "Sell",
                            "side": trade.side,
                        }
                    )
                exit_time = bar_time(trade.exit_bar)
                if exit_time is not None:
                    reason = getattr(trade, "exit_reason", "") or ""
                    color, label = exit_styles.get(reason, ("#a855f7", "Exit"))
                    markers.append(
                        {
                            "time": exit_time,
                            "position": "aboveBar",
                            "color": color,
                            "shape": "arrowDown",
                            "text": label,
                            "side": trade.side,
                            "exit_reason": reason,
                        }
                    )
                # SL/TP price levels for the entry → exit span (drawn as price lines).
                if entry_time is not None:
                    if trade.stop_px is not None:
                        levels.append({"time": entry_time, "price": float(trade.stop_px), "type": "stop"})
                    if trade.limit_px is not None:
                        levels.append({"time": entry_time, "price": float(trade.limit_px), "type": "take_profit"})
            return Response(
                {"strategy_id": strategy.pk, "source": source, "markers": markers, "levels": levels}
            )
        elif source == "paper":
            from apps.exchange.candle_store import load_candles
            from apps.paper.models import PaperAccount, PaperTrade

            account = PaperAccount.objects.filter(user=request.user, strategy=strategy).first()
            if account:
                trades = PaperTrade.objects.filter(account=account)
                df = load_candles(strategy.symbol, strategy.timeframe)
                ts_list = [int(t // 1000) for t in df["ts"].tolist()] if not df.empty else []

                def bar_time(bar_index: int | None) -> int | None:
                    if bar_index is None or bar_index < 0 or bar_index >= len(ts_list):
                        return None
                    return ts_list[bar_index]

                for trade in trades:
                    entry_time = bar_time(trade.entry_bar)
                    if entry_time is not None:
                        is_long = trade.side == "long"
                        markers.append(
                            {
                                "time": entry_time,
                                "position": "belowBar" if is_long else "aboveBar",
                                "color": "#22c55e" if is_long else "#ef4444",
                                "shape": "arrowUp" if is_long else "arrowDown",
                                "text": "Entry",
                                "side": trade.side,
                            }
                        )
                    exit_time = bar_time(trade.exit_bar)
                    if exit_time is not None:
                        markers.append(
                            {
                                "time": exit_time,
                                "position": "aboveBar",
                                "color": "#a855f7",
                                "shape": "circle",
                                "text": "Exit",
                                "side": trade.side,
                            }
                        )
        else:
            orders = OrderRecord.objects.filter(strategy=strategy).order_by("created_at")
            for order in orders:
                ts = int(order.created_at.timestamp())
                is_buy = order.side == OrderRecord.Side.BUY
                markers.append(
                    {
                        "time": ts,
                        "position": "belowBar" if is_buy else "aboveBar",
                        "color": "#22c55e" if is_buy else "#ef4444",
                        "shape": "arrowUp" if is_buy else "arrowDown",
                        "text": "Buy" if is_buy else "Sell",
                        "side": order.side,
                    }
                )

        return Response({"strategy_id": strategy.pk, "source": source, "markers": markers})


class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.transpiler.models import Backtest

        backtests = (
            Backtest.objects.filter(strategy__user=request.user, status=Backtest.Status.DONE)
            .select_related("strategy")
            .order_by("-created_at")[:100]
        )
        rows = []
        for bt in backtests:
            m = bt.metrics or {}
            rows.append(
                {
                    "backtest_id": bt.id,
                    "strategy_id": bt.strategy_id,
                    "strategy_name": bt.strategy.name,
                    "symbol": bt.symbol,
                    "timeframe": bt.timeframe,
                    "net_pnl": m.get("net_pnl"),
                    "sharpe_ratio": m.get("sharpe_ratio"),
                    "profit_factor": m.get("profit_factor"),
                    "max_drawdown": m.get("max_drawdown"),
                    "num_trades": m.get("num_trades"),
                    "created_at": bt.created_at,
                }
            )
        best = max(rows, key=lambda r: r.get("net_pnl") or 0, default=None)
        worst = min(rows, key=lambda r: r.get("net_pnl") or 0, default=None)
        if best:
            best_bt = next((bt for bt in backtests if bt.id == best["backtest_id"]), None)
            if best_bt:
                best = {**best, "equity_series": (best_bt.metrics or {}).get("equity_series", [])}
        if worst:
            worst_bt = next((bt for bt in backtests if bt.id == worst["backtest_id"]), None)
            if worst_bt:
                worst = {**worst, "equity_series": (worst_bt.metrics or {}).get("equity_series", [])}

        # Monthly performance buckets (by run creation month).
        monthly: dict[str, dict] = {}
        for bt in backtests:
            key = bt.created_at.strftime("%Y-%m")
            bucket = monthly.setdefault(key, {"month": key, "net_pnl": 0.0, "count": 0})
            bucket["net_pnl"] += float((bt.metrics or {}).get("net_pnl") or 0)
            bucket["count"] += 1
        monthly_list = sorted(monthly.values(), key=lambda b: b["month"])

        # Per-asset win rate + funding aggregation (trade-weighted win rate).
        by_asset: dict[str, dict] = {}
        total_funding = 0.0
        for bt in backtests:
            m = bt.metrics or {}
            sym = bt.symbol or "?"
            a = by_asset.setdefault(
                sym, {"symbol": sym, "net_pnl": 0.0, "num_trades": 0, "_wins": 0.0, "funding_paid": 0.0}
            )
            trades_n = int(m.get("num_trades") or 0)
            a["net_pnl"] += float(m.get("net_pnl") or 0)
            a["num_trades"] += trades_n
            a["_wins"] += float(m.get("win_rate") or 0) * trades_n
            a["funding_paid"] += float(m.get("funding_paid") or 0)
            total_funding += float(m.get("funding_paid") or 0)
        asset_list = []
        for a in by_asset.values():
            win_rate = round(a["_wins"] / a["num_trades"], 4) if a["num_trades"] else 0.0
            asset_list.append(
                {
                    "symbol": a["symbol"],
                    "net_pnl": round(a["net_pnl"], 8),
                    "num_trades": a["num_trades"],
                    "win_rate": win_rate,
                    "funding_paid": round(a["funding_paid"], 8),
                }
            )
        asset_list.sort(key=lambda x: x["net_pnl"], reverse=True)

        return Response(
            {
                "runs": rows,
                "best": best,
                "worst": worst,
                "count": len(rows),
                "monthly": monthly_list,
                "by_asset": asset_list,
                "total_funding_paid": round(total_funding, 8),
            }
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"error": "invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        return Response(
            {
                "id": user.pk,
                "username": user.username,
                "is_trading_enabled": user.is_trading_enabled,
            }
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"status": "logged_out"})


@ensure_csrf_cookie
def csrf_token_view(request):
    return JsonResponse({"csrfToken": get_token(request)})
