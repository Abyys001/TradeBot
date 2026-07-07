from django.contrib import admin

from .models import Backtest, BacktestTrade


class BacktestTradeInline(admin.TabularInline):
    model = BacktestTrade
    extra = 0


@admin.register(Backtest)
class BacktestAdmin(admin.ModelAdmin):
    list_display = ("id", "strategy", "status", "symbol", "created_at")
    list_filter = ("status",)
    inlines = [BacktestTradeInline]
