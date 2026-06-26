from celery import shared_task


@shared_task(name="integrations.signum_send_webhook")
def signum_send_webhook_task(user_id: int, payload: str):
    from django.contrib.auth import get_user_model

    from apps.integrations.signum import send_signum_webhook

    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return {"ok": False, "error": "user_not_found"}
    return send_signum_webhook(user, payload)
