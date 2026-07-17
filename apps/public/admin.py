from django.contrib import admin

from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "contact", "status", "locale", "created_at")
    list_filter = ("status", "locale")
    search_fields = ("name", "email", "contact")
    readonly_fields = ("created_at",)
