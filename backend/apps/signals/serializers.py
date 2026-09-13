"""The panel's view of a signal source. The secret is never in it.

Write-only in the strict sense the platform uses everywhere else: the server
does not send the secret, not even masked, because a value the browser holds is
a value in a heap dump, a screenshot and a support ticket. It is returned
exactly once — in the response to the create that generated it — and after that
the only thing anyone can see is the fingerprint.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.bots.models import Bot, BotState
from apps.signals.models import SignalEvent, SignalSource


class SignalSourceSerializer(serializers.ModelSerializer):
    endpoint = serializers.CharField(read_only=True)
    secret_set = serializers.SerializerMethodField()
    bot_name = serializers.CharField(source="bot.name", read_only=True)
    symbol = serializers.CharField(source="bot.symbol", read_only=True)

    class Meta:
        model = SignalSource
        fields = [
            "id",
            "name",
            "bot",
            "bot_name",
            "symbol",
            "token",
            "endpoint",
            "secret_set",
            "secret_fingerprint",
            "enabled",
            "require_signature",
            "allowed_ips",
            "replay_window_seconds",
            "created_at",
            "created_by",
            "last_seen_at",
            "last_accepted_at",
        ]
        read_only_fields = [
            "token",
            "secret_fingerprint",
            "created_at",
            "created_by",
            "last_seen_at",
            "last_accepted_at",
        ]

    def get_secret_set(self, obj: SignalSource) -> bool:
        return obj.has_secret

    def validate_bot(self, bot: Bot) -> Bot:
        if not bot.is_webhook:
            raise serializers.ValidationError(
                f"“{bot.name}” takes its signals from a Pine script. Set its signal "
                "source to webhook before binding an external strategy to it — a bot "
                "driven by both would have two things deciding one position."
            )
        return bot

    def validate_allowed_ips(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("allowed_ips must be a list of addresses")
        return [str(entry).strip() for entry in value if str(entry).strip()]

    def validate(self, attrs):
        """Refuse the one combination that turns the endpoint into a bare URL.

        An unsigned webhook is a link: anyone who has ever seen it — a proxy
        log, a screenshot, a browser history — can open and close positions
        with it. It is allowed while the bot is in paper, where it is genuinely
        useful for getting a sender working, and refused the moment real money
        is behind it.
        """
        instance = self.instance
        require = attrs.get(
            "require_signature",
            instance.require_signature if instance else True,
        )
        bot = attrs.get("bot", instance.bot if instance else None)
        if not require and bot is not None and bot.state == BotState.LIVE:
            raise serializers.ValidationError(
                {
                    "require_signature": (
                        "a live bot's webhook must be signed — without a signature the "
                        "endpoint URL is the only thing standing between anyone who has "
                        "seen it and this bot's positions"
                    )
                }
            )
        return attrs


class SignalEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignalEvent
        fields = [
            "id",
            "source",
            "received_at",
            "remote_addr",
            "signal_id",
            "verb",
            "verdict",
            "code",
            "detail",
            "payload",
            "actions",
            "run",
        ]
        read_only_fields = fields
