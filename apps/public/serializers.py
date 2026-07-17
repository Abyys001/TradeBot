from rest_framework import serializers

from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    # Honeypot: a real visitor never fills this in. Bots that autofill every
    # field will trip it. Write-only, never persisted.
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Lead
        fields = ["name", "email", "contact", "message", "locale", "website"]

    def validate_locale(self, value):
        return value if value in ("en", "fa") else ""
