from django.contrib import admin

from .models import ExchangeCredential


@admin.register(ExchangeCredential)
class ExchangeCredentialAdmin(admin.ModelAdmin):
    list_display = ("user", "exchange", "label", "network", "is_active", "last_verified_at")
    list_filter = ("exchange", "network", "is_active")
    search_fields = ("label", "wallet_address", "agent_address")
    exclude = ("agent_private_key_enc",)
