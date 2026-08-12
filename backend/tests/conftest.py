import pytest
from django.core.cache import cache

from apps.exchanges.paper import reset_paper_state


@pytest.fixture(autouse=True)
def _clean_paper_state():
    """Demo positions are process-global, so wipe them between tests.

    Without this a trade opened in one test would still be open in the next.
    """
    reset_paper_state()
    yield
    reset_paper_state()


@pytest.fixture(autouse=True)
def _clean_cache():
    """The cache spans tests too — it holds the kill-switch flag and market data.

    A test that halts routing would otherwise leave every later test halted.
    """
    cache.clear()
    yield
    cache.clear()
