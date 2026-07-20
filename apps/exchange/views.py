"""REST API for historical market data management."""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard.publish import publish_dashboard
from apps.exchange.candle_store import (
    dataset_coverage,
    delete_dataset,
    list_datasets,
    load_candles,
    load_candles_from_db,
    load_funding_from_db,
)
from apps.exchange.constants import BAR_MAP, normalize_coin, normalize_interval

from .models import HistoryDownload
from .serializers import HistoryDownloadSerializer
from .tasks import import_archive_task

_VALID_NETWORKS = frozenset({"mainnet", "testnet"})
_VALID_KINDS = frozenset({"ohlcv", "funding", "open_interest"})


class HistoryDatasetsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        network = request.query_params.get("network")
        include_quality = request.query_params.get("include_quality", "").lower() in ("1", "true", "yes")
        if network and network not in _VALID_NETWORKS:
            return Response({"error": f"invalid network: {network}"}, status=status.HTTP_400_BAD_REQUEST)
        datasets = list_datasets(network=network)
        if include_quality:
            from apps.exchange.data_quality import dataset_quality_light

            for ds in datasets:
                if ds.get("kind", "ohlcv") == "ohlcv":
                    try:
                        report = dataset_quality_light(
                            bars=int(ds.get("bars", 0)),
                            start_ts=int(ds.get("start_ts", 0)),
                            end_ts=int(ds.get("end_ts", 0)),
                            interval=ds.get("interval", "1h"),
                        )
                        ds["healthy"] = report.get("healthy", True)
                        ds["gap_count"] = report.get("gap_count", 0)
                        ds["missing_bars"] = report.get("missing_bars", 0)
                    except (TypeError, ValueError):
                        ds["healthy"] = True
                        ds["gap_count"] = 0
                        ds["missing_bars"] = 0
        return Response({"datasets": datasets})

    def delete(self, request):
        # Accept JSON body or query params (some proxies strip DELETE bodies).
        src = {**request.query_params.dict(), **(request.data or {})}
        network = src.get("network", "mainnet")
        coin = src.get("coin")
        interval = src.get("interval")
        kind = src.get("kind", "ohlcv")

        if network not in _VALID_NETWORKS:
            return Response({"error": f"invalid network: {network}"}, status=status.HTTP_400_BAD_REQUEST)
        if not coin:
            return Response({"error": "coin required"}, status=status.HTTP_400_BAD_REQUEST)
        if kind not in _VALID_KINDS:
            return Response({"error": f"invalid kind: {kind}"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            norm_coin = normalize_coin(coin)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if kind == "ohlcv":
            if not interval:
                return Response({"error": "interval required for ohlcv"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                norm_interval = normalize_interval(interval)
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            norm_interval = ""

        try:
            deleted = delete_dataset(network, norm_coin, norm_interval or "1h", kind=kind)
        except OSError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not deleted:
            return Response({"error": "dataset not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"ok": True})


class HistoryCandlesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        coin = request.query_params.get("coin", "BTC")
        interval = request.query_params.get("interval", "1h")
        network = request.query_params.get("network", "mainnet")
        source = request.query_params.get("source", "db")
        try:
            limit = min(int(request.query_params.get("limit", 500)), 50000)
        except (TypeError, ValueError):
            return Response({"error": "invalid limit"}, status=status.HTTP_400_BAD_REQUEST)

        start = request.query_params.get("start")
        end = request.query_params.get("end")
        try:
            start_ms = int(start) if start else None
            end_ms = int(end) if end else None
            coin = normalize_coin(coin)
            interval = normalize_interval(interval)
        except (TypeError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if source == "parquet":
            df = load_candles(coin, interval, start_ms, end_ms, network=network)
        else:
            df = load_candles_from_db(
                coin, interval, start_ms, end_ms, network=network, limit=limit if not start_ms else None
            )

        if df.empty:
            return Response({"coin": coin, "interval": interval, "network": network, "candles": []})

        if limit and len(df) > limit:
            df = df.iloc[-limit:]

        candles = [
            {
                "time": int(row.ts // 1000),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
            for row in df.itertuples()
        ]
        return Response({"coin": coin, "interval": interval, "network": network, "candles": candles})


class HistoryFundingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        coin = request.query_params.get("coin", "BTC")
        network = request.query_params.get("network", "mainnet")
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        try:
            start_ms = int(start) if start else None
            end_ms = int(end) if end else None
            coin = normalize_coin(coin)
        except (TypeError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        df = load_funding_from_db(coin, start_ms, end_ms, network=network)
        if df.empty:
            return Response({"coin": coin, "network": network, "funding": []})

        funding = [
            {
                "time": int(row.ts // 1000),
                "funding_rate": float(row.funding_rate),
                "premium": float(row.premium),
            }
            for row in df.itertuples()
        ]
        return Response({"coin": coin, "network": network, "funding": funding})


class HistoryCoverageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        coin = request.query_params.get("coin", "BTC")
        interval = request.query_params.get("interval", "1h")
        network = request.query_params.get("network", "mainnet")
        kind = request.query_params.get("kind", "ohlcv")
        try:
            coin = normalize_coin(coin)
            interval = normalize_interval(interval)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        coverage = dataset_coverage(network, coin, interval, kind=kind)
        if coverage is None:
            return Response({"error": "dataset not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(coverage)


class HistoryGapsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.exchange.data_quality import find_gaps

        coin = request.query_params.get("coin", "BTC")
        interval = request.query_params.get("interval", "1h")
        network = request.query_params.get("network", "mainnet")
        try:
            coin = normalize_coin(coin)
            interval = normalize_interval(interval)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        gaps = find_gaps(coin, interval, network=network)
        return Response({"coin": coin, "interval": interval, "network": network, "gaps": gaps})


class HistoryQualityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.exchange.data_quality import dataset_report

        coin = request.query_params.get("coin", "BTC")
        interval = request.query_params.get("interval", "1h")
        network = request.query_params.get("network", "mainnet")
        kind = request.query_params.get("kind", "ohlcv")
        try:
            coin = normalize_coin(coin)
            interval = normalize_interval(interval)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(dataset_report(coin, interval, network=network, kind=kind))


class HistoryMarketsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        network = request.query_params.get("network", "mainnet")
        intervals = sorted(set(BAR_MAP.values()))
        # Tabdeal-only: markets are whatever we have actually recorded locally
        # (no exchange metadata backfill). Derive coins from the stored datasets.
        try:
            coins = sorted({ds.get("coin") for ds in list_datasets(network=network) if ds.get("coin")})
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"network": network, "coins": [], "intervals": intervals, "error": str(exc)}
            )
        return Response({"network": network, "coins": coins, "intervals": intervals})


class ArchiveImportView(APIView):
    """POST /api/history/import-archive/ — import a Dwellir Parquet/CSV archive.

    Body::
        {
            "file_path": "/data/archives/BTC-1h-full.parquet",
            "coin": "BTC",          // optional — inferred from filename
            "interval": "1h",       // optional — inferred from filename
            "network": "mainnet"    // optional, default "mainnet"
        }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        file_path = request.data.get("file_path")
        if not file_path:
            return Response(
                {"error": "file_path is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        import os
        if not os.path.isfile(file_path):
            return Response(
                {"error": f"file not found: {file_path}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        coin = request.data.get("coin")
        interval = request.data.get("interval")
        network = request.data.get("network", "mainnet")
        if network not in _VALID_NETWORKS:
            return Response(
                {"error": f"invalid network: {network}"}, status=status.HTTP_400_BAD_REQUEST
            )

        job = HistoryDownload.objects.create(
            user=request.user,
            network=network,
            coins=[coin or "?"],
            intervals=[interval or "?"],
            data_types=["ohlcv"],
            start_ms=0,
            end_ms=0,
            status=HistoryDownload.Status.PENDING,
        )
        import_archive_task.delay(file_path, coin=coin, interval=interval, network=network, job_id=job.id)

        publish_dashboard(
            request.user.pk,
            {
                "source": "history_download",
                "job_id": job.id,
                "status": "pending",
                "progress": {},
            },
        )
        return Response(
            HistoryDownloadSerializer(job).data, status=status.HTTP_202_ACCEPTED
        )


# --- Market Data Engine: readiness / coverage / symbols (Master Plan §P3) --------

_DEFAULT_REQUIRED_BARS = 200


def _resolve_required_bars(request) -> int:
    """Warmup requirement: explicit ``required_bars``, else the strategy's warmup_bars."""
    raw = request.query_params.get("required_bars")
    if raw is not None:
        try:
            return max(int(raw), 0)
        except (TypeError, ValueError):
            return _DEFAULT_REQUIRED_BARS
    strategy_id = request.query_params.get("strategy_id")
    if strategy_id:
        from apps.strategies.models import Strategy

        strat = Strategy.objects.filter(pk=strategy_id, user=request.user).first()
        if strat is not None:
            return int(getattr(strat, "warmup_bars", _DEFAULT_REQUIRED_BARS))
    return _DEFAULT_REQUIRED_BARS


class MarketDataReadinessView(APIView):
    """GET /api/marketdata/readiness/?symbol=BTC_USDT&tf=1m[&strategy_id=|&required_bars=]"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.exchange.readiness import readiness

        symbol = request.query_params.get("symbol", "BTC_USDT")
        tf = request.query_params.get("tf") or request.query_params.get("timeframe", "1m")
        required = _resolve_required_bars(request)
        return Response(readiness(symbol, tf, required))


class MarketDataCoverageView(APIView):
    """GET /api/marketdata/coverage/?symbol=BTC_USDT — recorded coverage window."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.exchange import coverage as coverage_svc
        from apps.exchange.ledger import union_coverage

        symbol = request.query_params.get("symbol", "BTC_USDT")
        intervals_ms = union_coverage(symbol)
        if not intervals_ms:
            return Response({"symbol": symbol.upper(), "recording_since": None,
                             "recorded_until": None, "coverage_pct": 0.0, "intervals": []})
        start_ms, end_ms = intervals_ms[0][0], intervals_ms[-1][1]
        # Chart consumes seconds; expose interval edges in seconds for the scrubber.
        intervals_s = [[lo // 1000, hi // 1000] for lo, hi in intervals_ms]
        return Response({
            "symbol": symbol.upper(),
            "recording_since": start_ms // 1000,
            "recorded_until": end_ms // 1000,
            "coverage_pct": round(coverage_svc.coverage_pct(symbol, start_ms, end_ms) * 100, 2),
            "intervals": intervals_s,
        })


class MarketDataSymbolsView(APIView):
    """GET /api/marketdata/symbols/ — symbols the recorder has any ledger for."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.exchange.ledger import ledger_dir

        base = ledger_dir()
        symbols: list[str] = []
        if base.exists():
            symbols = sorted(p.name for p in base.iterdir() if p.is_dir())
        return Response({"symbols": symbols})
