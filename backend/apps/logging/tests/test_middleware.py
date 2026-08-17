from unittest.mock import MagicMock

from apps.logging.middleware import RequestLoggingMiddleware
from apps.logging.models import LogEntry


def _make_request(path="/api/trading/policy/", method="GET"):
    request = MagicMock()
    request.path = path
    request.method = method
    request.META = {}
    request.user = MagicMock(is_authenticated=False)
    return request


def _make_response(status_code=200):
    response = MagicMock()
    response.status_code = status_code
    return response


def test_middleware_logs_a_mutation(db):
    def view(request):
        return _make_response(200)

    middleware = RequestLoggingMiddleware(view)
    middleware(_make_request(method="POST"))
    assert LogEntry.objects.filter(category="SYSTEM").exists()


def test_a_successful_read_is_not_an_event(db):
    """The panel polls several endpoints every few seconds. Persisting those made
    the log a traffic capture and buried everything worth reading."""

    def view(request):
        return _make_response(200)

    RequestLoggingMiddleware(view)(_make_request(method="GET"))
    assert LogEntry.objects.count() == 0


def test_a_failed_read_is_kept(db):
    def view(request):
        return _make_response(404)

    RequestLoggingMiddleware(view)(_make_request(method="GET"))
    assert LogEntry.objects.get().level == "WARNING"


def test_middleware_skips_health(db):
    def view(request):
        return _make_response(200)

    middleware = RequestLoggingMiddleware(view)
    request = _make_request(path="/api/health/")
    middleware(request)
    assert LogEntry.objects.count() == 0


def test_middleware_logs_5xx_as_error(db):
    def view(request):
        return _make_response(500)

    middleware = RequestLoggingMiddleware(view)
    request = _make_request()
    middleware(request)
    entry = LogEntry.objects.first()
    assert entry.level == "ERROR"


def test_middleware_logs_4xx_as_warning(db):
    def view(request):
        return _make_response(404)

    middleware = RequestLoggingMiddleware(view)
    request = _make_request()
    middleware(request)
    entry = LogEntry.objects.first()
    assert entry.level == "WARNING"


def test_middleware_skips_the_log_api_itself(db):
    """Reading the log wrote a row and broadcast it, so the tail filled with
    the act of watching it."""

    def view(request):
        return _make_response(200)

    RequestLoggingMiddleware(view)(_make_request(path="/api/logging/logs/"))
    assert LogEntry.objects.count() == 0


def test_a_request_naming_an_account_is_tagged_with_it(db):
    """Without the tag the row says `/api/accounts/7/` with account_id=None, and
    the hidden-account filter has nothing to match on."""

    def view(request):
        return _make_response(200)

    RequestLoggingMiddleware(view)(_make_request(path="/api/accounts/7/pause/", method="POST"))
    assert LogEntry.objects.get().account_id == 7


def test_every_row_of_one_request_shares_a_request_id(db):
    """`request_id` was a column nothing ever wrote."""
    import logging

    def view(request):
        logging.getLogger("apps.engine.test").warning("something inside the view")
        return _make_response(200)

    RequestLoggingMiddleware(view)(_make_request(method="POST"))
    ids = set(LogEntry.objects.values_list("request_id", flat=True))
    assert len(ids) == 1
    assert ids != {None}
