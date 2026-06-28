"""Pro features REST API."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.exchange.candle_store import load_candles
from apps.strategies.models import Strategy

from .models import ReplaySession, StrategyVersion


class StrategyVersionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, strategy_id: int):
        strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
        if not strategy:
            return Response({"error": "not found"}, status=404)
        versions = StrategyVersion.objects.filter(strategy=strategy).values(
            "id", "version", "note", "created_at"
        )
        return Response({"versions": list(versions)})

    def post(self, request, strategy_id: int):
        strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
        if not strategy:
            return Response({"error": "not found"}, status=404)
        last = StrategyVersion.objects.filter(strategy=strategy).order_by("-version").first()
        ver = (last.version + 1) if last else 1
        sv = StrategyVersion.objects.create(
            strategy=strategy,
            version=ver,
            source=strategy.source,
            params=strategy.params,
            note=request.data.get("note", ""),
        )
        return Response({"id": sv.id, "version": sv.version})


class StrategyVersionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, strategy_id: int, version: int):
        strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
        if not strategy:
            return Response({"error": "not found"}, status=404)
        sv = StrategyVersion.objects.filter(strategy=strategy, version=version).first()
        if not sv:
            return Response({"error": "version not found"}, status=404)
        return Response(
            {
                "id": sv.id,
                "version": sv.version,
                "source": sv.source,
                "params": sv.params,
                "note": sv.note,
                "created_at": sv.created_at,
            }
        )


class StrategyVersionRestoreView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, strategy_id: int, version: int):
        strategy = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
        if not strategy:
            return Response({"error": "not found"}, status=404)
        sv = StrategyVersion.objects.filter(strategy=strategy, version=version).first()
        if not sv:
            return Response({"error": "version not found"}, status=404)
        strategy.source = sv.source
        strategy.params = sv.params
        strategy.validation_status = ""
        strategy.validation_error = ""
        strategy.save(update_fields=["source", "params", "validation_status", "validation_error"])
        return Response({"ok": True, "strategy_id": strategy.pk, "version": sv.version})


class ReplayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session = ReplaySession.objects.create(
            user=request.user,
            coin=request.data.get("coin", "BTC"),
            interval=request.data.get("interval", "1h"),
            network=request.data.get("network", "mainnet"),
            cursor_bar=int(request.data.get("cursor_bar", 0)),
            speed=float(request.data.get("speed", 1.0)),
        )
        return Response({"id": session.id, "cursor_bar": session.cursor_bar})


class ReplayDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id: int):
        session = ReplaySession.objects.filter(pk=session_id, user=request.user).first()
        if not session:
            return Response({"error": "not found"}, status=404)
        df = load_candles(session.coin, session.interval, network=session.network)
        candles = []
        if not df.empty:
            slice_df = df.iloc[session.cursor_bar : session.cursor_bar + 200]
            candles = [
                {
                    "time": int(row.ts // 1000),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "volume": float(row.volume),
                }
                for row in slice_df.itertuples()
            ]
        return Response(
            {
                "id": session.id,
                "coin": session.coin,
                "interval": session.interval,
                "network": session.network,
                "cursor_bar": session.cursor_bar,
                "speed": session.speed,
                "total_bars": len(df) if not df.empty else 0,
                "candles": candles,
            }
        )

    def delete(self, request, session_id: int):
        deleted, _ = ReplaySession.objects.filter(pk=session_id, user=request.user).delete()
        if not deleted:
            return Response({"error": "not found"}, status=404)
        return Response({"ok": True})


class ReplayStepView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id: int):
        session = ReplaySession.objects.filter(pk=session_id, user=request.user).first()
        if not session:
            return Response({"error": "not found"}, status=404)
        step = int(request.data.get("step", 1))
        df = load_candles(session.coin, session.interval, network=session.network)
        total = len(df) if not df.empty else 0
        session.cursor_bar = min(max(0, session.cursor_bar + step), max(0, total - 1))
        session.save(update_fields=["cursor_bar"])
        bar = None
        if not df.empty and session.cursor_bar < total:
            row = df.iloc[session.cursor_bar]
            bar = {
                "time": int(row.ts // 1000),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
        return Response({"cursor_bar": session.cursor_bar, "bar": bar, "total_bars": total})
