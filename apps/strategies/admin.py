from django.contrib import admin

from .models import Strategy, StrategyState


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "symbol", "type", "status", "created_at")
    list_filter = ("status", "type")


@admin.register(StrategyState)
class StrategyStateAdmin(admin.ModelAdmin):
    list_display = ("strategy", "last_signal", "pnl", "updated_at")
