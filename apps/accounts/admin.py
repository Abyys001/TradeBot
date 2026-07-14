from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_trading_enabled", "is_staff", "created_at")
    list_filter = UserAdmin.list_filter + ("role", "is_trading_enabled")
    fieldsets = UserAdmin.fieldsets + (
        ("Trading", {"fields": ("role", "is_trading_enabled", "must_change_password")}),
    )
