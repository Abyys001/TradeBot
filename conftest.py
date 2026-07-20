"""Project-wide pytest configuration.

Overrides Django CACHES and CHANNEL_LAYERS to use in-memory backends so
tests run without a live Redis server.
"""
import pytest
from django.test import override_settings


@pytest.fixture(autouse=True, scope="session")
def _local_backends():
    with override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            }
        },
        CHANNEL_LAYERS={
            "default": {
                "BACKEND": "channels.layers.InMemoryChannelLayer",
            }
        },
    ):
        yield
