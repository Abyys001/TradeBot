from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.logging.context import new_request_id, reset_request_id, set_request_id

#: ``/api/logging/`` is here for the same reason ``/api/health/`` is, only more
#: so: reading the log wrote a row, that row was broadcast to the panel, and the
#: panel's own refresh therefore appeared in the tail it was refreshing. The log
#: filled with the act of looking at it. Mutations under that prefix audit
#: themselves explicitly (see ``LogEntryViewSet.prune``), so nothing is lost.
SKIP_PATHS = ("/api/health/", "/ws/", "/api/logging/")

#: The account a request is *about*, when the URL names one. Without this the
#: row carries ``account_id=None`` and the hidden-account filter in
#: ``LogEntryViewSet`` has nothing to match on, so ``GET /api/accounts/7/`` would
#: report the existence of hidden account 7 to a reader who may not see it.
_ACCOUNT_IN_PATH = re.compile(r"/accounts/(\d+)(?:/|$)")

#: Methods that change something. A *successful* request with any other method
#: only read state, and is logged at DEBUG — which ``DatabaseHandler`` does not
#: persist. This is the difference between a log and a traffic capture: the panel
#: polls positions, tickers, balances, notifications and the policy every few
#: seconds, so nine rows in ten were "the admin's browser asked a question and
#: got an answer", burying the fan-out warnings the page exists to show (and
#: adding six figures of rows a day for the prune button to fight). Failures
#: (>=400) are always kept, whatever the method.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

logger = logging.getLogger("apps.logging.access")


class RequestLoggingMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith(SKIP_PATHS):
            return self.get_response(request)

        # Set before the view runs so *everything* the view logs — engine
        # warnings, adapter errors, the access row below — shares one id.
        token = set_request_id(new_request_id())
        try:
            start = time.perf_counter()
            response = self.get_response(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 1)

            status = response.status_code
            if status >= 500:
                level = "ERROR"
            elif status >= 400:
                level = "WARNING"
            elif request.method in MUTATING_METHODS:
                level = "INFO"
            else:
                level = "DEBUG"

            account_match = _ACCOUNT_IN_PATH.search(request.path)

            logger.log(
                getattr(logging, level),
                "%s %s %s %sms",
                request.method,
                request.path,
                status,
                duration_ms,
                extra={
                    "category": "SYSTEM",
                    "account_id": int(account_match.group(1)) if account_match else None,
                    "context": {
                        "method": request.method,
                        "path": request.path,
                        "status": status,
                        "duration_ms": duration_ms,
                        "remote_addr": request.META.get("REMOTE_ADDR", ""),
                    },
                },
            )
            return response
        finally:
            reset_request_id(token)
