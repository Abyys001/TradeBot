"""Celery tasks for credential health."""
from celery import shared_task

from apps.exchange.hl_client import verify_credential

from .models import ExchangeCredential


@shared_task(name="credentials.verify_credential")
def verify_credential_task(credential_id: int):
    """Re-validate one credential against Hyperliquid."""
    try:
        cred = ExchangeCredential.objects.get(pk=credential_id)
    except ExchangeCredential.DoesNotExist:
        return {"ok": False, "detail": "credential not found"}
    ok, detail = verify_credential(cred)
    return {"ok": ok, "detail": detail}
