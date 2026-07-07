"""REST API for historical market data management."""
from __future__ import annotations

import time

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
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
from apps.exchange.hl_constants import BAR_MAP, normalize_coin, normalize_interval
from apps.exchange.history_download import DEFAULT_START, VALID_DATA_TYPES, build_initial_progress, date_to_ms, job_has_retryable_pairs, known_perp_coins, reset_pairs_for_retry

from .models import HistoryDownload
from .serializers import HistoryDownloadSerializer, is_stale_pending
from .tasks import download_history_task, import_archive_task

_VALID_NETWORKS = frozenset({"mainnet", "testnet"})
_VALID_DATA_TYPES = frozenset(VALID_DATA_TYPES)
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
        try:
            coins = sorted(known_perp_coins(network))
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"network": network, "coins": [], "intervals": intervals, "error": str(exc)}
            )
        return Response({"network": network, "coins": coins, "intervals": intervals})


class HistoryDownloadViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = HistoryDownloadSerializer

    def get_queryset(self):
        return HistoryDownload.objects.filter(user=self.request.user).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        coins = request.data.get("coins") or []
        intervals = request.data.get("intervals") or []
        data_types = request.data.get("data_types") or ["ohlcv"]

        if "trades" in data_types:
            return Response(
                {"error": "trades have no Hyperliquid history endpoint and cannot be backfilled"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invalid = [d for d in data_types if d not in _VALID_DATA_TYPES]
        if invalid:
            return Response(
                {"error": f"invalid data_types: {', '.join(invalid)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not coins:
            return Response(
                {"error": "coins required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if "ohlcv" in data_types and not intervals:
            return Response(
                {"error": "intervals required for ohlcv"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        network = request.data.get("network", "mainnet")
        if network not in _VALID_NETWORKS:
            return Response(
                {"error": f"invalid network: {network}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_str = request.data.get("start", DEFAULT_START)
        end_str = request.data.get("end")

        try:
            start_ms = int(request.data["start"]) if str(request.data.get("start", "")).isdigit() else date_to_ms(start_str)
            if end_str:
                end_ms = int(end_str) if str(end_str).isdigit() else date_to_ms(end_str)
            else:
                end_ms = int(time.time() * 1000)
        except (TypeError, ValueError) as exc:
            return Response({"error": f"bad date: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        if start_ms >= end_ms:
            return Response(
                {"error": "start must be before end"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            norm_coins = [normalize_coin(c) for c in coins]
            norm_intervals = [normalize_interval(i) for i in intervals]
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        job = HistoryDownload.objects.create(
            user=request.user,
            network=network,
            coins=norm_coins,
            intervals=norm_intervals,
            data_types=list(data_types),
            start_ms=start_ms,
            end_ms=end_ms,
            progress=build_initial_progress(norm_coins, norm_intervals, list(data_types)),
        )
        try:
            download_history_task.delay(job.id)
        except Exception as exc:  # noqa: BLE001
            job.status = HistoryDownload.Status.FAILED
            job.error = f"Failed to queue task: {exc}"
            job.save(update_fields=["status", "error"])
            return Response(
                HistoryDownloadSerializer(job).data,
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        publish_dashboard(
            request.user.pk,
            {
                "source": "history_download",
                "job_id": job.id,
                "status": "pending",
                "progress": job.progress,
            },
        )
        return Response(
            HistoryDownloadSerializer(job).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        job = self.get_object()
        retryable_done = job.status == HistoryDownload.Status.DONE and job_has_retryable_pairs(job.progress)
        if job.status not in {
            HistoryDownload.Status.FAILED,
            HistoryDownload.Status.PARTIAL,
            HistoryDownload.Status.PENDING,
        } and not retryable_done:
            return Response(
                {"error": "only failed, partial, stale pending, or empty jobs can be retried"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if job.status == HistoryDownload.Status.PENDING and not is_stale_pending(job):
            return Response(
                {"error": "job is still queued"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.status = HistoryDownload.Status.PENDING
        job.error = ""
        if job.progress:
            job.progress = reset_pairs_for_retry(job.progress)
        else:
            job.progress = build_initial_progress(job.coins, job.intervals, job.data_types or ["ohlcv"])
        job.save(update_fields=["status", "error", "progress"])

        try:
            download_history_task.delay(job.id)
        except Exception as exc:  # noqa: BLE001
            job.status = HistoryDownload.Status.FAILED
            job.error = f"Failed to queue task: {exc}"
            job.save(update_fields=["status", "error"])
            return Response(
                HistoryDownloadSerializer(job).data,
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        publish_dashboard(
            request.user.pk,
            {
                "source": "history_download",
                "job_id": job.id,
                "status": "pending",
                "progress": job.progress,
            },
        )
        return Response(HistoryDownloadSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="retry-stale")
    def retry_stale(self, request):
        """Re-queue all stale pending download jobs for the current user."""
        stale_jobs = [
            j
            for j in self.get_queryset().filter(status=HistoryDownload.Status.PENDING)
            if is_stale_pending(j)
        ]
        retried: list[int] = []
        failed: list[int] = []
        for job in stale_jobs:
            job.status = HistoryDownload.Status.PENDING
            job.error = ""
            job.save(update_fields=["status", "error"])
            try:
                download_history_task.delay(job.id)
                retried.append(job.id)
            except Exception as exc:  # noqa: BLE001
                job.status = HistoryDownload.Status.FAILED
                job.error = f"Failed to queue task: {exc}"
                job.save(update_fields=["status", "error"])
                failed.append(job.id)

        if retried:
            publish_dashboard(
                request.user.pk,
                {"source": "history_download", "status": "pending", "retried": retried},
            )
        return Response({"retried": retried, "failed": failed, "count": len(retried)})


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
