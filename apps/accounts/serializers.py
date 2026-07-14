from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "is_trading_enabled",
            "role",
            "must_change_password",
        )


class InvestorSerializer(serializers.ModelSerializer):
    """Admin-facing read view of an investor account."""

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "role",
            "is_trading_enabled",
            "is_active",
            "must_change_password",
            "date_joined",
            "last_login",
            "created_at",
        )
        read_only_fields = fields


class InvestorCreateSerializer(serializers.ModelSerializer):
    """Admin creates an investor: username + temp password, forced change on first login."""

    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "is_trading_enabled")

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(
            role=User.Role.INVESTOR,
            must_change_password=True,
            **validated_data,
        )
        user.set_password(password)
        user.save()
        return user
