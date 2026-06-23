from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "is_trading_enabled", "is_staff", "created_at")
    list_filter = UserAdmin.list_filter + ("is_trading_enabled",)
    fieldsets = UserAdmin.fieldsets + (
        ("Trading", {"fields": ("is_trading_enabled",)}),
    )
