from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from .models import HistoryDownload, RecordedSymbol

STALE_PENDING_SECONDS = 120


def is_stale_pending(obj: HistoryDownload) -> bool:
    if obj.status != HistoryDownload.Status.PENDING:
        return False
    age = (timezone.now() - obj.created_at).total_seconds()
    return age > STALE_PENDING_SECONDS


class HistoryDownloadSerializer(serializers.ModelSerializer):
    is_stale = serializers.SerializerMethodField()

    class Meta:
        model = HistoryDownload
        fields = [
            "id",
            "status",
            "network",
            "coins",
            "intervals",
            "data_types",
            "start_ms",
            "end_ms",
            "progress",
            "error",
            "created_at",
            "is_stale",
        ]
        read_only_fields = fields

    def get_is_stale(self, obj: HistoryDownload) -> bool:
        return is_stale_pending(obj)

    def to_representation(self, instance: HistoryDownload) -> dict:
        data = super().to_representation(instance)
        if not data.get("progress"):
            from .history_jobs import build_initial_progress

            data["progress"] = build_initial_progress(
                instance.coins,
                instance.intervals,
                instance.data_types or ["ohlcv"],
            )
        return data


class RecordedSymbolSerializer(serializers.ModelSerializer):
    """A market the ingest nodes record, plus its live recording status."""

    coverage = serializers.SerializerMethodField()

    class Meta:
        model = RecordedSymbol
        fields = ["id", "symbol", "is_active", "note", "created_at", "updated_at", "coverage"]
        read_only_fields = ["created_at", "updated_at"]

    def validate_symbol(self, value: str) -> str:
        symbol = str(value).strip().upper().replace("-", "_").replace("/", "_")
        if not symbol:
            raise serializers.ValidationError("Symbol is required.")
        if "_" not in symbol:
            raise serializers.ValidationError(
                "Use the exchange pair format, e.g. BTC_USDT."
            )
        return symbol

    def get_coverage(self, obj) -> dict:
        """Recorded span for this symbol — None until the first trade lands."""
        from .ledger import available_range

        try:
            span = available_range(obj.symbol)
        except Exception:  # noqa: BLE001 — a missing ledger dir is not an error
            span = None
        if span is None:
            return {"recording_since": None, "recorded_until": None, "hours": 0.0}
        first, last = span
        return {
            "recording_since": first,
            "recorded_until": last,
            "hours": round((last - first) / 3_600_000, 2),
        }
