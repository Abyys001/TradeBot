from rest_framework import serializers
from .models import TelegramConfig, AlertWhitelist


class TelegramConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramConfig
        fields = ["bot_token", "enabled", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"bot_token": {"write_only": True}}


class AlertWhitelistSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertWhitelist
        fields = ["id", "chat_id", "label", "enabled", "created_at"]
        read_only_fields = ["id", "created_at"]
