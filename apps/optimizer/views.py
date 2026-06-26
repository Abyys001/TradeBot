"""Optimizer REST API."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.exchange.candle_store import load_candles
from apps.strategies.models import Strategy

from .grid import grid_search
from .monte_carlo import monte_carlo_equity
from .portfolio import portfolio_backtest
from .walk_forward import walk_forward


class OptimizeGridView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        strategy_id = request.data.get("strategy_id")
        coin = request.data.get("coin", "BTC")
        interval = request.data.get("interval", "1h")
        network = request.data.get("network", "mainnet")
        param_grid = request.data.get("param_grid") or {}

        strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
        if not strategy:
            return Response({"error": "strategy not found"}, status=404)
        if not param_grid:
            return Response({"error": "param_grid required"}, status=400)

        df = load_candles(coin, interval, network=network)
        if df.empty:
            return Response({"error": "no data"}, status=404)

        results = grid_search(strategy.source, df, param_grid, base_kwargs={"live_config": strategy.live_config})
        return Response({"results": results[:50]})


class OptimizeWalkForwardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        strategy_id = request.data.get("strategy_id")
        coin = request.data.get("coin", "BTC")
        interval = request.data.get("interval", "1h")
        network = request.data.get("network", "mainnet")
        param_grid = request.data.get("param_grid") or {}
        train_bars = int(request.data.get("train_bars", 500))
        test_bars = int(request.data.get("test_bars", 100))

        strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
        if not strategy:
            return Response({"error": "strategy not found"}, status=404)

        df = load_candles(coin, interval, network=network)
        windows = walk_forward(
            strategy.source,
            df,
            param_grid,
            train_bars=train_bars,
            test_bars=test_bars,
            base_kwargs={"live_config": strategy.live_config},
        )
        return Response({"windows": windows})


class OptimizeMonteCarloView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        backtest_id = request.data.get("backtest_id")
        simulations = int(request.data.get("simulations", 500))
        from apps.transpiler.models import Backtest

        bt = Backtest.objects.filter(pk=backtest_id, strategy__user=request.user).first()
        if not bt:
            return Response({"error": "backtest not found"}, status=404)
        pnls = [float(t.pnl) for t in bt.trades.all()]
        return Response(monte_carlo_equity(pnls, simulations=simulations))


class OptimizePortfolioView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        items = request.data.get("strategies") or []
        network = request.data.get("network", "mainnet")
        interval = request.data.get("interval", "1h")
        if not items:
            return Response({"error": "strategies required"}, status=400)

        strategies_payload = []
        data = {}
        for item in items:
            strategy_id = item.get("strategy_id")
            symbol = item.get("symbol")
            strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
            if not strategy or not symbol:
                continue
            df = load_candles(symbol, interval, network=network)
            if df.empty:
                continue
            data[symbol] = df
            strategies_payload.append({"symbol": symbol, "source": strategy.source, "kwargs": {"live_config": strategy.live_config}})

        if not strategies_payload:
            return Response({"error": "no data"}, status=404)
        return Response(portfolio_backtest(strategies_payload, data))
