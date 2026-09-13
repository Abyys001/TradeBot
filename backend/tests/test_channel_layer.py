"""The WebSocket's channel layer, and the one number that has to be bigger.

An idle consumer is not idle at the Redis level: ``channels_redis`` parks it in
a ``BZPOPMIN`` that blocks server-side for ``RedisChannelLayer.brpop_timeout``
seconds. The client's own socket read deadline therefore has to outlive that
block, or the client gives up on a command that was working correctly.

redis-py 8 changed its async ``socket_timeout`` default from "never" to five
seconds — the same five seconds ``channels_redis`` blocks for. The two expired
together and the client won the race every time: ``TimeoutError: Timeout
reading from redis:6379`` out of ``await_many_dispatch``, the consumer dead,
and the panel's socket dropped seconds after every connect. Six idle receives
out of six failed on the deployment; nothing that rides that socket — bot
state, per-leg fan-out results, failure notices, the latency readings — arrived
at all, and every drop was logged as a system error.

The fix is one setting. This is the test that stops it coming back, from either
side: a ``channels_redis`` that decides to block for longer, or a redis-py that
lowers its default again.
"""

from __future__ import annotations

from django.conf import settings


def test_the_socket_read_outlives_the_blocking_pop():
    from channels_redis.core import RedisChannelLayer

    assert settings.REDIS_SOCKET_TIMEOUT > RedisChannelLayer.brpop_timeout, (
        "the Redis read deadline must outlive the BZPOPMIN it waits on, or every "
        "idle consumer dies on a command that was behaving correctly"
    )


def test_the_channel_layer_carries_that_timeout_onto_the_connection():
    """Pinned as the *shape* of the config, not only as a number in settings.

    ``channels_redis`` passes a host dict straight to
    ``ConnectionPool.from_url(address, **rest)``, so the timeout only takes
    effect when the host is a dict carrying it. A bare URL string — which is
    what this was — silently takes redis-py's default instead, and the failure
    that follows is a dropped WebSocket rather than an error at start-up.

    Built here rather than read off ``settings.CHANNEL_LAYERS``: the suite runs
    with ``REDIS_URL`` blanked on purpose, so the live setting is the in-memory
    layer and the branch that matters would never be looked at.
    """
    from channels_redis.utils import decode_hosts

    from config.settings import channel_layer_config

    layer = channel_layer_config("redis://redis:6379/0")["default"]
    assert "channels_redis" in layer["BACKEND"]
    for host in decode_hosts(layer["CONFIG"]["hosts"]):
        assert host.get("socket_timeout") == settings.REDIS_SOCKET_TIMEOUT


def test_without_a_redis_the_layer_is_in_memory():
    """What the test suite itself runs on, and what a laptop with no Redis gets."""
    from config.settings import channel_layer_config

    layer = channel_layer_config("")["default"]
    assert layer["BACKEND"] == "channels.layers.InMemoryChannelLayer"
