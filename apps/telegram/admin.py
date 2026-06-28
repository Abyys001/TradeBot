from django.contrib import admin

from .models import AlertWhitelist, TelegramConfig


@admin.register(TelegramConfig)
class TelegramConfigAdmin(admin.ModelAdmin):
    list_display = ["user", "enabled", "created_at", "updated_at"]


@admin.register(AlertWhitelist)
class AlertWhitelistAdmin(admin.ModelAdmin):
    list_display = ["user", "chat_id", "label", "enabled", "created_at"]
