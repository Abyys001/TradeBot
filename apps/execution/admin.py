from django.contrib import admin

from .models import ExecutionLog, OrderRecord


@admin.register(OrderRecord)
class OrderRecordAdmin(admin.ModelAdmin):
    list_display = ("exchange_order_id", "strategy", "symbol", "side", "status", "created_at")
    list_filter = ("side", "status")


@admin.register(ExecutionLog)
class ExecutionLogAdmin(admin.ModelAdmin):
    list_display = ("level", "event", "strategy", "created_at")
    list_filter = ("level",)
