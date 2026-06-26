from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from .models import HistoryDownload

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
            from .history_download import build_initial_progress

            data["progress"] = build_initial_progress(
                instance.coins,
                instance.intervals,
                instance.data_types or ["ohlcv"],
            )
        return data
