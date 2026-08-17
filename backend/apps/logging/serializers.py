from rest_framework import serializers

from apps.logging.models import LogEntry


class LogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LogEntry
        fields = [
            "id",
            "timestamp",
            "level",
            "category",
            "source",
            "message",
            "account_id",
            "trade_id",
            "exchange",
            "error_code",
            "context",
            "request_id",
        ]
        read_only_fields = fields
