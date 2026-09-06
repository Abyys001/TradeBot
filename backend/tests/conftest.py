import logging

import pytest
from django.core.cache import cache

from apps.exchanges.paper import reset_paper_state
from apps.logging.handlers import DatabaseHandler
from apps.security import flags


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

    ``flags.invalidate`` goes with it: the security policy is also held in a
    per-process snapshot, and one test switching a control on would otherwise
    leave it on for up to a second of the next one.
    """
    cache.clear()
    flags.invalidate()
    yield
    cache.clear()
    flags.invalidate()


@pytest.fixture(autouse=True)
def _clean_bot_supervisor():
    """Running bots are tracked module-globally, and a leaked one outlives its loop.

    ``supervisor._TASKS`` holds one asyncio task per running bot. A test that
    starts a bot without stopping it leaves the entry behind pointing at a task
    on *that* test's event loop, which is closed by the time the next test
    runs. The next call to ``stop_all`` — the kill switch's flatten path, which
    stops every bot before it closes positions (Q22) — then awaits a future
    attached to a dead loop and dies with ``RuntimeError``, failing a test that
    never went near bot mode. Dropping the registry keeps one test's bot out of
    another test's halt.
    """
    from apps.bots import supervisor

    supervisor._TASKS.clear()
    yield
    supervisor._TASKS.clear()


@pytest.fixture(autouse=True)
def _detach_log_writer():
    """Keep the ``/logs`` handler off the root logger while tests run.

    ``DatabaseHandler`` writes a ``LogEntry`` row per record, and from the
    event loop it does so on its own writer thread — a second sqlite connection
    inserting rows while the test's transaction is open. That is fine in
    production and poison in a test run: the writes land mid-teardown and the
    table locks, failing whichever test happened to log at the wrong moment.
    The handler's own behaviour is covered by ``test_logging_handler.py``,
    which builds one directly and is unaffected by this.
    """
    root = logging.getLogger()
    detached = [h for h in root.handlers if isinstance(h, DatabaseHandler)]
    for handler in detached:
        root.removeHandler(handler)
    yield
    for handler in detached:
        root.addHandler(handler)


def ledger_settings(**overrides) -> dict:
    """``settings.LEDGER`` with a few keys changed, and the rest real.

    ``override_settings(LEDGER={...})`` replaces the whole dict, so a test that
    wanted to move one threshold used to delete every other key with it — and a
    new key would then only fail once someone read it. Merging onto the live
    defaults keeps ``config/settings.py`` the one place the values live.
    """
    from django.conf import settings

    return {**settings.LEDGER, **overrides}
