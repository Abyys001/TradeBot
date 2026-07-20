from rest_framework import serializers

from .models import SignumConfig


class SignumConfigSerializer(serializers.ModelSerializer):
    bot_id = serializers.CharField(write_only=True, required=False, allow_blank=True)
    webhook_url = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_bot_id = serializers.SerializerMethodField()
    has_webhook_url = serializers.SerializerMethodField()

    class Meta:
        model = SignumConfig
        fields = (
            "enabled",
            "order_size_default",
            "use_settings_bot_id",
            "has_bot_id",
            "has_webhook_url",
            "bot_id",
            "webhook_url",
            "updated_at",
        )
        read_only_fields = ("has_bot_id", "has_webhook_url", "updated_at")

    def get_has_bot_id(self, obj) -> bool:
        return bool(obj.bot_id_enc)

    def get_has_webhook_url(self, obj) -> bool:
        return bool(obj.webhook_url_enc)

    def create(self, validated_data):
        bot_id = validated_data.pop("bot_id", "")
        webhook_url = validated_data.pop("webhook_url", "")
        user = self.context["request"].user
        cfg, _ = SignumConfig.objects.get_or_create(user=user, defaults=validated_data)
        for k, v in validated_data.items():
            setattr(cfg, k, v)
        if bot_id:
            cfg.set_bot_id(bot_id)
        if webhook_url:
            cfg.set_webhook_url(webhook_url)
        cfg.save()
        return cfg

    def update(self, instance, validated_data):
        bot_id = validated_data.pop("bot_id", None)
        webhook_url = validated_data.pop("webhook_url", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if bot_id is not None:
            instance.set_bot_id(bot_id)
        if webhook_url is not None:
            instance.set_webhook_url(webhook_url)
        instance.save()
        return instance
