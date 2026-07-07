"""Celery application instance.

Broker / result backend / schedule are configured from Django settings
(CELERY_* keys). Tasks are autodiscovered from each installed app's tasks.py.
"""
from celery import Celery

app = Celery("tradebot")

# Pull config from Django settings, keys prefixed with CELERY_.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks.py in every installed app.
app.autodiscover_tasks()

# Beat schedule is configured via CELERY_BEAT_SCHEDULE in Django settings.


@app.task(name="config.ping")
def ping():
    """Health-check task: confirms worker <-> broker round-trip."""
    return "pong"
