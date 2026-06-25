"""Pro features REST API."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.exchange.candle_store import load_candles
from apps.strategies.models import Strategy

from .models import MarketplacePackage, ReplaySession, StrategyVersion, TradeJournal


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


class JournalView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entries = TradeJournal.objects.filter(user=request.user).order_by("-created_at")[:50]
        return Response(
            {
                "entries": [
                    {
                        "id": e.id,
                        "strategy_id": e.strategy_id,
                        "title": e.title,
                        "body": e.body,
                        "tags": e.tags,
                        "created_at": e.created_at,
                    }
                    for e in entries
                ]
            }
        )

    def post(self, request):
        entry = TradeJournal.objects.create(
            user=request.user,
            strategy_id=request.data.get("strategy_id"),
            title=request.data.get("title", "Untitled"),
            body=request.data.get("body", ""),
            tags=request.data.get("tags", []),
            screenshot_url=request.data.get("screenshot_url", ""),
        )
        return Response({"id": entry.id})


class MarketplaceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        packages = MarketplacePackage.objects.filter(is_public=True).order_by("-created_at")[:50]
        return Response(
            {
                "packages": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "author_id": p.author_id,
                    }
                    for p in packages
                ]
            }
        )

    def post(self, request):
        pkg = MarketplacePackage.objects.create(
            author=request.user,
            name=request.data.get("name", "Strategy"),
            description=request.data.get("description", ""),
            source=request.data.get("source", ""),
            params=request.data.get("params", {}),
            metadata=request.data.get("metadata", {}),
            is_public=bool(request.data.get("is_public", False)),
        )
        return Response({"id": pkg.id})


class MarketplaceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, package_id: int):
        pkg = MarketplacePackage.objects.filter(pk=package_id, is_public=True).first()
        if not pkg:
            return Response({"error": "not found"}, status=404)
        return Response(
            {
                "id": pkg.id,
                "name": pkg.name,
                "description": pkg.description,
                "source": pkg.source,
                "params": pkg.params,
                "metadata": pkg.metadata,
                "author_id": pkg.author_id,
            }
        )


class MarketplaceImportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, package_id: int):
        pkg = MarketplacePackage.objects.filter(pk=package_id, is_public=True).first()
        if not pkg:
            return Response({"error": "not found"}, status=404)
        strategy = Strategy.objects.create(
            user=request.user,
            name=request.data.get("name", pkg.name),
            type="pine",
            symbol=request.data.get("symbol", "BTC"),
            source=pkg.source,
            params=pkg.params,
            live_config=request.data.get("live_config", {}),
        )
        return Response({"strategy_id": strategy.pk})


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
