from unittest.mock import MagicMock

from apps.logging.models import LogEntry
from apps.logging.middleware import RequestLoggingMiddleware


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


def test_middleware_logs_request(db):
    def view(request):
        return _make_response(200)

    middleware = RequestLoggingMiddleware(view)
    request = _make_request()
    middleware(request)
    assert LogEntry.objects.filter(category="SYSTEM").exists()


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
