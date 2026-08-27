from __future__ import annotations

from rest_framework import serializers

from apps.security.models import SecurityEvent


class SecurityEventSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = SecurityEvent
        fields = ["id", "kind", "label", "at", "username", "ip_address", "user_agent", "detail"]
