from django.contrib import admin

from .models import CopyOrder, CopySignal, CopySubscription, CopyTrade, EquitySnapshot


@admin.register(CopySignal)
class CopySignalAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "is_active", "platform_share_pct", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    exclude = ("secret_token",)


@admin.register(CopySubscription)
class CopySubscriptionAdmin(admin.ModelAdmin):
    list_display = ("signal", "credential", "risk_factor", "is_active", "created_at")
    list_filter = ("is_active",)


@admin.register(CopyOrder)
class CopyOrderAdmin(admin.ModelAdmin):
    list_display = ("subscription", "pair", "side", "status", "size", "created_at")
    list_filter = ("side", "status")


@admin.register(CopyTrade)
class CopyTradeAdmin(admin.ModelAdmin):
    list_display = ("subscription", "status", "gross_pnl", "platform_share_amount", "opened_at", "closed_at")
    list_filter = ("status",)


@admin.register(EquitySnapshot)
class EquitySnapshotAdmin(admin.ModelAdmin):
    list_display = ("subscription", "balance", "equity", "captured_at")
